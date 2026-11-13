"""Tests for read-only evidence packet intake from private collector snapshots."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from collector_packets import packets, VisibleText, COLLECTOR

HTML=b"""<html><head><script>Never quote this script data</script>
<style>hidden css content</style></head>
<body><main><h1>SYNTHETIC city council agenda</h1>
<section><h2>Proposed public meeting item</h2>
<p>This is a controlled fictional proposal, not evidence of a real event.</p>
<p>This is a controlled fictional proposal, not evidence of a real event.</p>
</section></main></body></html>"""


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="packet-readonly-")
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"source.sqlite3"
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript("""
            CREATE TABLE documents(id INTEGER PRIMARY KEY,source_id TEXT,document_key TEXT);
            CREATE TABLE revisions(
               id INTEGER PRIMARY KEY,document_id INTEGER,sha256 TEXT,raw_body BLOB,
               observed_at TEXT,source_url TEXT,title TEXT,topic TEXT,region TEXT,content_type TEXT);
            """)
            c.execute("INSERT INTO documents VALUES(1,'town-agendas','index')")
            for i in (1,2):
                raw = HTML if i==1 else HTML+b" suffix"
                c.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (i,1,sha256(raw).hexdigest(),raw,
                    "2026-11-12T22:00:00+00:00",
                    "https://www.greenevilletn.gov/o/tog/page/board-commission-agendas",
                    "Synthetic town agenda","government","Greeneville, TN","text/html"))
            c.commit()

    def test_extracts_meaningful_visible_text(self):
        p=packets(self.db,limit=1)["packets"][0]
        self.assertIn("SYNTHETIC city council agenda",p["private_excerpt"])
        self.assertNotIn("Never quote this script",p["private_excerpt"])
        self.assertNotIn("hidden css content",p["private_excerpt"])

    def test_evidence_id_and_hash_preserved(self):
        p=packets(self.db,limit=1)["packets"][0]
        self.assertEqual(p["revision_id"],1)
        self.assertEqual(len(p["source_sha256"]),64)
        self.assertEqual(p["source_id"],"town-agendas")
        self.assertEqual(p["publication_approval"],False)

    def test_cursor_returns_only_unread_revisions(self):
        report=packets(self.db,after_revision=1)
        self.assertEqual(len(report["packets"]),1)
        self.assertEqual(report["last_revision"],2)
        self.assertEqual(report["after_revision"],1)

    def test_empty_cursor_is_stable(self):
        report=packets(self.db,after_revision=2)
        self.assertEqual(report["last_revision"],2)
        self.assertEqual(report["packets"],[])

    def test_bounded_packet_size(self):
        p=packets(self.db,max_chars=500)["packets"][0]
        self.assertLessEqual(len(p["private_excerpt"]),500)

    def test_invalid_bounds_are_rejected(self):
        for kw in [{"limit":0},{"limit":1000},{"max_chars":1},{"after_revision":-1}]:
            with self.subTest(params=kw):
                with self.assertRaises(ValueError):
                    packets(self.db,**kw)

    def test_read_does_not_modify_original_database(self):
        stat=self.db.stat()
        packets(self.db)
        new=self.db.stat()
        self.assertEqual((stat.st_mtime_ns,stat.st_size),(new.st_mtime_ns,new.st_size))

    def test_real_source_store_is_read_only(self):
        if not COLLECTOR.is_file():
            self.skipTest("real collector not available on this test host")
        before=COLLECTOR.stat()
        r=packets(COLLECTOR,limit=4,max_chars=2000)
        after=COLLECTOR.stat()
        self.assertEqual((before.st_mtime_ns,before.st_size),(after.st_mtime_ns,after.st_size))
        self.assertGreaterEqual(len(r["packets"]),1)
        self.assertFalse(any(p["publication_approval"] for p in r["packets"]))


if __name__=="__main__":
    unittest.main(verbosity=2)