"""Checkpoint 008 official-source polling safety tests: all inserts are synthetic."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from source_cycle import (plan,read_registry,execute_cycle,activation_ok,
                          CollectionBlocked,exclusive_lock,MAX_DOCS_PER_RUN)

EASTERN=ZoneInfo("America/New_York")
STAMP=datetime.fromisoformat("2026-11-12T20:45:00-05:00")

class PollTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="ds-poller-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.private=self.root/"private"
        self.db=self.root/"source.sqlite3"
        self.db.write_bytes(b"synthetic source DB marker")
        self.registry=self.root/"registry.json"
        x=read_registry()
        self.registry.write_text(json.dumps(x))
        self.calls=[]

    def adapter(self,ids):
        self.calls.append(ids)
        # No real remote network. Mimic original collector receipt schema.
        return {"run_id":1,"added_revisions":len(ids),"duplicates":0}

    def test_registry_is_exact_existing_five_official_sources(self):
        x=read_registry(self.registry)
        self.assertEqual(len(x["sources"]),5)
        self.assertTrue(all(s["index_only"] for s in x["sources"]))

    def test_even_hour_rotates_town_group(self):
        p=plan(STAMP,self.registry)
        self.assertEqual(p["source_ids"],("town-agendas","town-events","town-events-program"))
        self.assertEqual(p["mode"],"PLAN_ONLY")

    def test_alternate_even_hour_rotates_county_group(self):
        t=datetime.fromisoformat("2026-11-12T22:45:00-05:00")
        self.assertEqual(plan(t,self.registry)["source_ids"],("county-notices","county-purchasing"))

    def test_timezone_aware_time_required(self):
        with self.assertRaisesRegex(CollectionBlocked,"timezone"):
            plan(datetime(2026,11,12,20,45),self.registry)

    def test_allowlist_change_blocked(self):
        x=json.loads(self.registry.read_text())
        x["sources"][0]["id"]="unapproved-news-site"
        self.registry.write_text(json.dumps(x))
        with self.assertRaisesRegex(CollectionBlocked,"allowlist"):
            plan(STAMP,self.registry)

    def test_disallow_new_domains(self):
        x=json.loads(self.registry.read_text())
        x["sources"][0]["url"]="https://someunknown.example/other"
        self.registry.write_text(json.dumps(x))
        with self.assertRaisesRegex(CollectionBlocked,"unapproved source"):
            plan(STAMP,self.registry)

    def test_poll_requires_separate_owner_activation(self):
        with self.assertRaisesRegex(CollectionBlocked,"not activated"):
            execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter)
        self.assertEqual(self.calls,[])

    def test_activation_absent_by_default(self):
        self.assertFalse(activation_ok(self.private,self.registry))
        self.assertFalse(self.private.exists())

    def test_test_adapter_collects_no_more_than_three(self):
        x=execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        self.assertEqual(x["added"],3)
        self.assertEqual(len(self.calls[0]),3)
        self.assertFalse(x["live_site_modified"])

    def test_receipt_is_private(self):
        execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        self.assertEqual(self.private.stat().st_mode&0o777,0o700)
        self.assertEqual((self.private/"collection-receipts.sqlite3").stat().st_mode&0o777,0o600)
        self.assertEqual((self.private/"collection.lock").stat().st_mode&0o777,0o600)

    def test_same_slot_no_retries(self):
        execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        with self.assertRaisesRegex(CollectionBlocked,"already attempted"):
            execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        self.assertEqual(len(self.calls),1)

    def test_next_slot_can_collect_other_group(self):
        execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        later=datetime.fromisoformat("2026-11-12T22:45:00-05:00")
        x=execute_cycle(later,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        self.assertEqual(x["added"],2)
        self.assertEqual(len(self.calls),2)

    def test_failed_adapter_does_not_reset_slot(self):
        def fail(_):raise RuntimeError("simulated offline robots failure")
        with self.assertRaisesRegex(RuntimeError,"simulated"):
            execute_cycle(STAMP,self.private,self.registry,self.db,fail,owner_enabled=True)
        with self.assertRaisesRegex(CollectionBlocked,"already attempted: failed"):
            execute_cycle(STAMP,self.private,self.registry,self.db,self.adapter,owner_enabled=True)
        self.assertEqual(self.calls,[])
        with closing(sqlite3.connect(self.private/"collection-receipts.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT status,error FROM collection_runs").fetchone(),
                             ("failed","RuntimeError"))

    def test_failed_schema_never_claims_success(self):
        with self.assertRaisesRegex(CollectionBlocked,"missing original collector receipt"):
            execute_cycle(STAMP,self.private,self.registry,self.db,lambda _:{"added":3},owner_enabled=True)
        with closing(sqlite3.connect(self.private/"collection-receipts.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT status FROM collection_runs").fetchone()[0],"failed")

    def test_oversized_receipt_rejected(self):
        with self.assertRaisesRegex(CollectionBlocked,"out of range"):
            execute_cycle(STAMP,self.private,self.registry,self.db,
                          lambda _:{"added_revisions":99,"duplicates":0},owner_enabled=True)

    def test_live_db_source_symlink_rejected(self):
        fake=self.root/"linked.sqlite"
        fake.symlink_to(self.db)
        with self.assertRaisesRegex(CollectionBlocked,"symlinked"):
            execute_cycle(STAMP,self.private,self.registry,fake,self.adapter,owner_enabled=True)

    def test_lock_rejects_concurrent_polling(self):
        with exclusive_lock(self.private):
            with self.assertRaisesRegex(CollectionBlocked,"already running"):
                with exclusive_lock(self.private):
                    pass

    def test_unauthorized_activation_marker_rejected(self):
        self.private.mkdir(mode=0o700)
        p=self.private/"activation.json"
        p.write_text(json.dumps({"enabled":True,"explicit_owner_activation":"separately-approved",
                 "source_registry_sha256":"0"*64}))
        p.chmod(0o600)
        self.assertFalse(activation_ok(self.private,self.registry))

    def test_plan_never_writes_to_collector(self):
        size=self.db.stat().st_size
        self.assertEqual(plan(STAMP,self.registry)["mode"],"PLAN_ONLY")
        self.assertEqual(self.db.stat().st_size,size)
        self.assertFalse(self.private.exists())

if __name__=="__main__":
    unittest.main(verbosity=2)