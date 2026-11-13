#!/usr/bin/env python3
"""Single-actor publication preflight; no network writes or unattended activation.

One only path may prepare the next release. It requires a durable quota,
clean pinned remote main, private source-backed editor approval and a
publisher lock. If any piece is unknown, it stops without publishing.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
import fcntl
import hashlib
import json
import os
import sqlite3

from production_quota import (ProductionLedger, QuotaBlocked,
                              inspect_current_main,verified_editorial_record)

BLOCKED_TERMS=(
  "arrested","arrest","charged with","accused of","suspect","fatal","death",
  "shooting","sexual","child abuse","lawsuit","convicted","fraud allegations",
  "domestic violence","suicide","injured","evacuation ordered")
SITE_HOSTS={"www.greenevilletn.gov","www.greenecountytngov.com",
            "greenevilletn.gov","greenecountytngov.com"}
MAX_ACTIVE_RELEASES=1

class PublicationBlocked(ValueError):pass

def activate_enabled(private_root:Path)->bool:
    """Separate owner authorization is required; no file is created here."""
    p=Path(private_root)/"publication-activation.json"
    if not p.is_file() or p.is_symlink() or p.stat().st_mode&0o077:
        return False
    try:x=json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError,OSError):return False
    return (x.get("enabled") is True and
            x.get("explicit_owner_activation")=="separately-approved" and
            x.get("daily_new_cap")==4 and
            x.get("exclusive_publisher")=="ds-blog-production-single-writer" and
            x.get("correction_policy")=="source-bound-with-history")

@contextmanager
def publisher_lock(private_root:Path):
    """Single-host lock; protects the full publish/verify/mail lifecycle."""
    root=Path(private_root)
    if root.is_symlink() or ".git" in root.parts:
        raise PublicationBlocked("unsafe private publisher state")
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(root,0o700)
    path=root/"exclusive-publisher.lock"
    if path.is_symlink():raise PublicationBlocked("publisher lock symlink forbidden")
    with open(path,"a+b") as f:
        os.chmod(path,0o600)
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise PublicationBlocked("another publishing actor holds exclusive lock") from exc
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)

def source_policy(story:dict, now:datetime, *, strict_freshness:bool=True)->dict:
    if not isinstance(story,dict) or not story.get("sources"):
        raise PublicationBlocked("missing original source references")
    if story.get("sensitive") is not False or story.get("publication_status")!="draft":
        raise PublicationBlocked("sensitive or pre-approved draft rejected")
    if len(story["sources"])<1 or len(story["sources"])>8:
        raise PublicationBlocked("source count out of bounds")
    for s in story["sources"]:
        parsed=urlsplit(s.get("url",""))
        if (parsed.scheme!="https" or parsed.hostname not in SITE_HOSTS
            or parsed.username or parsed.password or parsed.fragment
            or s.get("kind")!="official"):
            raise PublicationBlocked("new source requires explicit scope and rights review")
    if story.get("verification_status") not in ("confirmed","proposed","reported"):
        raise PublicationBlocked("verification status not recognized")
    content=" ".join([story.get("title",""),story.get("summary","")]
       +[p for section in story.get("sections",[]) for p in section.get("paragraphs",[])])
    low=content.casefold()
    if any(x in low for x in BLOCKED_TERMS):
        raise PublicationBlocked("high-risk keyword: requires explicit owner review")
    if len(content)<240:
        raise PublicationBlocked("substantive original summary is required")
    if strict_freshness:
        try:when=datetime.fromisoformat(story["updated_at"])
        except (KeyError,ValueError):raise PublicationBlocked("article modified timestamp missing")
        if when.tzinfo is None or when>now+timedelta(minutes=5) or now-when>timedelta(days=10):
            raise PublicationBlocked("stale/future article timestamp; recheck sources")
    return {"low_risk_screen_passed":True,"sources":len(story["sources"]),
            "automated_policy_is_not_full_fact_check":True}

def preflight(story_id:str, *, ledger:ProductionLedger, main:Path, remote_sha:str,
              editorial_db:Path, source_db:Path, at:datetime)->dict:
    """Pure read-only approval/quota/source checks; no quota reservation."""
    if at.tzinfo is None:raise PublicationBlocked("timezone required")
    try:
        sha,live_paths=inspect_current_main(main,remote_sha)
        approved=verified_editorial_record(editorial_db,source_db,story_id)
    except (QuotaBlocked,sqlite3.Error) as exc:
        raise PublicationBlocked("origin/review/evidence verification failed") from exc
    story=approved["story"]
    result=source_policy(story,at)
    path="greeneville/"+story["slug"]+".html"
    if path in live_paths:
        raise PublicationBlocked("existing public article; update via correction workflow only")
    state=ledger.inspect(at)
    if state["verified_main_sha"]!=sha:
        raise PublicationBlocked("unrecognized production main SHA; reconcile before publishing")
    if state["remaining_slots"]<=0:
        raise PublicationBlocked("four-new-post Eastern daily quota exhausted")
    active=[r for r in state["intents"]
            if r["status"] in ("reserved","prepared","publishing","uncertain")]
    if active:
        raise PublicationBlocked("in-flight or uncertain release must be reconciled first")
    if any(r["story_id"]==story_id or r["slug"]==story["slug"] for r in state["intents"]):
        raise PublicationBlocked("previously attempted story; no duplicate release")
    return {
        "state":"APPROVED_FOR_ONE_GUARDED_PREPARATION_ONLY",
        "story_id":story_id,"current_main_sha":sha,
        "proposed_url":"https://dsdigitaldesigns.org/"+path,
        "remaining_new_slots":state["remaining_slots"],
        "independent_reviewer":approved["reviewer_id"],
        "payload_sha256":approved["payload_sha"],
        "source_policy":result,
        "no_publication_performed":True,
        "unattended_activation":False
    }

def cli():
    import argparse
    from pilot_preflight import (verified_remote_main,MAIN,EDITORIAL,COLLECTOR)
    from production_quota import DEFAULT_ROOT
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("status","preflight"))
    p.add_argument("--story-id")
    args=p.parse_args()
    ledger=ProductionLedger(DEFAULT_ROOT)
    if args.action=="status":
        state=ledger.inspect(datetime.now(timezone.utc))
        state["unattended_publisher_enabled"]=activate_enabled(DEFAULT_ROOT)
        state["no_production_changes"]=True
        print(json.dumps(state,indent=2))
        return
    if not args.story_id:p.error("--story-id required")
    # Only read-only preflight; publisher activation is a separate future step.
    with publisher_lock(DEFAULT_ROOT):
        print(json.dumps(preflight(args.story_id,ledger=ledger,main=MAIN,
                  remote_sha=verified_remote_main(),editorial_db=EDITORIAL,
                  source_db=COLLECTOR,at=datetime.now(timezone.utc)),indent=2))

if __name__=="__main__":
    import sys
    try:cli()
    except (PublicationBlocked,QuotaBlocked,OSError,ValueError,sqlite3.Error) as e:
        print("PUBLISHING_DISABLED:",str(e),file=sys.stderr);sys.exit(2)