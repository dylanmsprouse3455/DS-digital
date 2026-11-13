#!/usr/bin/env python3
"""Prepare a REAL, evidence-linked private editorial draft for the pilot.

NO editor approval, no quota reservation, no publication, no Gmail.
Requires two exact immutable captures of the Town of Greeneville's pages.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from release_coordinator import Store, require_source_evidence, public_story_payload

PRIVATE=Path("/var/lib/kali-ai-remote/ds-blog-pilot-evidence-006")
DB=PRIVATE/"official-sources.sqlite3"
DRAFT=PRIVATE/"historic-zoning-meeting-2026-11-17.draft.json"
EDITOR=PRIVATE/"editorial-queue"

REQUIRED_EVENT_QUOTES=[
    "The item will be on the Nov. 17 meeting agenda.",
    "Historic Zoning Commission Meeting",
    "Meets in the G. Thomas Love Boardroom at GEA"
]
REQUIRED_BOARD_QUOTES=[
    "The Greeneville Historic Zoning Commission meets at 8:30 a.m.",
    "first and third Tuesdays",
    "110 N College Street"
]

def prepare():
    meta=json.loads((PRIVATE/"capture-metadata.json").read_text(encoding="utf-8"))
    assert meta["schema_version"]==1 and len(meta["sources"])==2
    by_id={s["id"]:s for s in meta["sources"]}
    assert set(by_id)=={"town-events","historic-zoning-commission"}
    raws={}
    for sid,record in by_id.items():
        file=PRIVATE/(sid+".txt")
        data=file.read_bytes()
        assert file.stat().st_mode & 0o777 == 0o600
        assert sha256(data).hexdigest()==record["sha256"]
        assert len(data)==record["raw_bytes"] and record["http_status"]==200
        assert record["url"].startswith("https://www.greenevilletn.gov/")
        raws[sid]=data
    text1=raws["town-events"].decode("utf-8")
    text2=raws["historic-zoning-commission"].decode("utf-8")
    for q in REQUIRED_EVENT_QUOTES:assert q in text1
    for q in REQUIRED_BOARD_QUOTES:assert q in text2
    # Verify the date, start and end *together* with the named meeting.
    import re
    assert re.search(r"NOV\s+17\s+8:30 AM\s+9:30 AM\s+Historic Zoning Commission Meeting",text1)
    assert "2026" in text1

    if DB.exists() or DRAFT.exists():
        raise FileExistsError("Pilot evidence DB/draft already prepared; no overwrite allowed")
    with closing(sqlite3.connect(DB)) as db:
        db.executescript("""
        CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT NOT NULL,document_key TEXT NOT NULL);
        CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL,
          raw_body BLOB NOT NULL,sha256 TEXT NOT NULL,source_url TEXT NOT NULL,
          observed_at TEXT NOT NULL,source_mode TEXT NOT NULL);
        """)
        for index,sid in enumerate(("town-events","historic-zoning-commission"),start=1):
            record=by_id[sid]
            db.execute("INSERT INTO documents VALUES(?,?,?)",
                (index,sid,"rendered-public-page-2026-11-12"))
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?)",
                (index,index,raws[sid],record["sha256"],record["url"],record["captured_at"],
                 record["mode"]))
        db.commit()
    DB.chmod(0o600)

    now=datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    story={
      "id":"greeneville-historic-zoning-commission-2026-11-17",
      "slug":"greeneville-historic-zoning-commission-november-17-2026",
      "title":"Greeneville schedules Nov. 17 Historic Zoning Commission meeting; North Main Street item expected",
      "summary":"Town records list a Nov. 17 meeting at Greeneville Energy Authority and say a request involving 300 N. Main Street is expected on the agenda. No decision has been reported.",
      "location":"Greeneville, TN",
      "category":"government",
      "verification_status":"confirmed",
      "published_at":now,
      "updated_at":now,
      "sources":[
        {"title":"Town of Greeneville official events calendar",
         "url":by_id["town-events"]["url"],"kind":"official"},
        {"title":"Town of Greeneville Historic Zoning Commission information",
         "url":by_id["historic-zoning-commission"]["url"],"kind":"official"}
      ],
      "sections":[
        {"heading":"When and where the meeting is listed",
         "paragraphs":[
          "The Town of Greeneville's events calendar lists the Historic Zoning Commission meeting for Tuesday, November 17, 2026, from 8:30 to 9:30 a.m. at Greeneville Energy Authority, 110 N. College Street.",
          "The town's separate Historic Zoning Commission page identifies the G. Thomas Love Board Room at Greeneville Energy Authority as the commission's regular meeting location. The commission normally meets on the first and third Tuesdays at 8:30 a.m."
         ]},
        {"heading":"North Main Street request is expected for review",
         "paragraphs":[
          "The town calendar describes a November 10 site visit by commission members at 300 N. Main Street to examine the back of a house in connection with a request for changes to the structure.",
          "The town specifically states that no formal votes were to occur during that site visit and that the item would appear on the November 17 meeting agenda. This does not establish that the request has been approved or denied."
         ]},
        {"heading":"Where to confirm the latest details",
         "paragraphs":[
          "Residents can consult the town's official events calendar and Historic Zoning Commission information page for meeting details. The listed schedule is subject to change.",
          "This article reports the meeting listing and anticipated agenda item, not an outcome. Any vote or decision should be checked against official minutes or a subsequent town notice."
         ]}
      ],
      "sensitive":False,
      "publication_status":"draft",
      "evidence_refs":[
        {"revision_id":1,"sha256":by_id["town-events"]["sha256"],
         "quote":"The item will be on the Nov. 17 meeting agenda."},
        {"revision_id":1,"sha256":by_id["town-events"]["sha256"],
         "quote":"Historic Zoning Commission Meeting"},
        {"revision_id":2,"sha256":by_id["historic-zoning-commission"]["sha256"],
         "quote":"The Greeneville Historic Zoning Commission meets at 8:30 a.m."}
      ]
    }
    public_story_payload(story)
    require_source_evidence(story,DB)
    DRAFT.write_text(json.dumps(story,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    DRAFT.chmod(0o600)
    editor=Store(EDITOR)
    sha=editor.submit(story,"ds-local-blog-writer-pilot",datetime.now(ZoneInfo("America/New_York")))
    report={
        "state":"DRAFT_AWAITING_INDEPENDENT_EDITOR",
        "story_id":story["id"],"title":story["title"],"idempotence_sha":sha,
        "editorial_queue":editor.queue(),
        "evidence_sources":len(story["sources"]),
        "evidence_refs":len(story["evidence_refs"]),
        "live_publication":False,"actual_email_sent":False,
        "pilot_evidence_db":str(DB),"pilot_draft":str(DRAFT),
        "editorial_store":str(editor.path)
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":
    prepare()