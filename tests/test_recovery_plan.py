"""Local-only production rollback and crash-reconciliation safety tests."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from recovery_plan import prepare_local_revert, reconcile_inflight, RecoveryBlocked
from production_quota import ProductionLedger
from test_release_coordinator import T0

FILES={
"blog-v2.html":"NEW BLOG WITH ONE FIXTURE CARD",
"sitemap.xml":"<urlset><loc>mock article</loc></urlset>",
"assets/css/blog-local.css":"body { padding: 1em; }",
"assets/js/blog-local.js":"console.log('Synthetic test only')",
"greeneville/mock-test-article.html":"<html><h1>Fictional municipal item</h1></html>",
}

def git(cwd:Path,*args:str)->str:
    p=subprocess.run(["git",*args],cwd=cwd,text=True,capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr)
    return p.stdout.strip()


class RecoveryPlanTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ds-recovery-009-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.main=self.root/"main"
        self.main.mkdir()
        git(self.main,"init","-q","-b","main")
        (self.main/"index.html").write_text("UNRELATED ORIGINAL HOMEPAGE\n")
        (self.main/"CNAME").write_text("dsdigitaldesigns.org\n")
        (self.main/"post-site-speed-revenue.html").write_text("ORIGINAL OLD POST\n")
        (self.main/"blog-v2.html").write_text("OLD BLOG INDEX")
        (self.main/"sitemap.xml").write_text("<urlset/>")
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Fixture","-c","user.email=fixture@invalid.example",
            "commit","-q","-m","synthetic prior main")
        self.original=git(self.main,"rev-parse","HEAD")
        for name,content in FILES.items():
            path=self.main/name
            path.parent.mkdir(exist_ok=True,parents=True)
            path.write_text(content)
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Fixture","-c","user.email=fixture@invalid.example",
            "commit","-q","-m","synthetic pilot blog release")
        self.release=git(self.main,"rev-parse","HEAD")
        self.output=self.root/"private-rollback"

    def plan(self,**args):
        return prepare_local_revert(
            main_checkout=self.main,observed_main_sha=args.get("observed",self.release),
            target_release_sha=args.get("release",self.release),
            original_sha=args.get("original",self.original),
            output_dir=args.get("output",self.output),
            expected_paths=args.get("paths",set(FILES))
        )

    def test_revert_exactly_restores_pre_release_tree(self):
        plan=self.plan()
        self.assertEqual(plan["state"],"LOCAL_ROLLBACK_PLAN_ONLY")
        self.assertFalse(plan["production_git_ref_updated"])
        self.assertFalse(plan["public_rollback_attempted"])
        self.assertTrue(plan["requires_separate_owner_approval"])
        self.assertEqual(plan["restored_tree_sha"],git(self.main,"rev-parse",self.original+"^{tree}"))
        self.assertEqual(set(plan["changed_paths"]),set(FILES))
        self.assertEqual(git(self.main,"rev-parse","HEAD"),self.release)

    def test_unrelated_homepage_remains_original_in_revert(self):
        plan=self.plan()
        dest=Path(plan["private_checkout"])
        self.assertEqual((dest/"index.html").read_text(),"UNRELATED ORIGINAL HOMEPAGE\n")
        self.assertEqual((dest/"post-site-speed-revenue.html").read_text(),"ORIGINAL OLD POST\n")
        self.assertEqual((self.main/"blog-v2.html").read_text(),FILES["blog-v2.html"])

    def test_wrong_observed_main_blocks(self):
        with self.assertRaisesRegex(RecoveryBlocked,"baseline"):
            self.plan(observed="f"*40)
        self.assertFalse(self.output.exists())

    def test_intervening_commit_blocks(self):
        (self.main/"new-unrelated-file.txt").write_text("another legitimate website change")
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Fixture","-c","user.email=fixture@invalid.example",
            "commit","-q","-m","another actor changed main")
        latest=git(self.main,"rev-parse","HEAD")
        with self.assertRaisesRegex(RecoveryBlocked,"intervening"):
            self.plan(observed=latest)

    def test_dirty_main_blocks(self):
        (self.main/"untracked.txt").write_text("must not ignore other work")
        with self.assertRaisesRegex(RecoveryBlocked,"baseline"):
            self.plan()

    def test_wrong_previous_main_blocks(self):
        with self.assertRaisesRegex(RecoveryBlocked,"parent"):
            self.plan(original="f"*40)

    def test_wrong_file_allowlist_blocks(self):
        with self.assertRaisesRegex(RecoveryBlocked,"does not exactly match"):
            self.plan(paths={"blog-v2.html","sitemap.xml"})

    def test_unrelated_file_in_allowlist_rejected(self):
        with self.assertRaisesRegex(RecoveryBlocked,"unrelated website"):
            self.plan(paths=set(FILES)|{"CNAME"})

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        (self.output/"precious.txt").write_text("leave intact")
        with self.assertRaisesRegex(RecoveryBlocked,"fresh private"):
            self.plan()
        self.assertEqual((self.output/"precious.txt").read_text(),"leave intact")

    def test_local_clone_origin_not_real_github(self):
        r=self.plan()
        self.assertNotIn("github.com",git(Path(r["private_checkout"]),"remote","get-url","origin"))

    def test_plan_file_owner_only(self):
        self.plan()
        self.assertEqual((self.output/"rollback-plan.json").stat().st_mode&0o777,0o600)
        self.assertEqual(self.output.stat().st_mode&0o777,0o700)


class AmbiguousReleaseTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ds-ambiguous-009-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.ledger=ProductionLedger(self.root/"owner-state")
        self.rid="1"*32
        self.before="a"*40
        self.target="b"*40
        self.url="https://dsdigitaldesigns.org/greeneville/fictional-example.html"
        with self.ledger.tx() as db:
            db.execute("INSERT INTO control VALUES('verified_main_sha',?)",(self.before,))
            db.execute("""INSERT INTO release_intents
            (release_id,story_id,slug,payload_sha,local_day,kind,status,
             expected_main_sha,proposed_url,approved_reviewer,created_at,updated_at,
             candidate_commit_sha,desired_html_sha)
             VALUES(?,?,?,?,'2026-11-12','new','publishing',?,?,?,?,?,?,?)""",(
                self.rid,"synthetic-id","fictional-example","c"*64,self.before,
                self.url,"independent-editor",T0.isoformat(),T0.isoformat(),
                self.target,"d"*64))
            db.commit()

    def test_remote_candidate_requires_public_proof(self):
        result=reconcile_inflight(self.ledger,self.rid,self.target)
        self.assertEqual(result["finding"],"GITHUB_MAIN_HAS_CANDIDATE__PUBLIC_HTTP_PROOF_REQUIRED")
        self.assertFalse(result["quota_slot_freed"])
        self.assertTrue(result["requires_human_reconciliation"])

    def test_remote_unchanged_does_not_free_slot(self):
        result=reconcile_inflight(self.ledger,self.rid,self.before)
        self.assertEqual(result["finding"],"GITHUB_MAIN_STILL_AT_PRE_RELEASE_SHA__DO_NOT_AUTO_FREE_SLOT")
        self.assertEqual(self.ledger.inspect(T0)["remaining_slots"],3)

    def test_unexpected_remote_requires_manual_reconciliation(self):
        result=reconcile_inflight(self.ledger,self.rid,"e"*40)
        self.assertIn("UNEXPECTED",result["finding"])
        self.assertEqual(self.ledger.inspect(T0)["slots_reserved_or_live"],1)

    def test_missing_remote_sha_blocks(self):
        with self.assertRaisesRegex(RecoveryBlocked,"unavailable"):
            reconcile_inflight(self.ledger,self.rid,"")

    def test_published_receipt_cannot_be_reconciled_as_crash(self):
        with self.ledger.tx() as db:
            db.execute("UPDATE release_intents SET status='live_verified' WHERE release_id=?",(self.rid,))
            db.commit()
        with self.assertRaisesRegex(RecoveryBlocked,"no ambiguous"):
            reconcile_inflight(self.ledger,self.rid,self.target)

if __name__=="__main__":unittest.main(verbosity=2)