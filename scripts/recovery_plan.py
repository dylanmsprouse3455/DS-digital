#!/usr/bin/env python3
"""Checkpoint 009: production rollback DRY RUN and ambiguous-release triage.

Only prepares a local Git revert commit in a private directory; it cannot
push or deploy. A live rollback requires separate explicit owner approval.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from hashlib import sha256
import json
import os
import re
import subprocess

from production_quota import inspect_current_main, ProductionLedger, QuotaBlocked

ALLOWED_RELEASE_PATHS={
    "blog-v2.html",
    "sitemap.xml",
    "assets/css/blog-local.css",
    "assets/js/blog-local.js",
}
ARTICLE_REGEX=re.compile(r"greeneville/[a-z0-9]+(?:-[a-z0-9]+)*\.html\Z")
SHA_REGEX=re.compile(r"[a-f0-9]{40}\Z")

class RecoveryBlocked(ValueError):
    pass


def git(cwd:Path,*args:str)->str:
    proc=subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,timeout=40)
    if proc.returncode:
        raise RecoveryBlocked("local Git inspection failed: "+args[0]+": "+proc.stderr[:180])
    return proc.stdout.strip()


def validate_changed_path(p:str)->None:
    if not isinstance(p,str) or PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts:
        raise RecoveryBlocked("unsafe rollback file path")
    if p not in ALLOWED_RELEASE_PATHS and not ARTICLE_REGEX.fullmatch(p):
        raise RecoveryBlocked("rollback would touch unrelated website file")


def prepare_local_revert(*, main_checkout:Path, observed_main_sha:str,
                         target_release_sha:str, original_sha:str,
                         output_dir:Path, expected_paths:set[str])->dict:
    """Prepare local rollback proof of exact tree restoration, with no push."""
    current_main=Path(main_checkout).resolve()
    out=Path(output_dir)
    if out.is_symlink() or out.exists() or out.resolve().is_relative_to(current_main):
        raise RecoveryBlocked("rollback output must be a fresh private directory")
    if any(not SHA_REGEX.fullmatch(s or "") for s in
           (observed_main_sha,target_release_sha,original_sha)):
        raise RecoveryBlocked("invalid rollback commit SHA")
    if not expected_paths or len(expected_paths)>10:
        raise RecoveryBlocked("expected rollback paths missing or too broad")
    for x in expected_paths:validate_changed_path(x)
    try:live_sha,_=inspect_current_main(current_main,observed_main_sha)
    except QuotaBlocked as e:raise RecoveryBlocked("main baseline mismatch") from e
    if live_sha!=target_release_sha:
        raise RecoveryBlocked("intervening production commits prevent this rollback")
    parent=git(current_main,"rev-parse","HEAD^")
    if parent!=original_sha:
        raise RecoveryBlocked("original parent SHA differs")
    files=set(git(current_main,"diff","--name-only",original_sha,target_release_sha).splitlines())
    if files!=expected_paths:
        raise RecoveryBlocked("changed path manifest does not exactly match approved release")
    before_tree=git(current_main,"rev-parse",original_sha+"^{tree}")
    if out.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise RecoveryBlocked("private rollback artifacts cannot be stored in source tree")
    out.mkdir(parents=True,mode=0o700)
    os.chmod(out,0o700)
    checkout=out/"rollback-git"
    git(out,"clone","--quiet","--no-hardlinks",str(current_main),str(checkout))
    if git(checkout,"rev-parse","HEAD")!=target_release_sha:
        raise RecoveryBlocked("private rollback clone does not match target")
    # All mutations are within out/rollback-git. No remote push or force.
    git(checkout,"-c","user.name=DS Blog Recovery Dry Run",
        "-c","user.email=local-recovery@invalid.example","revert","--no-edit",
        "--no-gpg-sign",target_release_sha)
    new_sha=git(checkout,"rev-parse","HEAD")
    restored_tree=git(checkout,"rev-parse","HEAD^{tree}")
    if restored_tree!=before_tree:
        raise RecoveryBlocked("local revert does not exactly restore original tree")
    if git(checkout,"status","--porcelain"):
        raise RecoveryBlocked("rollback checkout contains uncommitted modifications")
    altered=set(git(checkout,"diff","--name-only","HEAD^","HEAD").splitlines())
    if altered!=expected_paths:
        raise RecoveryBlocked("reversion changed unexpected paths")
    report={
        "state":"LOCAL_ROLLBACK_PLAN_ONLY",
        "original_main_sha":original_sha,
        "release_main_sha":target_release_sha,
        "rollback_commit_sha":new_sha,
        "restored_tree_sha":restored_tree,
        "changed_paths":sorted(files),
        "private_checkout":str(checkout),
        "production_git_ref_updated":False,
        "public_rollback_attempted":False,
        "gmail_action_performed":False,
        "requires_separate_owner_approval":True,
        "verified_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    receipt=out/"rollback-plan.json"
    receipt.write_text(json.dumps(report,sort_keys=True,indent=2),encoding="utf-8")
    os.chmod(receipt,0o600)
    return report


def reconcile_inflight(ledger:ProductionLedger,release_id:str,
                       observed_remote_sha:str)->dict:
    """Read-only, fail-closed triage after a timeout/crash; NO slot reset."""
    if not SHA_REGEX.fullmatch(observed_remote_sha or ""):
        raise RecoveryBlocked("current remote SHA unavailable")
    with ledger.tx() as db:
        row=db.execute("SELECT * FROM release_intents WHERE release_id=?",
                       (release_id,)).fetchone()
    if row is None:
        raise RecoveryBlocked("production release receipt not found")
    if row["status"] not in ("publishing","uncertain","prepared"):
        raise RecoveryBlocked("no ambiguous in-flight release to reconcile")
    target=row["candidate_commit_sha"]
    if observed_remote_sha==target and target:
        finding="GITHUB_MAIN_HAS_CANDIDATE__PUBLIC_HTTP_PROOF_REQUIRED"
    elif observed_remote_sha==row["expected_main_sha"]:
        finding="GITHUB_MAIN_STILL_AT_PRE_RELEASE_SHA__DO_NOT_AUTO_FREE_SLOT"
    else:
        finding="GITHUB_MAIN_UNEXPECTED__MANUAL_RECONCILIATION"
    return {
        "release_id":release_id,"status":row["status"],
        "finding":finding,"observed_main_sha":observed_remote_sha,
        "expected_main_sha":row["expected_main_sha"],
        "candidate_sha":target,
        "quota_slot_freed":False,"production_changed":False,
        "email_sent":False,
        "requires_human_reconciliation":True
    }