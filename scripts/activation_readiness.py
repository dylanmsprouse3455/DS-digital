#!/usr/bin/env python3
"""Checkpoint 009: single fail-closed readiness report, no activation action.

Combines authenticated source-bound review policy, unique role custody,
actual scheduled-run handoff receipts, current production quota state,
rollback proof, Gmail receipt and storage headroom.

The absence of external scheduled run IDs is always a blocker. This script
has no GitHub/Gmail write capabilities and never creates activation files.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import os

from role_audit import system_permissions_report, DEFAULT_ROOT
from publication_gate import activate_enabled
from production_quota import ProductionLedger
from source_cycle import activation_ok as collector_activation_ok, PRIVATE_ROOT as COLLECT_ROOT, REGISTRY

PRODUCTION_MAIN_EXPECTED_FROM_PILOT = "4707b655ec2ad6958382a50761b9fdf699f9bb62"
PRODUCTION_ROLLBACK_REPORT = Path("/var/lib/kali-ai-remote/ds-blog-c009-rollback-plan/rollback-plan.json")
MIN_SUSTAINABLE_HEADROOM_GIB = 10


def evaluate_readiness(
    *, roles_ready:bool, scheduled_writer_run:bool,
    scheduled_editor_run:bool, receipt_verified:bool,
    signed_editor_credential_ready:bool, limited_publisher_credential_ready:bool,
    quota_healthy:bool, rollback_dry_run_passed:bool,
    production_rollback_verified:bool, gmail_verification_passed:bool,
    source_collector_tested:bool, extraction_editorial_quality_validated:bool,
    storage_headroom_gib:float, owner_activation:bool
) -> dict:
    checks={
        "dedicated_writer_editor_publisher_boundaries":roles_ready,
        "writer_real_unattended_execution":scheduled_writer_run,
        "editor_real_unattended_execution":scheduled_editor_run,
        "cross_run_private_handoff_verification":receipt_verified,
        "editor_signer_credential_separated":signed_editor_credential_ready,
        "publisher_git_gmail_credential_scope":limited_publisher_credential_ready,
        "persistent_daily_quota":quota_healthy,
        "recovery_dry_run_exact_tree":rollback_dry_run_passed,
        "production_cdn_recovery_verified":production_rollback_verified,
        "prior_live_gmail_receipt_verified":gmail_verification_passed,
        "official_source_collector_offline_tested":source_collector_tested,
        "reliable_real_story_extraction_and_editorial_review":extraction_editorial_quality_validated,
        "sustainable_storage_headroom":storage_headroom_gib>=MIN_SUSTAINABLE_HEADROOM_GIB,
        "separate_owner_activation":owner_activation,
    }
    return {
        "unattended_activation_ready":all(checks.values()),
        "checks":checks,
        "failed_gates":[name for name,ok in checks.items() if not ok],
        "safe_staging_complete":all(checks[name] for name in (
            "persistent_daily_quota","recovery_dry_run_exact_tree",
            "prior_live_gmail_receipt_verified","official_source_collector_offline_tested")),
        "unattended_publisher_enabled_by_this_check":False,
        "new_schedules_created_by_this_check":False,
    }


def snapshot(*, scheduled_runs:dict|None=None)->dict:
    now=datetime.now(timezone.utc)
    roles=system_permissions_report()
    ledger=ProductionLedger(DEFAULT_ROOT)
    quota=ledger.inspect(now)
    actual=ledger.inspect(datetime.fromisoformat("2026-11-12T21:00:00-05:00"))
    mail=DEFAULT_ROOT/"outbox"/"notification-outbox.sqlite3"
    sent=False
    if mail.is_file() and not mail.is_symlink():
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect("file:"+str(mail.resolve())+"?mode=ro",uri=True)) as db:
            sent=db.execute("SELECT count(*) FROM notifications WHERE status='sent' AND gmail_message_id IS NOT NULL").fetchone()[0]>=1
    rollback_ok=False
    if PRODUCTION_ROLLBACK_REPORT.is_file() and not PRODUCTION_ROLLBACK_REPORT.is_symlink():
        try:
            report=json.loads(PRODUCTION_ROLLBACK_REPORT.read_text())
            rollback_ok=(report.get("state")=="LOCAL_ROLLBACK_PLAN_ONLY"
                    and report.get("production_git_ref_updated") is False
                    and report.get("original_main_sha")=="9ac82e6a6997e678db2b01c96f6a9aec8c55331b"
                    and report.get("release_main_sha")==PRODUCTION_MAIN_EXPECTED_FROM_PILOT
                    and len(report.get("changed_paths",[]))==5)
        except (OSError,ValueError):rollback_ok=False
    # Checkpoint 008 tests and staged service files are evidence of offline
    # validation, not of real recurring execution of its timer.
    staged=Path("/var/lib/kali-ai-remote/ds-blog-continuous-checkpoint-008-verified")
    source_tested=(staged/"tests/test_source_cycle.py").is_file() and (
        staged/"ops/staged-systemd/ds-blog-official-sources.timer").is_file()
    published=(actual["new_verified_live"]==1
               and len(actual["intents"])==1
               and actual["intents"][0]["status"]=="notified")
    free_gib=shutil.disk_usage(str(DEFAULT_ROOT)).free/(1024**3)
    requested_runs=scheduled_runs or {}
    writer_proof=bool(requested_runs.get("writer_completed_unattended"))
    editor_proof=bool(requested_runs.get("editor_completed_unattended"))
    # Never assert trusted unattended execution from local files alone.
    if not (writer_proof and editor_proof):
        writer_proof=False
        editor_proof=False
    return {
      "created_at_utc":now.isoformat(timespec="seconds"),
      "result":evaluate_readiness(
        roles_ready=roles["role_boundaries"]["dedicated_permissions_ready"],
        scheduled_writer_run=writer_proof,
        scheduled_editor_run=editor_proof,
        receipt_verified=bool(roles["shared_probe_hash_valid"] and writer_proof and editor_proof),
        signed_editor_credential_ready=roles["editor_signing_key_present"] and
                                       roles["role_boundaries"]["dedicated_permissions_ready"],
        limited_publisher_credential_ready=False,  # not provisioned, no inference
        quota_healthy=published and quota["daily_new_cap"]==4,
        rollback_dry_run_passed=rollback_ok,
        production_rollback_verified=False,   # not permitted this checkpoint
        gmail_verification_passed=sent,
        source_collector_tested=source_tested,
        extraction_editorial_quality_validated=False, # not proven over real cycles
        storage_headroom_gib=free_gib,
        owner_activation=activate_enabled(DEFAULT_ROOT) and collector_activation_ok(COLLECT_ROOT,REGISTRY),
      ),
      "environment":{
        "remote_main_known_from_last_live_pilot":PRODUCTION_MAIN_EXPECTED_FROM_PILOT,
        "actual_production_ledger_entries":len(quota["intents"]),
        "new_posts_published_november_12":actual["new_verified_live"],
        "real_gmail_sent_receipt_present":sent,
        "rollback_dry_run_verified":rollback_ok,
        "kali_available_free_gib":round(free_gib,2),
        "writer_receipt_present":roles["probe_writer_file_present"],
        "editor_receipt_present":roles["probe_editor_file_present"],
        "task_proof_supplied_for_this_check":bool(scheduled_runs),
        "publication_is_disabled":True,
      }
    }


if __name__=="__main__":
    print(json.dumps(snapshot(),indent=2))