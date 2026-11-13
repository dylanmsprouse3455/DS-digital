"""Exclusive publication policy tests; no public writes or real email."""
from contextlib import closing
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from publication_gate import (
    preflight,source_policy,publisher_lock,activate_enabled,PublicationBlocked)
from production_quota import ProductionLedger
from release_coordinator import Store
from test_release_coordinator import example, RAW,SOURCE_URL,T0

def git(root,*args):
    p=subprocess.run(["git",*args],cwd=root,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr)
    return p.stdout.strip()

class PolicyTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ds-publisher-policy-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.main=self.root/"main"
        self.main.mkdir()
        git(self.main,"init","-q","-b","main")
        (self.main/"index.html").write_text("Synthetic original main")
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Fixture","-c","user.email=fixture@invalid.local",
            "commit","-q","-m","synthetic origin")
        self.sha=git(self.main,"rev-parse","HEAD")
        self.collector=self.root/"raw.sqlite3"
        raw=RAW.encode("utf-8")
        self.digest=sha256(raw).hexdigest()
        with closing(sqlite3.connect(self.collector)) as c:
            c.executescript("""
            CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT);
            CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,
            raw_body BLOB,sha256 TEXT,source_url TEXT);
            """)
            c.execute("INSERT INTO documents VALUES(1,'fictional')")
            c.execute("INSERT INTO revisions VALUES(1,1,?,?,?)",(raw,self.digest,SOURCE_URL))
            c.commit()
        self.store=Store(self.root/"private-editorial")
        self.ledger=ProductionLedger(self.root/"private-quota")
        self.ledger.initialize_verified_baseline(self.main,self.sha,T0)
        self.story=example(1,self.digest)
        self.store.submit(self.story,"writer-task",T0)
        self.store.review(self.story["id"],"independent-editor","approved",self.collector,T0,
                          "Original synthetic-source quote and proposal classification checked.")

    def check(self,**kw):
        return preflight(self.story["id"],ledger=self.ledger,main=self.main,remote_sha=self.sha,
                         editorial_db=self.store.path,source_db=self.collector,
                         at=kw.get("at",T0))

    def test_good_low_risk_story_read_only_pass(self):
        item=self.check()
        self.assertTrue(item["no_publication_performed"])
        self.assertEqual(item["remaining_new_slots"],4)
        self.assertEqual(item["independent_reviewer"],"independent-editor")
        self.assertFalse(item["unattended_activation"])

    def test_preflight_does_not_reserve_daily_slot(self):
        self.check()
        self.assertEqual(self.ledger.inspect(T0)["slots_reserved_or_live"],0)

    def test_inflight_release_blocks_another(self):
        self.ledger.reserve_approved(self.story["id"],self.main,self.sha,
                                     self.store.path,self.collector,T0)
        with self.assertRaisesRegex(PublicationBlocked,"in-flight"):
            self.check()

    def test_high_risk_allegation_screen_blocks(self):
        draft=dict(self.story,title="An official arrested after public incident")
        with self.assertRaisesRegex(PublicationBlocked,"high-risk"):
            source_policy(draft,T0)

    def test_private_personal_information_does_not_bypass_sensitive_flag(self):
        draft=dict(self.story,sensitive=True)
        with self.assertRaisesRegex(PublicationBlocked,"sensitive"):
            source_policy(draft,T0)

    def test_unapproved_domain_blocks(self):
        draft=dict(self.story,sources=[{"url":"https://example.com/article","kind":"official"}])
        with self.assertRaisesRegex(PublicationBlocked,"source"):
            source_policy(draft,T0)

    def test_changed_official_source_but_false_label_blocks(self):
        draft=dict(self.story,sources=[{"url":SOURCE_URL,"kind":"user-post"}])
        with self.assertRaisesRegex(PublicationBlocked,"source"):
            source_policy(draft,T0)

    def test_stale_draft_blocks(self):
        later=T0+timedelta(days=30)
        with self.assertRaisesRegex(PublicationBlocked,"stale"):
            source_policy(self.story,later)

    def test_proposal_status_preserved(self):
        self.assertTrue(source_policy(self.story,T0)["low_risk_screen_passed"])
        self.assertTrue(source_policy(self.story,T0)["automated_policy_is_not_full_fact_check"])

    def test_tampered_main_preflight_fails_closed(self):
        (self.main/"untracked.txt").write_text("different source")
        with self.assertRaisesRegex(PublicationBlocked,"verification failed"):
            self.check()

    def test_publisher_exclusive_lock_rejects_other_publisher(self):
        root=self.root/"publisher-lock"
        with publisher_lock(root):
            with self.assertRaisesRegex(PublicationBlocked,"exclusive lock"):
                with publisher_lock(root):pass

    def test_no_activation_marker_by_default(self):
        self.assertFalse(activate_enabled(self.root/"publisher-lock"))
        self.assertFalse((self.root/"publisher-lock"/"publication-activation.json").exists())

    def test_marker_wrong_permissions_rejected(self):
        root=self.root/"activation"
        root.mkdir()
        marker=root/"publication-activation.json"
        marker.write_text(json.dumps({"enabled":True,
            "explicit_owner_activation":"separately-approved",
            "daily_new_cap":4,
            "exclusive_publisher":"ds-blog-production-single-writer",
            "correction_policy":"source-bound-with-history"}))
        self.assertFalse(activate_enabled(root)) # file initially 0644
        marker.chmod(0o600)
        self.assertTrue(activate_enabled(root)) # synthetic test only, not real path

    def test_activation_does_not_directly_deploy(self):
        root=self.root/"activation"
        root.mkdir(exist_ok=True)
        (root/"publication-activation.json").write_text(json.dumps({"enabled":True,
            "explicit_owner_activation":"separately-approved","daily_new_cap":4,
            "exclusive_publisher":"ds-blog-production-single-writer",
            "correction_policy":"source-bound-with-history"}))
        (root/"publication-activation.json").chmod(0o600)
        self.assertTrue(activate_enabled(root))
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],0)

if __name__=="__main__": unittest.main(verbosity=2)