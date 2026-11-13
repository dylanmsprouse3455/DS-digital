#!/usr/bin/env python3
"""One-time shared-Kali handoff probe; never publishes, crawls, or emails.

The writer must create a private receipt in its own *scheduled* run. The
editor must read it in its separately scheduled run. Tool-driven manual tests
are not proof of unattended automation: correlate with task run logs.
"""
from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys

PROBE_ID="ds-blog-shared-kali-008-20261112"
ROOT=Path("/var/lib/kali-ai-remote/ds-blog-continuous-private-008/handoff-probe")
COLLECTOR=Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/state/local-information.sqlite3")
PRODUCTION=Path("/var/lib/kali-ai-remote/ds-blog-production-pilot-state-006/publication-ledger.sqlite3")

class ProbeBlocked(ValueError):pass

def now()->str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def read_count(db_path:Path, table:str)->int:
    if table not in ("revisions","release_intents"):raise ProbeBlocked("invalid read-only probe table")
    p=Path(db_path)
    if not p.is_file() or p.is_symlink():raise ProbeBlocked("source data unavailable or symlink")
    with closing(sqlite3.connect("file:"+str(p.resolve())+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

def write_once(path:Path, payload:dict) -> bool:
    if path.is_symlink():raise ProbeBlocked("receipt symlink rejected")
    content=(json.dumps(payload,sort_keys=True,ensure_ascii=False)+"\n").encode()
    try:
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        existing=json.loads(path.read_text(encoding="utf-8"))
        if existing.get("probe_id")!=PROBE_ID:
            raise ProbeBlocked("existing receipt from another checkpoint")
        return False
    with os.fdopen(fd,"wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    return True

def run(role:str,state_root:Path=ROOT,collector_db:Path=COLLECTOR,
        production_db:Path=PRODUCTION)->dict:
    if role not in ("writer","editor","status"):
        raise ProbeBlocked("invalid probe role")
    root=Path(state_root)
    if root.is_symlink() or ".git" in root.parts:
        raise ProbeBlocked("invalid private probe root")
    if role=="status" and not root.is_dir():
        return {"probe_id":PROBE_ID,"writer_recorded":False,"editor_acknowledged":False,
                "unattended_execution_verified":False}
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    writer=root/"writer-receipt.json"
    editor=root/"editor-ack.json"
    if role=="writer":
        n=read_count(collector_db,"revisions")
        payload={"probe_id":PROBE_ID,"role":"writer","ran_at_utc":now(),
                 "collector_revisions_read_only":n,
                 "source_db_sha256":sha256(str(Path(collector_db).resolve()).encode()).hexdigest(),
                 "publication_performed":False}
        created=write_once(writer,payload)
        return {"probe_id":PROBE_ID,"role":"writer","recorded":True,
                "created":created,"collector_revisions":n,
                "unattended_execution_verified":False}
    if role=="editor":
        if not writer.is_file() or writer.is_symlink():
            raise ProbeBlocked("writer's separate scheduled receipt not present")
        raw=writer.read_bytes()
        original=json.loads(raw)
        if original.get("probe_id")!=PROBE_ID or original.get("role")!="writer":
            raise ProbeBlocked("unrecognized writer receipt")
        writer_sha=sha256(raw).hexdigest()
        n=read_count(production_db,"release_intents")
        payload={"probe_id":PROBE_ID,"role":"editor","ran_at_utc":now(),
                 "writer_receipt_sha256":writer_sha,
                 "production_release_count_read_only":n,
                 "publication_performed":False}
        created=write_once(editor,payload)
        return {"probe_id":PROBE_ID,"role":"editor","recorded":True,
                "created":created,"writer_receipt_hash_verified":True,
                "unattended_execution_verified":False}
    result={"probe_id":PROBE_ID,"writer_recorded":writer.is_file() and not writer.is_symlink(),
            "editor_acknowledged":editor.is_file() and not editor.is_symlink(),
            "unattended_execution_verified":False}
    if result["writer_recorded"] and result["editor_acknowledged"]:
        w=writer.read_bytes()
        e=json.loads(editor.read_text())
        result["shared_workspace_handoff_valid"]=(
            e.get("probe_id")==PROBE_ID and e.get("role")=="editor"
            and e.get("writer_receipt_sha256")==sha256(w).hexdigest())
    return result

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("role",choices=["writer","editor","status"])
    args=p.parse_args()
    print(json.dumps(run(args.role),indent=2))

if __name__=="__main__":
    try:main()
    except (ProbeBlocked,ValueError,OSError,sqlite3.Error) as exc:
        print("UNATTENDED_ACCESS_PROBE_BLOCKED:",str(exc),file=sys.stderr);sys.exit(2)