#!/usr/bin/env python3
"""Offline, immutable-URL corrections: source-backed body-only updates.

Does not push to GitHub, send mail or perform live rollback.
Corrections to headline, summary, publication date, slug or identity
require a separate full-manifest review (not silently attempted here).
"""
from __future__ import annotations
from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from production_quota import verified_editorial_record
from publication_gate import source_policy
from release_coordinator import public_story_payload
from build_local_stories import create_article

class CorrectionBlocked(ValueError):pass

SCHEMA="""
CREATE TABLE IF NOT EXISTS corrections (
  id TEXT PRIMARY KEY, story_id TEXT NOT NULL,
  canonical_path TEXT NOT NULL, old_sha256 TEXT NOT NULL, new_sha256 TEXT NOT NULL,
  main_sha TEXT NOT NULL, editor_id TEXT NOT NULL, reason TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status='STAGED_ONLY'),
  prepared_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ix_corrections_hash ON corrections(story_id,new_sha256);
"""

def prepare_correction(original:dict, story_id:str,
                       editorial_db:Path, evidence_db:Path,
                       production_checkout:Path,main_sha:str,
                       reason:str,private_root:Path,at:datetime)->dict:
    if not isinstance(reason,str) or not 35<=len(reason)<=500:
        raise CorrectionBlocked("substantive correction explanation required")
    if any(x in reason.lower() for x in ("retraction","allegation","arrest","privacy breach")):
        raise CorrectionBlocked("high-risk retraction or allegation requires owner review")
    approved=verified_editorial_record(editorial_db,evidence_db,story_id)
    update=approved["story"]
    source_policy(update,at)
    fixed=("id","slug","title","summary","location","category","published_at")
    if any(original.get(k)!=update.get(k) for k in fixed):
        raise CorrectionBlocked("identity/slug/headline/summary/first-published fields are immutable here")
    if update.get("updated_at")==original.get("updated_at"):
        raise CorrectionBlocked("correction needs a new modified timestamp")
    if datetime.fromisoformat(update["updated_at"])<=datetime.fromisoformat(original["updated_at"]):
        raise CorrectionBlocked("correction must be later than original article")
    if update.get("sections")==original.get("sections"):
        raise CorrectionBlocked("no substantive body correction")
    path="greeneville/"+original["slug"]+".html"
    main=Path(production_checkout)
    old_file=main/path
    if not old_file.is_file() or old_file.is_symlink():
        raise CorrectionBlocked("published original HTML is missing")
    expected_old=create_article(public_story_payload(original)).encode()
    old_bytes=old_file.read_bytes()
    if old_bytes!=expected_old:
        raise CorrectionBlocked("main article diverged from recorded original; reconcile history")
    approved_public=public_story_payload(update)
    approved_public["sections"].append({
        "heading":"Correction and update note",
        "paragraphs":[reason]})
    new_bytes=create_article(approved_public).encode()
    if old_bytes==new_bytes:
        raise CorrectionBlocked("correction did not change HTML")
    root=Path(private_root)
    if root.is_symlink() or root==Path("/") or ".git" in root.parts:
        raise CorrectionBlocked("private correction directory invalid")
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    dbfile=root/"corrections.sqlite3"
    if dbfile.is_symlink():raise CorrectionBlocked("corrections DB symlink rejected")
    stamp=at.isoformat(timespec="seconds")
    update_sha=sha256(new_bytes).hexdigest()
    release_id=sha256(("correction:"+story_id+":"+update_sha).encode()).hexdigest()[:32]
    with closing(sqlite3.connect(dbfile,timeout=10)) as conn:
        os.chmod(dbfile,0o600)
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        exists=conn.execute("SELECT id FROM corrections WHERE id=?",(release_id,)).fetchone()
        if exists:
            raise CorrectionBlocked("correction already staged; inspect existing receipt")
        if conn.execute("SELECT 1 FROM corrections WHERE story_id=? AND status='STAGED_ONLY'",
                        (story_id,)).fetchone():
            raise CorrectionBlocked("previous correction awaiting verification")
        conn.execute("""INSERT INTO corrections
            (id,story_id,canonical_path,old_sha256,new_sha256,main_sha,
             editor_id,reason,status,prepared_at)
             VALUES(?,?,?,?,?,?,?,?,'STAGED_ONLY',?)""",
             (release_id,story_id,path,sha256(old_bytes).hexdigest(),
              update_sha,main_sha,approved["reviewer_id"],reason,stamp))
        conn.commit()
    artifact=root/(release_id+".html")
    artifact.write_bytes(new_bytes)
    os.chmod(artifact,0o600)
    return {"state":"STAGED_ONLY","release_id":release_id,"url_path":path,
            "original_html_sha256":sha256(old_bytes).hexdigest(),
            "corrected_html_sha256":update_sha,
            "editor_id":approved["reviewer_id"],
            "article_file":str(artifact),
            "changed_file_count":1,
            "published":False,
            "needs_explicit_production_review":True}