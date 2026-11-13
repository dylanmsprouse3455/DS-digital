"""Checkpoint 004: source-bound review, concurrency quota, simulated release and email.

All sources and publication events in this test module are synthetic.
No network beyond an ephemeral loopback HTTP listener; no real email.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from release_coordinator import Store, GateError, read_only_collector, digest, DEFAULT_COLLECTOR, BUILD_ROOT

SOURCE_URL="https://www.greenevilletn.gov/o/tog/page/board-commission-agendas"
RAW="SYNTHETIC FIXTURE: a Proposed Example Trail Plan was discussed during a fictional test meeting. It is not a real event."
T0=datetime.fromisoformat("2026-11-12T18:00:00-05:00")
T1=datetime.fromisoformat("2026-11-13T18:00:00-05:00")


def example(i=1, raw_sha=None):
    return {
        "id":f"synthetic-trail-story-{i}",
        "slug":f"proposed-synthetic-test-trail-{i}",
        "title":f"Proposed Synthetic Example Trail Plan {i} — FICTIONAL TEST",
        "summary":"A controlled fictional demonstration for testing an editorial pipeline. Not a real local event.",
        "location":"Greeneville, TN",
        "category":"government",
        "verification_status":"proposed",
        "published_at":"2026-11-12T18:00:00-05:00",
        "updated_at":"2026-11-12T18:00:00-05:00",
        "sources":[{"title":"Synthetic municipal agenda fixture","url":SOURCE_URL,"kind":"official"}],
        "sections":[{"heading":"Fictional source evidence","paragraphs":[
            "This is a synthetic proposed activity only. It does not represent an actual town decision.",
            "The item is not approved or scheduled."
        ]}],
        "sensitive":False,
        "publication_status":"draft",
        "evidence_refs":[{"revision_id":1,"sha256":raw_sha,"quote":"Proposed Example Trail Plan was discussed"}],
    }


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="ds-integrated-test-")
        self.addCleanup(self.tmp.cleanup)
        self.parent=Path(self.tmp.name)
        self.collector=self.parent/"synthetic-sources.sqlite3"
        raw=RAW.encode()
        self.raw_hash=sha256(raw).hexdigest()
        with closing(sqlite3.connect(self.collector)) as c:
            c.executescript("""
            CREATE TABLE sources(id TEXT);
            CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT,document_key TEXT);
            CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,
                                   raw_body BLOB,sha256 TEXT,source_url TEXT);
            CREATE TABLE story_buckets(key TEXT,title TEXT,topic TEXT,updated_at TEXT,status TEXT);
            """)
            c.execute("INSERT INTO sources(id) VALUES('town-agendas')")
            c.execute("INSERT INTO documents(id,source_id,document_key) VALUES(1,'town-agendas','index')")
            c.execute("INSERT INTO revisions(id,document_id,raw_body,sha256,source_url) VALUES(1,1,?,?,?)",
                      (raw,self.raw_hash,SOURCE_URL))
            c.execute("INSERT INTO story_buckets VALUES('source:town-agendas:index','Synthetic Index','government','2026-11-12T00:00:00Z','unreviewed')")
            c.commit()
        self.store=Store(self.parent/"private-state")
        self.addCleanup(self._clean_builds)
        self.created_build_ids=set()

    def _clean_builds(self):
        for release_id in self.created_build_ids:
            shutil.rmtree(BUILD_ROOT / ("release-"+release_id),ignore_errors=True)

    def draft(self,i=1):
        return example(i,self.raw_hash)

    def put_approved(self,i=1,at=T0):
        story=self.draft(i)
        self.store.submit(story,"writer-task",at)
        self.store.review(story["id"],"editor-task","approved",self.collector,at,
                          "Independently checked the synthetic agenda and proposal status.")
        return story

    def reserve(self,story,at=T0):
        r=self.store.reserve(story["id"],at)
        self.created_build_ids.add(r["release_id"])
        return r

    def staged(self,i=1,at=T0):
        story=self.put_approved(i,at)
        r=self.reserve(story,at)
        return story,r,self.store.stage(r["release_id"],at)

    def test_collector_read_only_has_metadata_no_raw(self):
        data=read_only_collector(self.collector)
        self.assertEqual(data["revisions"],1)
        self.assertEqual(data["unreviewed_buckets"],1)
        self.assertNotIn("SYNTHETIC FIXTURE",json.dumps(data))
        self.assertFalse(data["candidates"][0]["editorial_approval"])

    def test_missing_collector_fails(self):
        with self.assertRaisesRegex(GateError,"unavailable"):
            read_only_collector(self.parent/"missing.sqlite3")

    def test_private_dir_perms(self):
        self.assertEqual(self.store.private_dir.stat().st_mode & 0o777,0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777,0o600)

    def test_refuses_private_state_inside_public_repo(self):
        with self.assertRaisesRegex(GateError,"public repository"):
            Store(ROOT/"build"/"must-not-create-private-state")

    def test_writer_cannot_mark_publication_approved(self):
        story=self.draft()
        story["publication_status"]="approved"
        with self.assertRaisesRegex(GateError,"cannot self-approve"):
            self.store.submit(story,"writer-task",T0)

    def test_writer_must_supply_source_references(self):
        story=self.draft();story["evidence_refs"]=[]
        with self.assertRaisesRegex(GateError,"unsubstantiated"):
            self.store.submit(story,"writer-task",T0)

    def test_submission_requires_valid_schema(self):
        story=self.draft();story["title"]="Misleading confirmed thing"
        with self.assertRaises(ValueError):
            self.store.submit(story,"writer-task",T0)

    def test_reject_same_identity_editor(self):
        s=self.draft();self.store.submit(s,"writer-task",T0)
        with self.assertRaisesRegex(GateError,"independent"):
            self.store.review(s["id"],"writer-task","approved",self.collector,T0,
                              "This is an independently checked story.")

    def test_approval_needs_verbatim_quote(self):
        s=self.draft();s["evidence_refs"][0]["quote"]="This quotation does not occur in any raw source"
        self.store.submit(s,"writer-task",T0)
        with self.assertRaisesRegex(GateError,"not found"):
            self.store.review(s["id"],"editor-task","approved",self.collector,T0,
                              "Synthetic evidence was cross-checked with primary source.")

    def test_approval_needs_matching_hash(self):
        s=self.draft();s["evidence_refs"][0]["sha256"]="0"*64
        self.store.submit(s,"writer-task",T0)
        with self.assertRaisesRegex(GateError,"mismatch"):
            self.store.review(s["id"],"editor-task","approved",self.collector,T0,
                              "Synthetic evidence was cross-checked with primary source.")

    def test_approval_needs_matching_source_url(self):
        s=self.draft();s["sources"][0]["url"]="https://example.org/other"
        self.store.submit(s,"writer-task",T0)
        with self.assertRaisesRegex(GateError,"not listed"):
            self.store.review(s["id"],"editor-task","approved",self.collector,T0,
                              "Synthetic evidence was cross-checked with primary source.")

    def test_sensitivity_escalation(self):
        s=self.draft();s["sensitive"]=True
        with self.assertRaises(ValueError):
            self.store.submit(s,"writer-task",T0)

    def test_rejected_draft_cannot_reserve(self):
        s=self.draft();self.store.submit(s,"writer-task",T0)
        self.store.review(s["id"],"editor-task","rejected",self.collector,T0,
                          "This synthetic record is unsuitable for publication.")
        with self.assertRaisesRegex(GateError,"approving review"):
            self.store.reserve(s["id"],T0)

    def test_unreviewed_draft_cannot_reserve(self):
        s=self.draft();self.store.submit(s,"writer-task",T0)
        with self.assertRaisesRegex(GateError,"approving review"):
            self.store.reserve(s["id"],T0)

    def test_new_draft_invalidates_old_review(self):
        s=self.put_approved()
        s["summary"]="Updated fictional summary, requiring a fresh editorial check before release."
        self.store.submit(s,"writer-task",T0)
        with self.assertRaisesRegex(GateError,"approving review"):
            self.store.reserve(s["id"],T0)

    def test_canonical_slug_cannot_change(self):
        s=self.put_approved()
        s["slug"]="altered-synthetic-slug"
        with self.assertRaisesRegex(GateError,"slug"):
            self.store.submit(s,"writer-task",T0)

    def test_reservation_idempotent(self):
        s=self.put_approved()
        first=self.reserve(s);second=self.reserve(s)
        self.assertEqual(first["release_id"],second["release_id"])
        self.assertEqual(self.store.status(T0)["new_posts_reserved_or_simulated"],1)

    def test_daily_max_four_fifth_blocked(self):
        for i in range(1,5):
            s=self.put_approved(i)
            self.reserve(s)
        s=self.put_approved(5)
        with self.assertRaisesRegex(GateError,"four new posts"):
            self.reserve(s)
        self.assertEqual(self.store.status(T0)["new_posts_remaining"],0)

    def test_quota_is_per_eastern_calendar_day(self):
        for i in range(1,5):
            s=self.put_approved(i)
            self.reserve(s,T0)
        s=self.put_approved(5,T1)
        self.assertEqual(self.reserve(s,T1)["local_date"],"2026-11-13")
        self.assertEqual(self.store.status(T1)["new_posts_reserved_or_simulated"],1)

    def test_utc_midnight_does_not_reset_eastern_quota(self):
        a=datetime.fromisoformat("2026-11-13T00:30:00+00:00") # Nov 12 in Eastern
        for i in range(1,5):
            s=self.put_approved(i)
            self.reserve(s,T0)
        s=self.put_approved(5)
        with self.assertRaisesRegex(GateError,"four new posts"):
            self.reserve(s,a)

    def test_concurrent_reservations_cannot_exceed_four(self):
        for i in range(1,9):
            self.put_approved(i)
        def reserve_one(i):
            try:
                r=self.store.reserve(f"synthetic-trail-story-{i}",T0)
                self.created_build_ids.add(r["release_id"])
                return "ok"
            except GateError: return "blocked"
        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes=list(executor.map(reserve_one,range(1,9)))
        self.assertEqual(outcomes.count("ok"),4)
        self.assertEqual(outcomes.count("blocked"),4)
        self.assertEqual(self.store.status(T0)["new_posts_reserved_or_simulated"],4)

    def test_stage_is_minimal_delta_bundle(self):
        story,rel,stage=self.staged()
        self.assertEqual(stage["file_count"],3)
        self.assertEqual(stage["paths"],["blog-v2.html","sitemap.xml",
                         "greeneville/proposed-synthetic-test-trail-1.html"])
        manifest=json.loads(Path(stage["bundle"]).read_text())
        self.assertEqual(manifest["mode"],"SIMULATION_ONLY")
        self.assertEqual(len(manifest["paths"]),3)
        self.assertNotIn("CNAME",stage["paths"])
        self.assertNotIn("index.html",stage["paths"])

    def test_stage_preserves_original_articles_and_sitemap(self):
        _,rel,stage=self.staged()
        base=Path(stage["preview_root"])
        blog=(base/"blog-v2.html").read_text()
        for name in ["post-high-converting-websites.html","post-small-business-security.html",
                     "post-site-speed-revenue.html"]:
            self.assertIn(f'href="{name}"',blog)
            self.assertTrue((base/name).is_file())
        sm=(base/"sitemap.xml").read_text()
        self.assertIn("greeneville/proposed-synthetic-test-trail-1.html",sm)

    def test_simulated_http_verification_and_no_email(self):
        _,rel,_=self.staged()
        result=self.store.simulate(rel["release_id"],T0)
        self.assertEqual(result["mock_http"],200)
        self.assertFalse(result["live_published"])
        self.assertEqual(result["email_status"],"NOT_SENT")
        self.assertTrue(result["proposed_public_url"].startswith("https://dsdigitaldesigns.org/"))
        with self.store._transaction() as c:
            row=c.execute("SELECT * FROM notification_previews").fetchone()
            self.assertIn("NOT SENT",row["body"])
            self.assertEqual(row["status"],"NOT_SENT")
            self.assertTrue(row["subject"].startswith("SIMULATION ONLY"))
        self.assertEqual(self.store.status(T0)["actual_emails_sent"],0)

    def test_simulation_replay_does_not_duplicate_email(self):
        _,rel,_=self.staged()
        first=self.store.simulate(rel["release_id"],T0)
        second=self.store.simulate(rel["release_id"],T0)
        self.assertTrue(second["replay"])
        self.assertFalse(first["replay"])
        self.assertEqual(self.store.status(T0)["notification_previews_not_sent"],1)

    def test_update_does_not_use_new_post_quota(self):
        story,rel,_=self.staged()
        self.store.simulate(rel["release_id"],T0)
        updated=self.draft()
        updated["updated_at"]="2026-11-13T18:00:00-05:00"
        updated["sections"][0]["paragraphs"].append("A new synthetic correction was recorded.")
        self.store.submit(updated,"writer-task",T1)
        self.store.review(updated["id"],"editor-task","approved",self.collector,T1,
                          "Synthetic correction checked against original source.")
        later=self.reserve(updated,T1)
        self.assertEqual(later["kind"],"update")
        self.assertEqual(self.store.status(T1)["new_posts_reserved_or_simulated"],0)
        staged=self.store.stage(later["release_id"],T1)
        self.assertEqual(staged["file_count"],3)
        self.store.simulate(later["release_id"],T1)
        self.assertEqual(self.store.status(T1)["notification_previews_not_sent"],2)

    def test_broken_staged_html_blocks_notification(self):
        _,rel,stage=self.staged()
        p=Path(stage["preview_root"])/stage["article_rel_path"]
        p.write_bytes(b"CORRUPTED STAGED HTML")
        with self.assertRaisesRegex(GateError,"integrity failure"):
            self.store.simulate(rel["release_id"],T0)
        self.assertEqual(self.store.status(T0)["notification_previews_not_sent"],0)

    def test_cannot_simulate_unstaged_reservation(self):
        s=self.put_approved()
        rel=self.reserve(s)
        with self.assertRaisesRegex(GateError,"staged first"):
            self.store.simulate(rel["release_id"],T0)

    def test_only_simulation_mode_exists_in_ledger_schema(self):
        with self.store._transaction() as db:
            text=db.execute("SELECT sql FROM sqlite_master WHERE name='releases'").fetchone()[0]
            self.assertIn("mode='simulation'",text)
            self.assertNotIn("production",text)

    def test_current_live_collector_is_not_edited(self):
        path=DEFAULT_COLLECTOR
        if not path.is_file():
            self.skipTest("live collector not mounted on test device")
        before=path.stat()
        result=read_only_collector(path)
        after=path.stat()
        self.assertEqual((before.st_size,before.st_mtime_ns),(after.st_size,after.st_mtime_ns))
        self.assertGreaterEqual(result["sources"],4)
        self.assertEqual(result["unreviewed_buckets"],len(result["candidates"]))

if __name__=="__main__":
    unittest.main(verbosity=2)