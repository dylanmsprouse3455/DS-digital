#!/usr/bin/env python3
"""Safe CLI for the private DS Local Intelligence Checkpoint 004 staging pipeline.

All mutable commands operate only in simulation/private staging. There is
intentionally NO deploy-to-main, public publish, schedule, or send-email command.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from collector_packets import packets
from release_coordinator import (
    DEFAULT_COLLECTOR, DEFAULT_PRIVATE, GateError, Store, read_only_collector
)


def main(argv=None) -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=[
        "collector-status","collector-packets","status","queue","submit-draft","review","reserve",
        "stage","simulate"
    ])
    p.add_argument("--private-root",type=Path,default=DEFAULT_PRIVATE)
    p.add_argument("--collector-db",type=Path,default=DEFAULT_COLLECTOR)
    p.add_argument("--after-revision",type=int,default=0)
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--file",type=Path)
    p.add_argument("--story-id")
    p.add_argument("--release-id")
    p.add_argument("--writer-id")
    p.add_argument("--reviewer-id")
    p.add_argument("--decision",choices=["approved","rejected"])
    p.add_argument("--note")
    args=p.parse_args(argv)
    now=datetime.now(timezone.utc)
    if args.command=="collector-status":
        out=read_only_collector(args.collector_db)
    elif args.command=="collector-packets":
        out=packets(args.collector_db,after_revision=args.after_revision,limit=args.limit)
    else:
        store=Store(args.private_root)
        if args.command=="status":
            out=store.status(now)
        elif args.command=="queue":
            out=store.queue()
        elif args.command=="submit-draft":
            if not args.file or not args.writer_id:
                p.error("--file and --writer-id required")
            if args.file.is_symlink() or args.file.stat().st_size>75_000:
                raise GateError("draft file must be a small ordinary non-symlink file")
            draft=json.loads(args.file.read_text(encoding="utf-8"))
            out={"story_id":draft["id"],"content_sha256":store.submit(draft,args.writer_id,now),"publication":"NOT_ALLOWED"}
        elif args.command=="review":
            if not (args.story_id and args.reviewer_id and args.decision and args.note):
                p.error("--story-id, --reviewer-id, --decision and --note required")
            store.review(args.story_id,args.reviewer_id,args.decision,args.collector_db,now,args.note)
            out={"story_id":args.story_id,"verdict":args.decision,"approved_for_public_deploy":False}
        elif args.command=="reserve":
            if not args.story_id:p.error("--story-id required")
            out=store.reserve(args.story_id,now)
        elif args.command=="stage":
            if not args.release_id:p.error("--release-id required")
            out=store.stage(args.release_id,now)
        elif args.command=="simulate":
            if not args.release_id:p.error("--release-id required")
            out=store.simulate(args.release_id,now)
        else:
            raise GateError("unsupported command")
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=="__main__":
    try:main()
    except (GateError,OSError,ValueError,KeyError) as e:
        print("STAGING_GATE_BLOCKED:",str(e),file=sys.stderr)
        sys.exit(2)