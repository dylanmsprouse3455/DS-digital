"""Checkpoint 009 readiness test: NO side effects or automatic activation."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from activation_readiness import evaluate_readiness,snapshot,MIN_SUSTAINABLE_HEADROOM_GIB

BASE={
    "roles_ready":True,
    "scheduled_writer_run":True,
    "scheduled_editor_run":True,
    "receipt_verified":True,
    "signed_editor_credential_ready":True,
    "limited_publisher_credential_ready":True,
    "quota_healthy":True,
    "rollback_dry_run_passed":True,
    "production_rollback_verified":True,
    "gmail_verification_passed":True,
    "source_collector_tested":True,
    "extraction_editorial_quality_validated":True,
    "storage_headroom_gib":20.0,
    "owner_activation":True,
}

class ReadinessTests(unittest.TestCase):
    def test_pure_hypothetical_fully_ready_policy(self):
        result=evaluate_readiness(**BASE)
        self.assertTrue(result["unattended_activation_ready"])
        self.assertFalse(result["unattended_publisher_enabled_by_this_check"])

    def test_each_missing_gate_blocks_activation(self):
        for key in BASE:
            data=BASE.copy()
            data[key]=0 if key=="storage_headroom_gib" else False
            with self.subTest(gate=key):
                result=evaluate_readiness(**data)
                self.assertFalse(result["unattended_activation_ready"])
                gate="sustainable_storage_headroom" if key=="storage_headroom_gib" else {
                    "roles_ready":"dedicated_writer_editor_publisher_boundaries",
                    "scheduled_writer_run":"writer_real_unattended_execution",
                    "scheduled_editor_run":"editor_real_unattended_execution",
                    "receipt_verified":"cross_run_private_handoff_verification",
                    "signed_editor_credential_ready":"editor_signer_credential_separated",
                    "limited_publisher_credential_ready":"publisher_git_gmail_credential_scope",
                    "quota_healthy":"persistent_daily_quota",
                    "rollback_dry_run_passed":"recovery_dry_run_exact_tree",
                    "production_rollback_verified":"production_cdn_recovery_verified",
                    "gmail_verification_passed":"prior_live_gmail_receipt_verified",
                    "source_collector_tested":"official_source_collector_offline_tested",
                    "extraction_editorial_quality_validated":"reliable_real_story_extraction_and_editorial_review",
                    "owner_activation":"separate_owner_activation",
                }[key]
                self.assertIn(gate,result["failed_gates"])

    def test_storage_threshold_is_10_gib(self):
        self.assertEqual(MIN_SUSTAINABLE_HEADROOM_GIB,10)
        data={**BASE,"storage_headroom_gib":9.999}
        self.assertFalse(evaluate_readiness(**data)["unattended_activation_ready"])

    def test_no_automatic_schedule_added_even_if_ready(self):
        r=evaluate_readiness(**BASE)
        self.assertFalse(r["new_schedules_created_by_this_check"])

    def test_no_automatic_publisher_started_even_if_ready(self):
        r=evaluate_readiness(**BASE)
        self.assertFalse(r["unattended_publisher_enabled_by_this_check"])

    def test_connected_kali_snapshot_inactive_and_read_only(self):
        from activation_readiness import DEFAULT_ROOT
        if not (DEFAULT_ROOT/"publication-ledger.sqlite3").is_file():
            self.skipTest("user Kali production ledger not available")
        before=(DEFAULT_ROOT/"publication-ledger.sqlite3").stat()
        r=snapshot()
        after=(DEFAULT_ROOT/"publication-ledger.sqlite3").stat()
        self.assertFalse(r["result"]["unattended_activation_ready"])
        self.assertEqual(r["environment"]["new_posts_published_november_12"],1)
        self.assertTrue(r["environment"]["real_gmail_sent_receipt_present"])
        self.assertEqual((before.st_size,before.st_mtime_ns),
                         (after.st_size,after.st_mtime_ns))

if __name__=="__main__":unittest.main(verbosity=2)