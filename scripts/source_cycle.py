#!/usr/bin/env python3
"""Checkpoint 008: fail-closed, bounded official-source poller.

Default is plan/read-only. Live collection requires BOTH --execute and a
separately owner-created activation.json; this checkpoint does not create one.
Never publishes raw content, pushes GitHub, or sends an email.
"""
from __future__ import annotations
from contextlib import closing, contextmanager
from datetime import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from zoneinfo import ZoneInfo

TZ=ZoneInfo("America/New_York")
COLLECTOR=Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/collector.py")
REGISTRY=Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/source-registry.json")
COLLECTOR_DB=Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/state/local-information.sqlite3")
PRIVATE_ROOT=Path("/var/lib/kali-ai-remote/ds-blog-continuous-private-008")
GROUPS=(("town-agendas","town-events","town-events-program"),
        ("county-notices","county-purchasing"))
MAX_DOCS_PER_RUN=3
MAX_DB_GROWTH_PER_DAY=24*1024*1024
MIN_FREE_BYTES=1024*1024*1024

SCHEMA="""
CREATE TABLE IF NOT EXISTS collection_runs(
  slot TEXT PRIMARY KEY, local_date TEXT NOT NULL, source_ids TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('reserved','complete','failed')),
  began_at TEXT NOT NULL, completed_at TEXT,
  added INTEGER NOT NULL DEFAULT 0, duplicates INTEGER NOT NULL DEFAULT 0,
  before_bytes INTEGER NOT NULL DEFAULT 0, after_bytes INTEGER NOT NULL DEFAULT 0,
  error TEXT);
CREATE INDEX IF NOT EXISTS idx_collection_date ON collection_runs(local_date,status);
"""

class CollectionBlocked(ValueError):pass

def read_registry(registry_path=REGISTRY):
    p=Path(registry_path)
    if not p.is_file() or p.is_symlink():raise CollectionBlocked("approved source registry unavailable")
    obj=json.loads(p.read_text(encoding="utf-8"))
    if obj.get("schema_version")!=1 or len(obj.get("sources",[]))!=5:
        raise CollectionBlocked("source registry has changed; human scope review required")
    ids=[r["id"] for r in obj["sources"]]
    if set(ids)!={x for group in GROUPS for x in group}:
        raise CollectionBlocked("source allowlist changed; stop collection")
    for s in obj["sources"]:
        from urllib.parse import urlsplit
        url=urlsplit(s["url"])
        if (not s.get("fetch_enabled") or not s.get("index_only")
            or url.scheme!="https" or url.hostname not in
               {"www.greenevilletn.gov","www.greenecountytngov.com"}
            or url.username or url.password or url.query or url.fragment):
            raise CollectionBlocked("unapproved source endpoint or collection scope")
    return obj

