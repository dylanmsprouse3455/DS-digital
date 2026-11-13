"""Handoff probe tests: simulated separate task executions, never real task proof."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from unattended_probe import run,ProbeBlocked

class HandoffTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ds-handoff-test-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.private=self.root/"private"
        self.collector=self.root/"collector.sqlite3"
        self.production=self.root/"production.sqlite3"
        for path,table in [(self.collector,"revisions"),(self.production,"release_intents")]:
            with closing(sqlite3.connect(path)) as db:
                db.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY)")
                db.execute(f"INSERT INTO {table}(id) VALUES(1)")
                db.commit()

    def run_role(self,role):
        return run(role,self.private,self.collector,self.production)

    def test_no_receipts_initially(self):
        r=self.run_role("status")
        self.assertFalse(r["writer_recorded"])
        self.assertFalse(r["editor_acknowledged"])
        self.assertFalse(self.private.exists())

    def test_editor_cannot_claim_writer_missing(self):
        with self.assertRaisesRegex(ProbeBlocked,"not present"):
            self.run_role("editor")
        self.assertFalse((self.private/"editor-ack.json").exists())

    def test_writer_receipt_reads_collector_only(self):
        a=self.run_role("writer")
        self.assertTrue(a["created"])
        self.assertEqual(a["collector_revisions"],1)
        self.assertFalse(a["unattended_execution_verified"])
        self.assertFalse((self.private/"editor-ack.json").exists())

    def test_write_once_is_idempotent(self):
        self.run_role("writer")
        b=self.run_role("writer")
        self.assertFalse(b["created"])

    def test_writer_and_editor_have_matching_receipt_hash(self):
        self.run_role("writer")
        res=self.run_role("editor")
        self.assertTrue(res["writer_receipt_hash_verified"])
        status=self.run_role("status")
        self.assertTrue(status["shared_workspace_handoff_valid"])
        self.assertFalse(status["unattended_execution_verified"])

    def test_editor_ack_is_idempotent(self):
        self.run_role("writer")
        self.run_role("editor")
        self.assertFalse(self.run_role("editor")["created"])

    def test_tampered_writer_receipt_breaks_ack(self):
        self.run_role("writer")
        self.run_role("editor")
        writer=self.private/"writer-receipt.json"
        data=json.loads(writer.read_text())
        data["publication_performed"]=True
        writer.write_text(json.dumps(data))
        self.assertFalse(self.run_role("status")["shared_workspace_handoff_valid"])

    def test_private_receipts_permissions(self):
        self.run_role("writer")
        self.run_role("editor")
        self.assertEqual(self.private.stat().st_mode&0o777,0o700)
        for f in self.private.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)

    def test_wrong_role_rejected(self):
        with self.assertRaises(ProbeBlocked):self.run_role("publisher")

    def test_symlinked_collector_rejected(self):
        link=self.root/"collector-link.sqlite3"
        link.symlink_to(self.collector)
        with self.assertRaisesRegex(ProbeBlocked,"symlink"):
            run("writer",self.private,link,self.production)

    def test_valid_writer_receipt_survives_new_instances(self):
        self.run_role("writer")
        again=run("editor",self.private,self.collector,self.production)
        self.assertTrue(again["recorded"])

if __name__=="__main__":unittest.main(verbosity=2)