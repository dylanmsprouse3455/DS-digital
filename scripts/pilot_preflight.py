#!/usr/bin/env python3
"""Read-only/publication-gated CLI for the isolated DS Digital Designs pilot.

This tool cannot publish, deploy, email, enable schedules, or change GitHub.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from production_quota import (
    DEFAULT_ROOT, ProductionLedger, QuotaBlocked, inspect_current_main
)

MAIN = Path("/var/lib/kali-ai-remote/ds-blog-main-baseline-c005")
EDITORIAL = Path("/var/lib/kali-ai-remote/ds-local-publishing-private-004/simulation.sqlite3")
COLLECTOR = Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/state/local-information.sqlite3")
REMOTE = "https://github.com/dylanmsprouse3455/DS-digital.git"

def verified_remote_main() -> str:
    result=subprocess.run(["git","ls-remote",REMOTE,"refs/heads/main"],
                          capture_output=True,text=True,timeout=15)
    if result.returncode or not result.stdout.strip():
        raise QuotaBlocked("unable to read authoritative remote GitHub main")
    return result.stdout.strip().split()[0]

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["preflight","initialize-baseline","status","reserve-approved"])
    p.add_argument("--state-dir",type=Path,default=DEFAULT_ROOT)
    p.add_argument("--main-checkout",type=Path,default=MAIN)
    p.add_argument("--editorial-db",type=Path,default=EDITORIAL)
    p.add_argument("--collector-db",type=Path,default=COLLECTOR)
    p.add_argument("--story-id")
    args=p.parse_args()
    now=datetime.now(timezone.utc)
    ledger=ProductionLedger(args.state_dir)
    if args.action=="status":
        result=ledger.inspect(now)
    elif args.action=="preflight":
        remote=verified_remote_main()
        sha,articles=inspect_current_main(args.main_checkout,remote)
        result={"mode":"READ_ONLY_PUBLICATION_PREFLIGHT","remote_main_sha":remote,
                "local_main_matches_remote":True,"existing_local_articles":len(articles),
                "private_quota":ledger.inspect(now),
                "public_site_modified":False}
    elif args.action=="initialize-baseline":
        remote=verified_remote_main()
        result=ledger.initialize_verified_baseline(args.main_checkout,remote,now)
        result["daily_quota"]=ledger.inspect(now)
    else:
        if not args.story_id:p.error("--story-id required")
        remote=verified_remote_main()
        result=ledger.reserve_approved(args.story_id,args.main_checkout,remote,
                                       args.editorial_db,args.collector_db,now)
        result["public_release_performed"]=False
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__":
    try:main()
    except (QuotaBlocked,OSError,ValueError,KeyError) as exc:
        print("PILOT_GATE_BLOCKED:",str(exc),file=sys.stderr)
        sys.exit(2)