def plan(at:datetime, registry_path=REGISTRY) -> dict:
    if at.tzinfo is None:raise CollectionBlocked("timezone-aware time required")
    registry=read_registry(registry_path)
    local=at.astimezone(TZ)
    group=(local.hour//2)%2
    ids=GROUPS[group]
    # Offset/fold distinguished during DST transitions.
    slot=f"{local.date().isoformat()}:{local.hour//2:02d}:{local.utcoffset().total_seconds():+g}"
    return {"slot":slot,"local_date":str(local.date()),"source_ids":ids,
            "official_source_count":len(registry["sources"]),
            "mode":"PLAN_ONLY","new_schedules_activated":False,
            "publication_enabled":False}

@contextmanager
def exclusive_lock(state_root:Path):
    root=Path(state_root)
    if root.is_symlink() or ".git" in root.parts:
        raise CollectionBlocked("untrusted private state root")
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    lock_path=root/"collection.lock"
    if lock_path.is_symlink():raise CollectionBlocked("lock symlink rejected")
    with open(lock_path,"a+b") as lock:
        os.chmod(lock_path,0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise CollectionBlocked("collector already running") from exc
        try:yield root
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

def collector_adapter(ids,collector_path=COLLECTOR,db_path=COLLECTOR_DB):
    if not Path(collector_path).is_file() or Path(collector_path).is_symlink():
        raise CollectionBlocked("original collector unavailable")
    # Imports the existing audited collector code, never replaces original.
    spec=importlib.util.spec_from_file_location("ds_private_source_collector",collector_path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module.one_shot_live(list(ids),Path(db_path))

def execute_cycle(at:datetime, state_root:Path, registry_path:Path,
                  source_db:Path, adapter, *, owner_enabled:bool=False) -> dict:
    if not owner_enabled:raise CollectionBlocked("owner has not activated live source collection")
    scope=plan(at,registry_path)
    root=Path(state_root)
    src=Path(source_db)
    if not src.is_file() or src.is_symlink():
        raise CollectionBlocked("collector DB absent or symlinked")
    if shutil.disk_usage(str(src.parent)).free<MIN_FREE_BYTES:
        raise CollectionBlocked("low free disk space; collector stopped")
    now=at.isoformat(timespec="seconds")
    before=src.stat().st_size
    with exclusive_lock(root):
        dbpath=root/"collection-receipts.sqlite3"
        if dbpath.is_symlink():raise CollectionBlocked("receipt DB symlink rejected")
        with closing(sqlite3.connect(dbpath,timeout=10)) as conn:
            os.chmod(dbpath,0o600)
            conn.executescript(SCHEMA)
            conn.execute("BEGIN IMMEDIATE")
            prev=conn.execute("SELECT status FROM collection_runs WHERE slot=?",(scope["slot"],)).fetchone()
            if prev:raise CollectionBlocked("this official-source slot was already attempted: "+prev[0])
            used=conn.execute("""SELECT COALESCE(SUM(MAX(after_bytes-before_bytes,0)),0) FROM collection_runs
                       WHERE local_date=?""",(scope["local_date"],)).fetchone()[0]
            if used>=MAX_DB_GROWTH_PER_DAY:
                raise CollectionBlocked("private daily source-storage budget exhausted")
            conn.execute("""INSERT INTO collection_runs(slot,local_date,source_ids,status,began_at,before_bytes,after_bytes)
                VALUES(?,?,?,'reserved',?,?,?)""",
                (scope["slot"],scope["local_date"],json.dumps(scope["source_ids"]),now,before,before))
            conn.commit()
            try:
                result=adapter(tuple(scope["source_ids"]))
                if not isinstance(result,dict):
                    raise CollectionBlocked("collector did not return a verifiable receipt")
                after=src.stat().st_size
                if "added_revisions" not in result or "duplicates" not in result:
                    raise CollectionBlocked("missing original collector receipt fields")
                added=int(result["added_revisions"])
                duplicates=int(result["duplicates"])
                if added<0 or duplicates<0 or added+duplicates>MAX_DOCS_PER_RUN:
                    raise CollectionBlocked("collector receipt out of range")
                conn.execute("""UPDATE collection_runs SET status='complete',completed_at=?,
                    added=?,duplicates=?,after_bytes=? WHERE slot=?""",
                    (at.isoformat(timespec="seconds"),added,duplicates,after,scope["slot"]))
                conn.commit()
                return {"slot":scope["slot"],"status":"complete","added":added,
                        "duplicates":duplicates,"source_ids":scope["source_ids"],
                        "live_site_modified":False,"email_sent":False}
            except Exception as exc:
                # Reserve failed slot; no retries without owner review.
                conn.execute("""UPDATE collection_runs SET status='failed',completed_at=?,error=?,
                    after_bytes=? WHERE slot=?""",
                    (at.isoformat(timespec="seconds"),type(exc).__name__,src.stat().st_size,scope["slot"]))
                conn.commit()
                raise

def activation_ok(state_root:Path,registry_path:Path) -> bool:
    root=Path(state_root)
    key=root/"activation.json"
    if not key.is_file() or key.is_symlink() or key.stat().st_mode & 0o077:
        return False
    x=json.loads(key.read_text())
    return (x.get("enabled") is True and
            x.get("source_registry_sha256")==hashlib.sha256(Path(registry_path).read_bytes()).hexdigest()
            and x.get("explicit_owner_activation")=="separately-approved")

def cli():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["plan","run"])
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    now=datetime.now(TZ)
    if args.action=="plan":
        print(json.dumps(plan(now),indent=2))
        return
    if not args.execute or not activation_ok(PRIVATE_ROOT,REGISTRY):
        raise CollectionBlocked("live collection not authorized: missing owner activation marker")
    print(json.dumps(execute_cycle(now,PRIVATE_ROOT,REGISTRY,COLLECTOR_DB,collector_adapter,
                                   owner_enabled=True),indent=2))

if __name__=="__main__":
    try:cli()
    except (CollectionBlocked,OSError,ValueError,sqlite3.Error) as exc:
        print("COLLECTION_NOT_ACTIVATED:",str(exc),file=sys.stderr);sys.exit(2)