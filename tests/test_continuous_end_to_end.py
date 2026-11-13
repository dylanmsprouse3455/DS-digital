"""Full offline continuous-workflow lab: source -> review -> Git -> receipt -> mail.

ALL network, GitHub publishing, Gmail, and source data are synthetic/local.
The protected production database and real source collector are untouched.
"""
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from email.message import Message
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from source_cycle import execute_cycle,REGISTRY,read_registry
from release_coordinator import Store,BUILD_ROOT
from production_quota import ProductionLedger
from publication_gate import preflight,publisher_lock
from release_candidate import prepare_candidate
from local_git_transport import simulated_fast_forward_push,simulated_revert_rollback,get_branch_sha
from verified_notification import NotificationOutbox
from unattended_probe import run as probe_run
from test_release_coordinator import example,RAW,SOURCE_URL,T0

COLLECTOR_PATH=Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/collector.py")

def git(root,*args):
    result=subprocess.run(["git",*args],cwd=root,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    return result.stdout.strip()

class MockPublicResponse:
    status=200
    def __init__(self,url,content):
        self.url=url;self.content=content
        self.headers=Message()
        self.headers["Content-Type"]="text/html"
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,n):return self.content[:n]

class CombinedTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ds-blog-transport-fixture-full-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.db=self.root/"source.sqlite3"
        # Build a synthetic read-only-compatible DB. The protected original
        # collector explicitly refuses external state directories; never
        # bypass its guard or modify its files for a test.
        with closing(sqlite3.connect(self.db)) as fake:
            fake.executescript("""
            CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT,document_key TEXT);
            CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,
                raw_body BLOB,sha256 TEXT,source_url TEXT);
            """)
            fake.commit()
        self.registry=REGISTRY
        self.raw=RAW.encode()
        self.raw_sha=sha256(self.raw).hexdigest()
        self.writer=Store(self.root/"editorial")
        self.ledger=ProductionLedger(self.root/"production")
        self.main=self.root/"main"
        self.main.mkdir()
        git(self.main,"init","-q","-b","main")
        for n,body in [
            ("CNAME","dsdigitaldesigns.org\n"),
            ("index.html","Original home not to be modified"),
            ("blog-v2.html","<html><body>Old blog</body></html>"),
            ("sitemap.xml","<urlset/>"),
            ("post-high-converting-websites.html","Prior post 1"),
            ("post-small-business-security.html","Prior post 2"),
            ("post-site-speed-revenue.html","Prior post 3"),
        ]:
            (self.main/n).write_text(body)
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Fixture","-c","user.email=fixture@localhost.invalid",
            "commit","-q","-m","Original synthetic main")
        self.main_sha=git(self.main,"rev-parse","HEAD")
        self.ledger.initialize_verified_baseline(self.main,self.main_sha,T0)
        self.srcclone=self.root/"clean-source"
        git(self.root,"clone","-q",str(ROOT),str(self.srcclone))
        self.stage_ids=[]

    def tearDown(self):
        for i in self.stage_ids:
            shutil.rmtree(BUILD_ROOT/("release-"+i),ignore_errors=True)

    def ingest(self):
        from datetime import timezone
        raw_source={s["id"]:s for s in read_registry()["sources"]}
        def adapter(ids):
            records=[]
            for id in ids:
                source=raw_source[id]
                raw=self.raw if id=="town-agendas" else ("Synthetic public fixture "+id).encode()
                records.append({
                    "source_id":id,"source_url":source["url"],
                    "raw":raw,"kind":"source_snapshot",
                    "title":"Synthetic fixture "+id,
                    "document_key":"index","content_type":"text/plain",
                    "observed_at":T0.astimezone(timezone.utc).isoformat()
                })
            with closing(sqlite3.connect(self.db)) as fake:
                for index,rec in enumerate(records,start=1):
                    fake.execute("INSERT INTO documents VALUES(?,?,?)",
                                 (index,rec["source_id"],rec["document_key"]))
                    fake.execute("INSERT INTO revisions VALUES(?,?,?,?,?)",
                                 (index,index,rec["raw"],sha256(rec["raw"]).hexdigest(),rec["source_url"]))
                fake.commit()
            return {"run_id":1,"added_revisions":len(records),"duplicates":0}
        # Collect at 16:45 Eastern (town group), before the 18:00 draft.
        collection_time=datetime.fromisoformat("2026-11-12T16:45:00-05:00")
        return execute_cycle(collection_time,self.root/"collection",self.registry,self.db,adapter,owner_enabled=True)

    def reviewed_story(self):
        r=self.ingest()
        self.assertEqual(r["added"],3)
        story=example(1,self.raw_sha)
        self.writer.submit(story,"scheduled-writer-fixture",T0)
        self.writer.review(story["id"],"independent-editor-fixture","approved",self.db,T0,
                           "Checked the fictional proposed event against original source bytes.")
        return story

    def build_candidate(self,story):
        allowed=preflight(story["id"],ledger=self.ledger,main=self.main,
                           remote_sha=self.main_sha,editorial_db=self.writer.path,
                           source_db=self.db,at=T0)
        self.assertTrue(allowed["no_publication_performed"])
        reservation=self.ledger.reserve_approved(story["id"],self.main,self.main_sha,
                                                  self.writer.path,self.db,T0)
        rel=self.writer.reserve(story["id"],T0)
        self.stage_ids.append(rel["release_id"])
        stage=self.writer.stage(rel["release_id"],T0)
        candidate=prepare_candidate(
            self.main,Path(stage["preview_root"]),Path(stage["bundle"]),
            self.srcclone,self.root/"candidate",self.main_sha)
        html_path=Path("greeneville")/(story["slug"]+".html")
        content=(candidate.root/"git"/html_path).read_bytes()
        self.ledger.prepared(reservation["release_id"],candidate.commit_sha,
                             sha256(content).hexdigest(),T0)
        return reservation,candidate,content

    def test_full_e2e_synthetic_no_remote_or_gmail(self):
        story=self.reviewed_story()
        with publisher_lock(self.root/"exclusive-publisher"):
            reservation,candidate,article=self.build_candidate(story)
            self.assertEqual(len(candidate.file_paths),5)
            remote=self.root/"mock-bare-remote.git"
            git(self.root,"clone","-q","--bare",str(self.main),str(remote))
            self.ledger.publishing(reservation["release_id"],T0)
            receipt=simulated_fast_forward_push(candidate.root/"git",remote,self.main_sha)
            self.assertFalse(receipt["actual_live_published"])
            self.assertEqual(get_branch_sha(remote),candidate.commit_sha)
            url=reservation["url"]
            fetch=lambda req,timeout:MockPublicResponse(req.full_url,article)
            proof=self.ledger.live_verified(reservation["release_id"],T0,
                                 remote_main_getter=lambda:get_branch_sha(remote),fetch=fetch)
            self.assertEqual(proof["public_http"],200)
            outbox=NotificationOutbox(self.root/"private-outbox")
            q=outbox.verify_and_queue(reservation["release_id"],url,sha256(article).hexdigest(),
                story["title"],fetch=fetch)
            self.assertEqual(q["status"],"verified")
            claimed=outbox.claim(reservation["release_id"])
            self.assertIn(url,claimed["body"])
            outbox.record_sent(reservation["release_id"],"SYNTHETIC_GMAIL_RECEIPT_123456789")
            self.ledger.mark_notified(reservation["release_id"],outbox.path,T0)
            status=self.ledger.inspect(T0)
            self.assertEqual(status["new_verified_live"],1)
            self.assertEqual(status["intents"][0]["status"],"notified")
            self.assertEqual(status["remaining_slots"],3)
            self.assertEqual(git(self.main,"rev-parse","HEAD"),self.main_sha)

    def test_synthetic_crash_after_push_requires_reconcile(self):
        story=self.reviewed_story()
        reservation,candidate,content=self.build_candidate(story)
        remote=self.root/"mock-bare-remote.git"
        git(self.root,"clone","-q","--bare",str(self.main),str(remote))
        self.ledger.publishing(reservation["release_id"],T0)
        simulated_fast_forward_push(candidate.root/"git",remote,self.main_sha)
        self.ledger.mark_uncertain(reservation["release_id"],"simulated crash after remote commit",T0)
        with self.assertRaises(Exception):
            preflight(story["id"],ledger=self.ledger,main=self.main,remote_sha=self.main_sha,
                      editorial_db=self.writer.path,source_db=self.db,at=T0)
        self.assertEqual(self.ledger.inspect(T0)["remaining_slots"],3)
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],0)

    def test_synthetic_git_rollback_without_public_receipt(self):
        story=self.reviewed_story()
        reservation,candidate,content=self.build_candidate(story)
        remote=self.root/"mock-bare-remote.git"
        git(self.root,"clone","-q","--bare",str(self.main),str(remote))
        simulated_fast_forward_push(candidate.root/"git",remote,self.main_sha)
        rolled=simulated_revert_rollback(remote,candidate.commit_sha,self.main_sha)
        self.assertTrue(rolled["tree_restored"])
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],0)

    def test_private_writer_editor_probe_handoff_does_not_publish(self):
        # Invoked manually in this test, NOT proof of unattended access.
        self.ingest()
        self.assertTrue(probe_run("writer",self.root/"probe",self.db,self.ledger.path)["recorded"])
        self.assertTrue(probe_run("editor",self.root/"probe",self.db,self.ledger.path)["recorded"])
        handoff=probe_run("status",self.root/"probe",self.db,self.ledger.path)
        self.assertTrue(handoff["shared_workspace_handoff_valid"])
        self.assertFalse(handoff["unattended_execution_verified"])
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],0)

if __name__=="__main__":unittest.main(verbosity=2)