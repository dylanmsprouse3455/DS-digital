"""Read-only integrity checks for the actual, private November 2026 pilot draft.

Tests skip outside authorized connected Kali; never export raw official text.
"""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from release_coordinator import require_source_evidence, public_story_payload

PRIVATE=Path("/var/lib/kali-ai-remote/ds-blog-pilot-evidence-006")
DRAFT=PRIVATE/"historic-zoning-meeting-2026-11-17.draft.json"
DB=PRIVATE/"official-sources.sqlite3"
EDITOR=PRIVATE/"editorial-queue/simulation.sqlite3"

class RealPilotEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(p.is_file() for p in (DRAFT,DB,EDITOR)):
            raise unittest.SkipTest("private real source capture is not available in this environment")
        cls.story=json.loads(DRAFT.read_text())

    def test_real_public_town_sources_only(self):
        self.assertEqual(len(self.story["sources"]),2)
        self.assertEqual({s["url"] for s in self.story["sources"]},{
          "https://www.greenevilletn.gov/events",
          "https://www.greenevilletn.gov/page/historic-zoning-commission"})
        self.assertTrue(all(s["kind"]=="official" for s in self.story["sources"]))

    def test_original_captured_hashes_match(self):
        with closing(sqlite3.connect(f"file:{DB}?mode=ro",uri=True)) as db:
            rows=db.execute("SELECT sha256,raw_body FROM revisions").fetchall()
        self.assertEqual(len(rows),2)
        for h,body in rows:
            self.assertEqual(sha256(body).hexdigest(),h)

    def test_original_verbatim_evidence_quotes_all_match(self):
        require_source_evidence(self.story,DB)

    def test_draft_is_not_publisher_approved(self):
        self.assertEqual(self.story["publication_status"],"draft")
        self.assertFalse(self.story["sensitive"])
        with closing(sqlite3.connect(f"file:{EDITOR}?mode=ro",uri=True)) as db:
            # The pilot's separate manual editorial pass may now have run.
            # A review must never be attributed to the original writer.
            reviewers=db.execute("SELECT reviewer_id,verdict FROM reviews").fetchall()
            self.assertFalse(any(r[0]=="ds-local-blog-writer-pilot" for r in reviewers))
            self.assertTrue(all(r[1] in ("approved","rejected") for r in reviewers))
            # This is a private simulation queue, NOT the production receipt.
            states=db.execute("SELECT DISTINCT mode FROM releases").fetchall()
            self.assertTrue(all(x[0]=="simulation" for x in states))

    def test_calendar_date_and_no_decision_claimed(self):
        self.assertIn("Nov. 17",self.story["title"])
        full=" ".join(p for section in self.story["sections"] for p in section["paragraphs"])
        self.assertIn("not establish that the request has been approved or denied",full)
        self.assertTrue(any(x in self.story["title"].lower() for x in ("scheduled","schedules")))
        public_story_payload(self.story)

    def test_private_file_permissions(self):
        for p in (DRAFT,DB,EDITOR):
            self.assertEqual(p.stat().st_mode & 0o777,0o600,p.name)

if __name__=="__main__":
    unittest.main(verbosity=2)