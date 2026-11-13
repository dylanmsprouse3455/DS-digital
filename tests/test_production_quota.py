"""Pilot production quota/state tests; all stories and repositories are fictional."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from email.message import Message
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from production_quota import ProductionLedger, QuotaBlocked, inspect_current_main, verified_editorial_record
from release_coordinator import Store
from test_release_coordinator import example, RAW, SOURCE_URL, T0, T1

def git(root: Path,*args):
    result=subprocess.run(["git",*args],cwd=root,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()

class FakeHTTP:
    status=200
    def __init__(self,url,body):
        self.url=url;self.body=body
        self.headers=Message()
        self.headers["Content-Type"]="text/html"
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,n):return self.body[:n]

def fake_release_page(url):
    return ('<html><head><link rel="canonical" href="'+url+'"></head>'
            '<body>Verified fictional article; not a real Greeneville event.</body></html>').encode()

class ProductionQuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="ds-prod-quota-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.main=self.root/"main"
        self.main.mkdir()
        git(self.main,"init","-q","-b","main")
        (self.main/"index.html").write_text("Original production main, synthetic")
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Test","-c","user.email=test@localhost.invalid",
            "commit","-q","-m","Synthetic main")
        self.baseline=git(self.main,"rev-parse","HEAD")
        self.collector=self.root/"collector.sqlite3"
        raw=RAW.encode()
        self.digest=sha256(raw).hexdigest()
        with closing(sqlite3.connect(self.collector)) as db:
            db.executescript("""
            CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT);
            CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,raw_body BLOB,sha256 TEXT,source_url TEXT);
            """)
            db.execute("INSERT INTO documents(id,source_id) VALUES(1,'test')")
            db.execute("INSERT INTO revisions VALUES(1,1,?,?,?)",(raw,self.digest,SOURCE_URL))
            db.commit()
        self.store=Store(self.root/"editorial-private")
        self.ledger=ProductionLedger(self.root/"production-private")

    def approve(self,i=1):
        story=example(i,self.digest)
        self.store.submit(story,"writer-task",T0)
        self.store.review(story["id"],"independent-editor","approved",self.collector,T0,
                          "Verified fictional source quote and proposal context.")
        return story

    def init(self):
        return self.ledger.initialize_verified_baseline(self.main,self.baseline,T0)

    def reserve(self,story,at=T0):
        return self.ledger.reserve_approved(story["id"],self.main,self.baseline,
                            self.store.path,self.collector,at)

    def test_first_baseline_records_empty_site(self):
        result=self.init()
        self.assertTrue(result["new"])
        self.assertEqual(result["existing_local_pages"],0)
        self.assertEqual(self.ledger.inspect(T0)["verified_main_sha"],self.baseline)

    def test_persistent_baseline_does_not_reset_on_restart(self):
        self.init()
        other=ProductionLedger(self.ledger.root)
        self.assertFalse(other.initialize_verified_baseline(self.main,self.baseline,T0)["new"])
        self.assertEqual(other.inspect(T0)["daily_new_cap"],4)

    def test_existing_article_inventory_requires_reconciliation(self):
        file=self.main/"greeneville"/"existing-local.html"
        file.parent.mkdir()
        file.write_text("<html>existing article</html>")
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Test","-c","user.email=test@localhost.invalid",
            "commit","-q","-m","Existing article")
        observed=git(self.main,"rev-parse","HEAD")
        with self.assertRaisesRegex(QuotaBlocked,"unknown pre-existing"):
            self.ledger.initialize_verified_baseline(self.main,observed,T0)

    def test_reserved_new_story_is_counted(self):
        self.init();story=self.approve()
        result=self.reserve(story)
        self.assertFalse(result["replay"])
        self.assertEqual(result["daily_remaining"],3)
        self.assertEqual(self.ledger.inspect(T0)["slots_reserved_or_live"],1)

    def test_duplicate_request_is_idempotent(self):
        self.init();story=self.approve()
        a=self.reserve(story);b=self.reserve(story)
        self.assertEqual(a["release_id"],b["release_id"])
        self.assertTrue(b["replay"])
        self.assertEqual(self.ledger.inspect(T0)["slots_reserved_or_live"],1)

    def test_four_limit_and_fifth_refused(self):
        self.init()
        for i in range(1,5):
            self.reserve(self.approve(i))
        with self.assertRaisesRegex(QuotaBlocked,"four new"):
            self.reserve(self.approve(5))
        self.assertEqual(self.ledger.inspect(T0)["remaining_slots"],0)

    def test_concurrent_attempts_never_exceed_four(self):
        self.init()
        stories=[self.approve(i) for i in range(1,10)]
        def attempt(story):
            try:self.reserve(story);return "accepted"
            except QuotaBlocked:return "blocked"
        with ThreadPoolExecutor(max_workers=9) as pool:
            values=list(pool.map(attempt,stories))
        self.assertEqual(values.count("accepted"),4)
        self.assertEqual(values.count("blocked"),5)

    def test_eastern_midnight_boundary(self):
        self.init()
        for i in range(1,5):self.reserve(self.approve(i))
        self.assertEqual(self.reserve(self.approve(5),T1)["daily_remaining"],3)
        self.assertEqual(self.ledger.inspect(T1)["slots_reserved_or_live"],1)

    def test_utc_midnight_does_not_reset_quota(self):
        self.init()
        for i in range(1,5):self.reserve(self.approve(i))
        near_midnight=datetime.fromisoformat("2026-11-13T01:00:00+00:00")
        with self.assertRaisesRegex(QuotaBlocked,"four new"):
            self.reserve(self.approve(5),near_midnight)

    def test_draft_needs_independent_editor_approval(self):
        self.init()
        story=example(1,self.digest)
        self.store.submit(story,"writer-task",T0)
        with self.assertRaisesRegex(QuotaBlocked,"distinct editor"):
            self.reserve(story)

    def test_unmatched_evidence_stops_reservation(self):
        self.init()
        story=self.approve()
        # Tamper the RAW SOURCE bytes, not the editorial approved record.
        with closing(sqlite3.connect(self.collector)) as c:
            c.execute("UPDATE revisions SET raw_body=? WHERE id=1",(b"tampered source bytes",))
            c.commit()
        with self.assertRaisesRegex(QuotaBlocked,"re-verification failed"):
            self.reserve(story)

    def test_stale_main_sha_fails(self):
        self.init()
        story=self.approve()
        with self.assertRaisesRegex(QuotaBlocked,"clean main"):
            self.ledger.reserve_approved(story["id"],self.main,"0"*40,
                                         self.store.path,self.collector,T0)

    def test_main_commit_change_requires_reconciliation(self):
        self.init()
        (self.main/"something.txt").write_text("changed")
        git(self.main,"add",".")
        git(self.main,"-c","user.name=Test","-c","user.email=test@localhost.invalid",
            "commit","-q","-m","Modified site")
        changed=git(self.main,"rev-parse","HEAD")
        story=self.approve()
        with self.assertRaisesRegex(QuotaBlocked,"changed"):
            self.ledger.reserve_approved(story["id"],self.main,changed,
                                         self.store.path,self.collector,T0)

    def test_dirty_main_fails(self):
        self.init()
        story=self.approve()
        (self.main/"untracked.txt").write_text("untracked")
        with self.assertRaisesRegex(QuotaBlocked,"clean main"):
            self.reserve(story)

    def test_prepared_and_publishing_states_persist(self):
        self.init();r=self.reserve(self.approve())
        self.ledger.prepared(r["release_id"],"a"*40,"b"*64,T0)
        self.ledger.publishing(r["release_id"],T0)
        restarted=ProductionLedger(self.ledger.root)
        self.assertEqual(restarted.inspect(T0)["intents"][0]["status"],"publishing")
        self.assertEqual(restarted.inspect(T0)["remaining_slots"],3)

    def test_uncertain_remains_reserved_after_crash(self):
        self.init();r=self.reserve(self.approve())
        self.ledger.prepared(r["release_id"],"a"*40,"b"*64,T0)
        self.ledger.publishing(r["release_id"],T0)
        self.ledger.mark_uncertain(r["release_id"],"GitHub timeout, status unresolved",T0)
        with self.assertRaises(QuotaBlocked):
            self.ledger.abort_unsubmitted(r["release_id"],"Would free occupied slot",T0)
        self.assertEqual(self.ledger.inspect(T0)["slots_reserved_or_live"],1)

    def test_abort_before_public_push_frees_slot(self):
        self.init();r=self.reserve(self.approve())
        self.ledger.abort_unsubmitted(r["release_id"],"Quality review retracted",T0)
        self.assertEqual(self.ledger.inspect(T0)["remaining_slots"],4)
        self.assertEqual(self.ledger.inspect(T0)["intents"][0]["status"],"aborted")

    def test_live_confirmation_rejects_wrong_commit(self):
        self.init();r=self.reserve(self.approve())
        payload=fake_release_page(r["url"])
        self.ledger.prepared(r["release_id"],"a"*40,sha256(payload).hexdigest(),T0)
        self.ledger.publishing(r["release_id"],T0)
        with self.assertRaisesRegex(QuotaBlocked,"GitHub main"):
            self.ledger.live_verified(r["release_id"],T0,
                remote_main_getter=lambda:"c"*40,
                fetch=lambda req,timeout:FakeHTTP(req.full_url,payload))

    def test_live_confirmation_rejects_wrong_url(self):
        self.init();r=self.reserve(self.approve())
        payload=fake_release_page(r["url"])
        self.ledger.prepared(r["release_id"],"a"*40,sha256(payload).hexdigest(),T0)
        self.ledger.publishing(r["release_id"],T0)
        with self.assertRaisesRegex(QuotaBlocked,"public HTTPS"):
            self.ledger.live_verified(r["release_id"],T0,
                remote_main_getter=lambda:"a"*40,
                fetch=lambda req,timeout:FakeHTTP(req.full_url+"?unexpected",payload))

    def test_live_receipt_updates_baseline_but_needs_new_checkout(self):
        self.init();r=self.reserve(self.approve())
        payload=fake_release_page(r["url"])
        self.ledger.prepared(r["release_id"],"a"*40,sha256(payload).hexdigest(),T0)
        self.ledger.publishing(r["release_id"],T0)
        proof=self.ledger.live_verified(r["release_id"],T0,
            remote_main_getter=lambda:"a"*40,
            fetch=lambda req,timeout:FakeHTTP(req.full_url,payload))
        self.assertEqual(proof["public_http"],200)
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],1)
        self.assertEqual(self.ledger.inspect(T0)["verified_main_sha"],"a"*40)
        with self.assertRaisesRegex(QuotaBlocked,"main.*changed"):
            self.reserve(self.approve(2))

    def test_no_public_proof_cannot_record_live_post(self):
        self.init();r=self.reserve(self.approve())
        payload=fake_release_page(r["url"])
        self.ledger.prepared(r["release_id"],"a"*40,sha256(payload).hexdigest(),T0)
        self.ledger.publishing(r["release_id"],T0)
        with self.assertRaisesRegex(QuotaBlocked,"public HTTPS"):
            self.ledger.live_verified(r["release_id"],T0,
                remote_main_getter=lambda:"a"*40,
                fetch=lambda req,timeout:FakeHTTP(req.full_url,b"wrong article"))
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],0)

    def test_gmail_receipt_is_required_for_notified_state(self):
        from verified_notification import NotificationOutbox
        self.init();r=self.reserve(self.approve())
        payload=fake_release_page(r["url"])
        self.ledger.prepared(r["release_id"],"a"*40,sha256(payload).hexdigest(),T0)
        self.ledger.publishing(r["release_id"],T0)
        self.ledger.live_verified(r["release_id"],T0,
            remote_main_getter=lambda:"a"*40,
            fetch=lambda req,timeout:FakeHTTP(req.full_url,payload))
        outbox=NotificationOutbox(self.root/"outbox-private")
        with self.assertRaisesRegex(QuotaBlocked,"no confirmed Gmail"):
            self.ledger.mark_notified(r["release_id"],outbox.path,T0)
        outbox.verify_and_queue(r["release_id"],r["url"],sha256(payload).hexdigest(),
                                "Synthetic local event preview",
                                fetch=lambda req,timeout:FakeHTTP(req.full_url,payload))
        outbox.claim(r["release_id"])
        outbox.record_sent(r["release_id"],"MOCK_GMAIL_TEST_123456789")
        result=self.ledger.mark_notified(r["release_id"],outbox.path,T0)
        self.assertEqual(result["status"],"notified")
        self.assertEqual(self.ledger.inspect(T0)["intents"][0]["status"],"notified")
        self.assertEqual(self.ledger.inspect(T0)["new_verified_live"],1)
        self.assertEqual(self.ledger.mark_notified(r["release_id"],outbox.path,T0)["status"],"notified")

    def test_database_is_private(self):
        self.assertEqual(self.ledger.root.stat().st_mode&0o777,0o700)
        self.assertEqual(self.ledger.path.stat().st_mode&0o777,0o600)

if __name__=="__main__":unittest.main(verbosity=2)