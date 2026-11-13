"""Staging-only GitHub release candidate and rollback-preparation regression tests."""
from __future__ import annotations
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from release_candidate import prepare_candidate, ReleaseBlocker, cmd
from release_coordinator import Store, BUILD_ROOT
from test_release_coordinator import example, RAW, SOURCE_URL, T0


def git(*args, cwd:Path):
    p=subprocess.run(["git",*args],cwd=cwd,text=True,capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr)
    return p.stdout.strip()


class ReleaseCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=tempfile.TemporaryDirectory(prefix="ds-release-gate-")
        cls.dir=Path(cls.scratch.name)
        cls.main=cls.dir/"main"
        cls.main.mkdir()
        git("init","-q","-b","main",cwd=cls.main)
        # A tiny synthetic stand-in for the original production repo.
        for name,content in [
            ("CNAME","dsdigitaldesigns.org\n"),
            ("README.md","Original unrelated site files must remain unchanged.\n"),
            ("index.html","<html><title>Original main</title></html>\n"),
            ("blog-v2.html","<html><title>Old live blog</title></html>\n"),
            ("sitemap.xml","<urlset></urlset>\n"),
            ("post-high-converting-websites.html","First old post\n"),
            ("post-small-business-security.html","Second old post\n"),
            ("post-site-speed-revenue.html","Third old post\n"),
        ]:
            (cls.main/name).write_text(content)
        git("add",".",cwd=cls.main)
        git("-c","user.name=Local Fixture","-c","user.email=local@invalid.example","commit","-q","-m","Simulated baseline main",cwd=cls.main)
        cls.baseline=git("rev-parse","HEAD",cwd=cls.main)
        # Clone an existing Git commit. Never push, deploy or alter current source.
        cls.source=cls.dir/"source"
        git("clone","-q","--no-hardlinks",str(ROOT),str(cls.source),cwd=cls.dir)
        assert (cls.source/"assets/css/blog-local.css").is_file()
        cls.fakecollector=cls.dir/"fakesources.sqlite3"
        raw=RAW.encode("utf-8")
        cls.hash=sha256(raw).hexdigest()
        with closing(sqlite3.connect(cls.fakecollector)) as db:
            db.executescript("""
            CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT);
            CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,raw_body BLOB,sha256 TEXT,source_url TEXT);
            """)
            db.execute("INSERT INTO documents VALUES(1,'synthetic-government')")
            db.execute("INSERT INTO revisions VALUES(1,1,?,?,?)",(raw,cls.hash,SOURCE_URL))
            db.commit()
        cls.store=Store(cls.dir/"private")
        draft=example(1,cls.hash)
        cls.store.submit(draft,"writer-task",T0)
        cls.store.review(draft["id"],"independent-editor","approved",cls.fakecollector,T0,
                         "Independently checked simulated source quote and proposal framing.")
        reservation=cls.store.reserve(draft["id"],T0)
        cls.release_id=reservation["release_id"]
        cls.staged=cls.store.stage(cls.release_id,T0)
        cls.bundle=Path(cls.staged["bundle"])
        cls.build=Path(cls.staged["preview_root"])
        cls.baseline_files={n:(cls.main/n).read_bytes() for n in
          ("CNAME","index.html","README.md","post-high-converting-websites.html",
           "post-small-business-security.html","post-site-speed-revenue.html")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.build,ignore_errors=True)
        cls.scratch.cleanup()

    def setUp(self):
        self.target=self.dir/("candidate-"+str(self._testMethodName))
        self.addCleanup(lambda:shutil.rmtree(self.target,ignore_errors=True))

    def candidate(self,main=None,bundle=None,sha=None,source=None):
        return prepare_candidate(main or self.main,self.build,bundle or self.bundle,
                                 source or self.source,self.target,sha or self.baseline)

    def test_candidate_has_5_files_including_required_bootstrap_assets(self):
        c=self.candidate()
        self.assertEqual(c.base_sha,self.baseline)
        self.assertEqual(c.report["mode"],"RELEASE_CANDIDATE_NOT_PUBLISHED")
        self.assertEqual(c.report["remote_deployment_permitted"],False)
        self.assertEqual(c.report["email_delivery_permitted"],False)
        self.assertEqual(c.report["published_verification"],False)
        self.assertEqual(len(c.file_paths),5)
        for f in ("assets/css/blog-local.css","assets/js/blog-local.js",
                  "blog-v2.html","sitemap.xml","greeneville/proposed-synthetic-test-trail-1.html"):
            self.assertIn(f,c.file_paths)
        self.assertNotIn("CNAME",c.file_paths)

    def test_main_unchanged_after_preparing_candidate(self):
        self.candidate()
        self.assertEqual(git("rev-parse","HEAD",cwd=self.main),self.baseline)
        self.assertEqual(git("status","--porcelain",cwd=self.main),"")
        for name,bytes_ in self.baseline_files.items():
            self.assertEqual((self.main/name).read_bytes(),bytes_)

    def test_candidate_parent_and_exact_diff(self):
        c=self.candidate()
        checkout=c.root/"git"
        self.assertEqual(git("rev-parse","HEAD^",cwd=checkout),self.baseline)
        self.assertEqual(git("status","--porcelain",cwd=checkout),"")
        changed=git("diff","--name-only","HEAD^","HEAD",cwd=checkout).splitlines()
        self.assertEqual(sorted(changed),sorted(c.file_paths))
        self.assertTrue((checkout/"greeneville/proposed-synthetic-test-trail-1.html").is_file())

    def test_rollback_can_restore_exact_previous_tree_locally(self):
        c=self.candidate()
        checkout=c.root/"git"
        before_tree=git("rev-parse","HEAD^:{tree}",cwd=checkout) if False else git("rev-parse","HEAD^{tree}",cwd=self.main)
        git("-c","user.name=Local Fixture","-c","user.email=local@invalid.example","revert","--no-edit","HEAD",cwd=checkout)
        restored_tree=git("rev-parse","HEAD^{tree}",cwd=checkout)
        self.assertEqual(before_tree,restored_tree)
        self.assertEqual(git("rev-parse","HEAD",cwd=self.main),self.baseline)

    def test_candidate_directory_collision_is_blocked(self):
        self.target.mkdir()
        with self.assertRaisesRegex(ReleaseBlocker,"reuse"):
            self.candidate()

    def test_wrong_main_sha_fails_before_mutating_repo(self):
        with self.assertRaisesRegex(ReleaseBlocker,"moved"):
            self.candidate(sha="0"*40)
        self.assertEqual(git("status","--porcelain",cwd=self.main),"")

    def test_wrong_branch_fails(self):
        git("checkout","-q","-b","other",cwd=self.main)
        try:
            with self.assertRaisesRegex(ReleaseBlocker,"wrong baseline"):
                self.candidate()
        finally:
            git("checkout","-q","main",cwd=self.main)
            git("branch","-D","other",cwd=self.main)

    def test_dirty_main_is_blocked(self):
        (self.main/"untracked.txt").write_text("untracked")
        try:
            with self.assertRaisesRegex(ReleaseBlocker,"uncommitted"):
                self.candidate()
        finally:
            (self.main/"untracked.txt").unlink()

    def test_main_change_is_blocked(self):
        (self.main/"README.md").write_text("changed main")
        git("add","README.md",cwd=self.main)
        git("-c","user.name=Local Fixture","-c","user.email=local@invalid.example","commit","-q","-m","changed main",cwd=self.main)
        try:
            with self.assertRaisesRegex(ReleaseBlocker,"moved"):
                self.candidate()
        finally:
            git("reset","-q","--hard",self.baseline,cwd=self.main)

    def test_corrupted_bundle_hash_fails(self):
        altered=self.dir/("altered-"+self._testMethodName+".json")
        obj=json.loads(self.bundle.read_text())
        obj["paths"][0]["sha256"]="a"*64
        altered.write_text(json.dumps(obj))
        self.addCleanup(lambda:altered.unlink(missing_ok=True))
        with self.assertRaisesRegex(ReleaseBlocker,"hash"):
            self.candidate(bundle=altered)

    def test_unauthorized_path_rejected(self):
        altered=self.dir/("altered-"+self._testMethodName+".json")
        obj=json.loads(self.bundle.read_text())
        obj["paths"][0]["path"]="CNAME"
        altered.write_text(json.dumps(obj))
        self.addCleanup(lambda:altered.unlink(missing_ok=True))
        with self.assertRaisesRegex(ReleaseBlocker,"allowed"):
            self.candidate(bundle=altered)

    def test_public_url_mismatch_rejected(self):
        altered=self.dir/("altered-"+self._testMethodName+".json")
        obj=json.loads(self.bundle.read_text())
        obj["proposed_public_url"]="https://evil.example.org/phishing"
        altered.write_text(json.dumps(obj))
        self.addCleanup(lambda:altered.unlink(missing_ok=True))
        with self.assertRaisesRegex(ReleaseBlocker,"public URL"):
            self.candidate(bundle=altered)

    def test_asset_collision_requires_review(self):
        p=self.main/"assets/css/blog-local.css"
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text("different css")
        git("add","assets/css/blog-local.css",cwd=self.main)
        git("-c","user.name=Local Fixture","-c","user.email=local@invalid.example","commit","-q","-m","synthetic asset",cwd=self.main)
        new_baseline=git("rev-parse","HEAD",cwd=self.main)
        try:
            with self.assertRaisesRegex(ReleaseBlocker,"differs"):
                self.candidate(sha=new_baseline)
        finally:
            git("reset","-q","--hard",self.baseline,cwd=self.main)
            p.unlink(missing_ok=True)

    def test_no_remote_push_codepath(self):
        # No git push is executed; a candidate git origin points to a local path.
        c=self.candidate()
        remote=git("remote","get-url","origin",cwd=c.root/"git")
        self.assertNotIn("github.com",remote)
        self.assertTrue(Path(remote).resolve()==self.main.resolve())
        self.assertEqual(git("rev-parse","HEAD",cwd=self.main),self.baseline)

if __name__=="__main__":
    unittest.main(verbosity=2)