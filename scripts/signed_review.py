#!/usr/bin/env python3
"""Checkpoint 009: pinned, detached Ed25519 editorial approval verification.

This module only verifies. It cannot sign a live review, publish or send mail.
The production trust root is deliberately NOT created by this checkpoint.
Key custody and task identity separation require a separately provisioned
trusted editor principal, outside the current shared Kali writer account.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import os
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from production_quota import verified_editorial_record
from publication_gate import preflight, PublicationBlocked

ALLOWED_KEYS = {"ds-editor-v1"}
CANONICAL_REPO = "dylanmsprouse3455/DS-digital"
SCOPE = "ds-blog-production-new-article-v1"
MAX_ATTESTATION_AGE = timedelta(hours=36)


class ApprovalBlocked(ValueError):
    pass


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def trusted_path(path: Path, *, require_outside_git: bool = True) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ApprovalBlocked("review or trust file unavailable/symlink")
    absolute = path.resolve()
    if require_outside_git and any(p == ".git" for p in absolute.parts):
        raise ApprovalBlocked("trust file inside a Git repository metadata directory")
    if (path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)) != 0:
        raise ApprovalBlocked("review or trust file is group/world-writable")
    return absolute


def approval_message(story_id: str, payload_sha: str, reviewer_id: str, *,
                     issued_at: str, expires_at: str) -> dict:
    """All inputs pinned into an unambiguous signed statement."""
    if not all(isinstance(v, str) and v for v in (story_id,payload_sha,reviewer_id,issued_at,expires_at)):
        raise ApprovalBlocked("approval fields are required")
    return {
        "schema_version":1,
        "scope":SCOPE,
        "repository":CANONICAL_REPO,
        "story_id":story_id,
        "payload_sha256":payload_sha,
        "reviewer_id":reviewer_id,
        "issued_at":issued_at,
        "expires_at":expires_at,
    }


def verify_signature(attestation_file: Path, public_key_file: Path,
                     story_id: str, payload_sha: str, reviewer_id: str,
                     writer_id: str, at: datetime) -> dict:
    if at.tzinfo is None: raise ApprovalBlocked("timezone-aware verifier time required")
    if reviewer_id == writer_id or not reviewer_id or not writer_id:
        raise ApprovalBlocked("writer/editor identities must differ")
    trusted_path(attestation_file)
    trusted_path(public_key_file)
    document = json.loads(Path(attestation_file).read_text("utf-8"))
    if set(document) != {"key_id","message","signature_b64"}:
        raise ApprovalBlocked("approval document has unknown or missing fields")
    if document["key_id"] not in ALLOWED_KEYS:
        raise ApprovalBlocked("unrecognized pinned editor key identity")
    msg = document["message"]
    if not isinstance(msg,dict) or set(msg) != set(approval_message(story_id,payload_sha,reviewer_id,
             issued_at=at.isoformat(),expires_at=at.isoformat())):
        raise ApprovalBlocked("wrong attestation message schema")
    expected = approval_message(story_id,payload_sha,reviewer_id,
                                issued_at=msg.get("issued_at"),expires_at=msg.get("expires_at"))
    if msg != expected:raise ApprovalBlocked("signed approval does not match draft or editor")
    try:
        issued=datetime.fromisoformat(msg["issued_at"])
        expiry=datetime.fromisoformat(msg["expires_at"])
    except (TypeError,ValueError) as ex:
        raise ApprovalBlocked("invalid approval timestamp") from ex
    if issued.tzinfo is None or expiry.tzinfo is None:
        raise ApprovalBlocked("approval timestamps must be offset-aware")
    if issued > at + timedelta(minutes=2) or expiry < at or expiry<=issued:
        raise ApprovalBlocked("approval expired or time-invalid")
    if expiry - issued > MAX_ATTESTATION_AGE or at - issued > MAX_ATTESTATION_AGE:
        raise ApprovalBlocked("editorial approval exceeds bounded validity")
    try:
        signature=base64.b64decode(document["signature_b64"],validate=True)
        pubkey=base64.b64decode(Path(public_key_file).read_text("utf-8").strip(),validate=True)
        if len(pubkey)!=32 or len(signature)!=64:
            raise ApprovalBlocked("malformed Ed25519 material")
        Ed25519PublicKey.from_public_bytes(pubkey).verify(signature,canonical_bytes(msg))
    except (InvalidSignature,ValueError,TypeError) as ex:
        raise ApprovalBlocked("review signature not verified") from ex
    return {"verified":True,"story_id":story_id,"payload_sha256":payload_sha,
            "reviewer_id":reviewer_id,"key_id":document["key_id"],
            "valid_until":expiry.isoformat(),"owner_activation":False}


def secure_preflight(story_id: str, *, ledger, main: Path, remote_sha: str,
                     editorial_db: Path, source_db: Path,
                     attestation_file: Path, public_key_file: Path,
                     at: datetime) -> dict:
    """Mandatory signed attestation PLUS original source/quotas checks.

    No production branch, public website or mail write occurs.
    """
    import sqlite3
    from contextlib import closing
    private=Path(editorial_db)
    with closing(sqlite3.connect("file:"+str(private.resolve())+"?mode=ro",uri=True)) as db:
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT payload_sha,writer_id FROM drafts WHERE story_id=?",(story_id,)).fetchone()
        review=db.execute("SELECT reviewer_id,verdict FROM reviews WHERE story_id=? AND payload_sha=?",
                          (story_id,row["payload_sha"])).fetchone() if row else None
    if not row or not review or review["verdict"]!="approved":
        raise ApprovalBlocked("no independently approved current draft")
    signed=verify_signature(attestation_file,public_key_file,story_id,row["payload_sha"],
                            review["reviewer_id"],row["writer_id"],at)
    eligible=preflight(story_id,ledger=ledger,main=main,remote_sha=remote_sha,
                       editorial_db=editorial_db,source_db=source_db,at=at)
    return {**eligible,"signed_editor_review":signed,
            "transport_authorized":False,"publication_enabled":False}