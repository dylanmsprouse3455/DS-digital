#!/usr/bin/env python3
"""Checkpoint 009: read-only dedicated publisher and editorial role audit.

Neither identities nor credentials are provisioned by this checkpoint.
Missing independent Unix principals / externally held signing credentials
are explicit production blockers, not reasons to fall back to one user.
"""
from __future__ import annotations
from pathlib import Path
import os
import pwd
import stat
import json
import sqlite3
from contextlib import closing

ROLE_NAMES = ("ds-blog-writer", "ds-blog-editor", "ds-blog-publisher")
DEFAULT_ROOT = Path("/var/lib/kali-ai-remote/ds-blog-production-pilot-state-006")
DEFAULT_PROBE = Path("/var/lib/kali-ai-remote/ds-blog-continuous-private-008/handoff-probe")
DEFAULT_TRUST = Path("/var/lib/kali-ai-remote/ds-blog-production-editor-trust-009")
DEFAULT_GITHUB = "dylanmsprouse3455/DS-digital"


def role_boundary_policy(uid_by_role: dict[str,int|None],
                         signer_owner_uid: int|None,
                         signing_key_mode: int|None) -> dict:
    """Pure policy evaluator for unit tests and the actual Kali read-only audit."""
    problems=[]
    if any(uid_by_role.get(role) is None for role in ROLE_NAMES):
        problems.append("dedicated_writer_editor_publisher_os_accounts_not_all_present")
    else:
        ids=[uid_by_role[role] for role in ROLE_NAMES]
        if len(set(ids))!=3:
            problems.append("writer_editor_publisher_uid_separation_missing")
        if signer_owner_uid != uid_by_role["ds-blog-editor"]:
            problems.append("editor_private_signing_key_not_editor_owned")
        if signing_key_mode is None or signing_key_mode & 0o077 or signing_key_mode & 0o600 != 0o600:
            problems.append("editor_private_key_not_owner_only")
    return {"dedicated_permissions_ready":len(problems)==0,
            "blockers":problems,
            "requires_separate_owner_provisioning":True,
            "no_accounts_or_credentials_created":True}


def system_permissions_report(
    state_root:Path=DEFAULT_ROOT,probe_root:Path=DEFAULT_PROBE,
    trust_root:Path=DEFAULT_TRUST
)->dict:
    uid_by_role={}
    for name in ROLE_NAMES:
        try:uid_by_role[name]=pwd.getpwnam(name).pw_uid
        except KeyError:uid_by_role[name]=None
    signing_file=trust_root/"editor-signing-private.key"
    signer_uid=signing_file.stat().st_uid if signing_file.is_file() and not signing_file.is_symlink() else None
    mode=(stat.S_IMODE(signing_file.stat().st_mode) if signer_uid is not None else None)
    roles=role_boundary_policy(uid_by_role,signer_uid,mode)
    ledger=state_root/"publication-ledger.sqlite3"
    probe_writer=probe_root/"writer-receipt.json"
    probe_editor=probe_root/"editor-ack.json"
    counts={"total_intents":None,"verified_new_posts":None,"sent_notified_posts":None}
    if ledger.is_file() and not ledger.is_symlink():
        with closing(sqlite3.connect("file:"+str(ledger.resolve())+"?mode=ro",uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            counts={
                "total_intents":db.execute("SELECT count(*) FROM release_intents").fetchone()[0],
                "verified_new_posts":db.execute("""SELECT count(*) FROM release_intents
                            WHERE kind='new' AND status IN ('live_verified','notified')""").fetchone()[0],
                "sent_notified_posts":db.execute("""SELECT count(*) FROM release_intents
                            WHERE status='notified'""").fetchone()[0],
            }
    writer_ok=probe_writer.is_file() and not probe_writer.is_symlink()
    editor_ok=probe_editor.is_file() and not probe_editor.is_symlink()
    shared_valid=False
    if writer_ok and editor_ok:
        from hashlib import sha256
        try:
            from unattended_probe import PROBE_ID
            writer_raw=probe_writer.read_bytes()
            w=json.loads(writer_raw)
            e=json.loads(probe_editor.read_text(encoding="utf-8"))
            shared_valid=(
                w.get("probe_id")==PROBE_ID and w.get("role")=="writer" and
                e.get("probe_id")==PROBE_ID and e.get("role")=="editor" and
                e.get("writer_receipt_sha256")==sha256(writer_raw).hexdigest())
        except (OSError,ValueError,KeyError):shared_valid=False
    blockers=list(roles["blockers"])
    if not shared_valid:
        blockers.append("writer_editor_unattended_kali_handoff_not_verified")
    if not trust_root.is_dir():
        blockers.append("trusted_editor_public_key_not_provisioned")
    if not (state_root/"publication-activation.json").is_file():
        blockers.append("unattended_production_authorization_absent")
    return {
        "mode":"READ_ONLY",
        "current_kali_euid":os.geteuid(),
        "role_uid_present":{name:(uid is not None) for name,uid in uid_by_role.items()},
        "role_boundaries":roles,
        "editor_signing_key_present":signer_uid is not None,
        "probe_writer_file_present":writer_ok,
        "probe_editor_file_present":editor_ok,
        "shared_probe_hash_valid":shared_valid,
        "unattended_execution_confirmed":False,  # Requires external scheduled-run receipts too.
        "production_receipts":counts,
        "unattended_activation_ready":False,
        "blockers":blockers,
        "no_production_changes":True,
    }

if __name__=="__main__":
    print(json.dumps(system_permissions_report(),indent=2))