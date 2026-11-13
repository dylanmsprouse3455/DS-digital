"""Guarded local-bare Git transport and rollback; NEVER pushes to public remotes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from local_git_transport import (
    TransportBlocked,verify_local_bare,get_branch_sha,
    simulated_fast_forward_push,simulated_revert_rollback
)

LIVE_MAIN=Path("/var/lib/kali-ai-remote/ds-blog-main-baseline-c005")
TEST_CANDIDATE=Path("/var/lib/kali-ai-remote/ds-blog-release-candidate-demo-005/git")


def git(*args,cwd):
    r=subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True)
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout.strip()


class SimulatedGitTransportTests(unittest.TestCase):
    def setUp(self):
        if not LIVE_MAIN.is_dir() or not TEST_CANDIDATE.is_dir():
            self.skipTest("read-only main baseline and synthetic candidate not available")
        self.temp=tempfile.TemporaryDirectory(prefix="ds-blog-transport-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.remote=Path(self.temp.name)/"remote.git"
        git("clone","-q","--bare",str(LIVE_MAIN),str(self.remote),cwd=Path(self.temp.name))
        self.base=git("rev-parse","HEAD",cwd=LIVE_MAIN)
        self.candidate=git("rev-parse","HEAD",cwd=TEST_CANDIDATE)
        self.assertEqual(get_branch_sha(self.remote),self.base)

    def test_only_local_test_remote_allowed(self):
        self.assertEqual(verify_local_bare(self.remote),self.remote.resolve())
        with self.assertRaises(TransportBlocked):
            verify_local_bare(LIVE_MAIN)
        with self.assertRaises(TransportBlocked):
            verify_local_bare(Path("/var/lib/kali-ai-remote"))

    def test_local_push_is_fast_forward_and_not_live(self):
        receipt=simulated_fast_forward_push(TEST_CANDIDATE,self.remote,self.base)
        self.assertEqual(receipt["new_sha"],self.candidate)
        self.assertFalse(receipt["actual_live_published"])
        self.assertEqual(get_branch_sha(self.remote),self.candidate)
        self.assertEqual(git("rev-parse","HEAD",cwd=LIVE_MAIN),self.base)

    def test_stale_main_blocks_repeat(self):
        simulated_fast_forward_push(TEST_CANDIDATE,self.remote,self.base)
        with self.assertRaisesRegex(TransportBlocked,"changed"):
            simulated_fast_forward_push(TEST_CANDIDATE,self.remote,self.base)

    def test_wrong_expected_sha_blocks(self):
        with self.assertRaisesRegex(TransportBlocked,"changed"):
            simulated_fast_forward_push(TEST_CANDIDATE,self.remote,"a"*40)
        self.assertEqual(get_branch_sha(self.remote),self.base)

    def test_local_revert_restores_original_tree(self):
        simulated_fast_forward_push(TEST_CANDIDATE,self.remote,self.base)
        receipt=simulated_revert_rollback(self.remote,self.candidate,self.base)
        self.assertTrue(receipt["tree_restored"])
        self.assertFalse(receipt["live_rollback_executed"])
        self.assertNotEqual(receipt["rollback_commit"],self.base)
        self.assertEqual(get_branch_sha(self.remote),receipt["rollback_commit"])
        self.assertEqual(git("rev-parse","HEAD^{tree}",cwd=self.remote),
                         git("rev-parse",self.base+"^{tree}",cwd=LIVE_MAIN))

    def test_refuses_rollback_if_new_changes_intervened(self):
        simulated_fast_forward_push(TEST_CANDIDATE,self.remote,self.base)
        simulated_revert_rollback(self.remote,self.candidate,self.base)
        with self.assertRaisesRegex(TransportBlocked,"intervening"):
            simulated_revert_rollback(self.remote,self.candidate,self.base)


if __name__=="__main__":
    unittest.main(verbosity=2)