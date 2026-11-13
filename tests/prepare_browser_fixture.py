#!/usr/bin/env python3
"""Create a temporary FICTIONAL pipeline output for local-browser verification only."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from release_coordinator import Store
sys.path.insert(0,str(ROOT/"tests"))
from test_release_coordinator import example, RAW, SOURCE_URL, T0

def main():
    tmp=Path(sys.argv[1]).resolve()
    tmp.mkdir(parents=True,exist_ok=True)
    col=tmp/"fake-collector.sqlite3"
    raw=RAW.encode("utf-8")
    digest=sha256(raw).hexdigest()
    with sqlite3.connect(col) as db:
        db.executescript("""
        CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT);
        CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,
          raw_body BLOB,sha256 TEXT,source_url TEXT);
        """)
        db.execute("INSERT INTO documents VALUES(1,'test-official')")
        db.execute("INSERT INTO revisions VALUES(1,1,?,?,?)",(raw,digest,SOURCE_URL))
    store=Store(tmp/"private")
    draft=example(1,digest)
    store.submit(draft,"writer-task",T0)
    store.review(draft["id"],"editor-task","approved",col,T0,
                 "Independently matched synthetic source excerpt and proposal label.")
    rel=store.reserve(draft["id"],T0)
    stage=store.stage(rel["release_id"],T0)
    verification=store.simulate(rel["release_id"],T0)
    print(json.dumps({"stage":stage,"verification":verification,"status":store.status(T0)}))

if __name__=="__main__":
    main()