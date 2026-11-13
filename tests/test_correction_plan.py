"""Original-URL correction planning; synthetic source and original HTML only."""
from contextlib import closing
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))
from correction_plan import prepare_correction,CorrectionBlocked
from release_coordinator import Store,public_story_payload
from build_local_stories import create_article
from test_release_coordinator import example,RAW,SOURCE_URL,T0,T1

class CorrectionTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="ds-correction-tests-")
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.collector=self.root/"raw.sqlite3"
        raw=RAW.encode()
        self.hash=sha256(raw).hexdigest()
        with closing(sqlite3.connect(self.collector)) as db:
            db.executescript("""CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT);
                CREATE TABLE revisions(id INTEGER PRIMARY KEY,document_id INTEGER,raw_body BLOB,sha256 TEXT,source_url TEXT);""")
            db.execute("INSERT INTO documents VALUES(1,'synthetic-official')")
            db.execute("INSERT INTO revisions VALUES(1,1,?,?,?)",(raw,self.hash,SOURCE_URL))
            db.commit()
        self.original=example(1,self.hash)
        self.update=example(1,self.hash)
        self.update["updated_at"]="2026-11-13T18:00:00-05:00"
        self.update["sections"][0]["paragraphs"].append("Correction: the fictional example is still only a proposal.")
        self.main=self.root/"main"
        self.main.mkdir()
        self.path="greeneville/"+self.original["slug"]+".html"
        (self.main/"greeneville").mkdir()
        (self.main/self.path).write_text(create_article(public_story_payload(self.original)))
        self.store=Store(self.root/"editorial")
        self.store.submit(self.update,"writer-task",T1)
        self.store.review(self.update["id"],"independent-editor","approved",self.collector,T1,
                          "Independently checked fictional correction against original source.")
        self.state=self.root/"private-correction"
        self.reason=("Correction: the municipal record describes a proposed item, "
                     "not a final approved decision; updated body wording.")

    def prepare(self,original=None,reason=None,at=T1):
        return prepare_correction(original or self.original,self.update["id"],
            self.store.path,self.collector,self.main,"a"*40,
            self.reason if reason is None else reason,self.state,at)

    def test_correction_is_one_file_staging_only(self):
        p=self.prepare()
        self.assertEqual(p["changed_file_count"],1)
        self.assertEqual(p["state"],"STAGED_ONLY")
        self.assertFalse(p["published"])
        self.assertEqual(p["url_path"],self.path)
        self.assertTrue(Path(p["article_file"]).is_file())

    def test_original_canonical_stays_unchanged(self):
        p=self.prepare()
        body=Path(p["article_file"]).read_text()
        self.assertIn("Correction and update note",body)
        self.assertIn("https://dsdigitaldesigns.org/"+self.path,body)

    def test_original_git_file_unmodified(self):
        h=sha256((self.main/self.path).read_bytes()).hexdigest()
        self.prepare()
        self.assertEqual(sha256((self.main/self.path).read_bytes()).hexdigest(),h)

    def test_private_state_permissions(self):
        p=self.prepare()
        self.assertEqual(self.state.stat().st_mode&0o777,0o700)
        self.assertEqual(Path(p["article_file"]).stat().st_mode&0o777,0o600)
        self.assertEqual((self.state/"corrections.sqlite3").stat().st_mode&0o777,0o600)

    def test_immutable_slug_change_rejected(self):
        wrong=dict(self.original,slug="new-address-slug")
        with self.assertRaisesRegex(CorrectionBlocked,"immutable"):
            self.prepare(original=wrong)

    def test_correction_requires_human_explanation(self):
        with self.assertRaisesRegex(CorrectionBlocked,"substantive"):
            self.prepare(reason="fix")

    def test_retraction_has_separate_escalation(self):
        with self.assertRaisesRegex(CorrectionBlocked,"requires owner review"):
            self.prepare(reason="Retraction: a previously reported accusation may be wrong and must be removed.")

    def test_diverged_original_blocks(self):
        (self.main/self.path).write_text("another actor rewrote this article")
        with self.assertRaisesRegex(CorrectionBlocked,"diverged"):
            self.prepare()

    def test_duplicate_correction_cannot_stage_twice(self):
        self.prepare()
        with self.assertRaisesRegex(CorrectionBlocked,"already staged"):
            self.prepare()

    def test_update_requires_newer_timestamp(self):
        self.update["updated_at"]=self.original["updated_at"]
        self.store.submit(self.update,"writer-task",T1)
        self.store.review(self.update["id"],"independent-editor","approved",self.collector,T1,
                          "Checked unchanged timestamp and source against prior record.")
        with self.assertRaisesRegex(CorrectionBlocked,"new modified timestamp"):
            self.prepare()

    def test_mismatched_title_rejected(self):
        self.update["title"]="Proposed new unrelated headline to trick existing URL"
        self.store.submit(self.update,"writer-task",T1)
        self.store.review(self.update["id"],"independent-editor","approved",self.collector,T1,
                          "Checked new title against fictional original source.")
        with self.assertRaisesRegex(CorrectionBlocked,"immutable"):
            self.prepare()

    def test_missing_approval_stops_correction(self):
        self.update["sections"][0]["paragraphs"].append("More fictional news requiring review.")
        self.store.submit(self.update,"writer-task",T1)
        with self.assertRaises(ValueError):
            self.prepare()

if __name__=="__main__":unittest.main(verbosity=2)