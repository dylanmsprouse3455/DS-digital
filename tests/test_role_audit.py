"""No real credentials needed: dedicated role policy tests."""
from __future__ import annotations
from pathlib import Path
import sqlite3
from contextlib import closing
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from role_audit import role_boundary_policy, system_permissions_report, ROLE_NAMES

class RoleAuditTests(unittest.TestCase):
    def test_all_distinct_and_private_editor_key_can_pass_policy(self):
        uid=dict(zip(ROLE_NAMES,(3001,3002,3003)))
        result=role_boundary_policy(uid,3002,0o600)
        self.assertTrue(result["dedicated_permissions_ready"])
        self.assertTrue(result["no_accounts_or_credentials_created"])

    def test_same_uid_writer_and_editor_rejected(self):
        uid=dict(zip(ROLE_NAMES,(3001,3001,3003)))
        r=role_boundary_policy(uid,3001,0o600)
        self.assertFalse(r["dedicated_permissions_ready"])
        self.assertIn("writer_editor_publisher_uid_separation_missing",r["blockers"])

    def test_missing_publisher_account_rejected(self):
        uid={"ds-blog-writer":3001,"ds-blog-editor":3002,"ds-blog-publisher":None}
        r=role_boundary_policy(uid,3002,0o600)
        self.assertFalse(r["dedicated_permissions_ready"])

    def test_key_owner_is_not_editor_rejected(self):
        uid=dict(zip(ROLE_NAMES,(3001,3002,3003)))
        r=role_boundary_policy(uid,3003,0o600)
        self.assertIn("editor_private_signing_key_not_editor_owned",r["blockers"])

    def test_world_readable_private_key_rejected(self):
        uid=dict(zip(ROLE_NAMES,(3001,3002,3003)))
        r=role_boundary_policy(uid,3002,0o644)
        self.assertIn("editor_private_key_not_owner_only",r["blockers"])

    def test_no_private_key_rejected(self):
        uid=dict(zip(ROLE_NAMES,(3001,3002,3003)))
        r=role_boundary_policy(uid,None,None)
        self.assertFalse(r["dedicated_permissions_ready"])

    def test_public_audit_does_not_modify_or_create_files(self):
        t=tempfile.TemporaryDirectory(prefix="ds-role-readonly-")
        self.addCleanup(t.cleanup)
        root=Path(t.name)
        report=system_permissions_report(root/"state",root/"probe",root/"trust")
        self.assertFalse(report["unattended_activation_ready"])
        self.assertFalse(report["no_production_changes"] is False)
        self.assertFalse((root/"state").exists())
        self.assertFalse((root/"probe").exists())
        self.assertFalse((root/"trust").exists())

    def test_fake_preexisting_ledger_is_read_only(self):
        t=tempfile.TemporaryDirectory(prefix="ds-role-ledger-")
        self.addCleanup(t.cleanup)
        root=Path(t.name)
        state=root/"state";state.mkdir()
        database=state/"publication-ledger.sqlite3"
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE release_intents (kind TEXT,status TEXT)")
            db.execute("INSERT INTO release_intents VALUES('new','notified')")
            db.commit()
        before=database.stat()
        report=system_permissions_report(state,root/"probe",root/"trust")
        self.assertEqual(report["production_receipts"]["verified_new_posts"],1)
        self.assertEqual(report["production_receipts"]["sent_notified_posts"],1)
        after=database.stat()
        self.assertEqual((before.st_size,before.st_mtime_ns),
                         (after.st_size,after.st_mtime_ns))

if __name__=="__main__":unittest.main(verbosity=2)