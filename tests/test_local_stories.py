"""Offline validation of the DS Local Intelligence static publishing boundary."""
from __future__ import annotations

import copy
import json
import pathlib
import shutil
import tempfile
import unittest
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_local_stories import BUILD_ROOT, InvalidStory, build, validate


def synthetic_story() -> dict:
    """Entirely fictional sample, NEVER use as an actual local event."""
    return {
        "id": "synthetic-demo-001",
        "slug": "synthetic-test-public-meeting",
        "publication_status": "approved",
        "sensitive": False,
        "title": "Proposed Example Park Meeting Discussed (SYNTHETIC TEST)",
        "summary": "Synthetic fixture only. This is not a real event in Greeneville.",
        "location": "Greeneville, TN",
        "category": "government",
        "verification_status": "proposed",
        "published_at": "2026-11-12T10:00:00-05:00",
        "updated_at": "2026-11-12T11:00:00-05:00",
        "sources": [{
            "title": "Fictional test document",
            "url": "https://example.org/synthetic-test-document",
            "kind": "official",
        }],
        "sections": [{
            "heading": "What the fictional record says",
            "paragraphs": [
                "This is fabricated test content, not a claim about a local meeting.",
                "The proposal has not been confirmed as an event.",
            ],
        }],
    }


class PublishingBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.sample = synthetic_story()
        self.generated = []
        self.addCleanup(lambda: [shutil.rmtree(p, ignore_errors=True) for p in self.generated])

    def preview_output(self, fixture_dir: pathlib.Path, suffix: str) -> pathlib.Path:
        target = BUILD_ROOT / (fixture_dir.name + "-" + suffix)
        self.generated.append(target)
        return target

    def test_empty_public_manifest_is_legal(self):
        self.assertEqual(validate({"schema_version": 1, "stories": []}), [])

    def test_valid_approved_record(self):
        self.assertEqual(len(validate({"schema_version": 1, "stories": [self.sample]})), 1)

    def test_draft_cannot_publish(self):
        self.sample["publication_status"] = "draft"
        with self.assertRaisesRegex(InvalidStory, "approved"):
            validate({"schema_version": 1, "stories": [self.sample]})

    def test_missing_review_classification_cannot_publish(self):
        self.sample.pop("sensitive")
        with self.assertRaisesRegex(InvalidStory, "review"):
            validate({"schema_version": 1, "stories": [self.sample]})

    def test_sensitive_cannot_publish(self):
        self.sample["sensitive"] = True
        with self.assertRaisesRegex(InvalidStory, "review"):
            validate({"schema_version": 1, "stories": [self.sample]})

    def test_unlabeled_proposed_item_rejected(self):
        self.sample["title"] = "The Example Park Meeting Is Happening"
        with self.assertRaisesRegex(InvalidStory, "clearly labeled"):
            validate({"schema_version": 1, "stories": [self.sample]})

    def test_confirmed_item_requires_better_evidence(self):
        self.sample["verification_status"] = "confirmed"
        self.sample["sources"][0]["kind"] = "other_reporting"
        with self.assertRaisesRegex(InvalidStory, "firsthand"):
            validate({"schema_version": 1, "stories": [self.sample]})

    def test_source_url_safety(self):
        for url in ("javascript:alert(1)", "http://example.org", "/file/path", "https://user:pass@example.org"):
            with self.subTest(url=url):
                s = copy.deepcopy(self.sample)
                s["sources"][0]["url"] = url
                with self.assertRaises(InvalidStory):
                    validate({"schema_version": 1, "stories": [s]})

    def test_unsafe_slug_rejected(self):
        for slug in ("../../secrets", "hello/world", "Index", "index"):
            with self.subTest(slug=slug):
                s = copy.deepcopy(self.sample)
                s["slug"] = slug
                with self.assertRaises(InvalidStory):
                    validate({"schema_version": 1, "stories": [s]})

    def test_duplicate_slug_rejected(self):
        s2 = copy.deepcopy(self.sample)
        s2["id"] = "synthetic-demo-002"
        with self.assertRaisesRegex(InvalidStory, "duplicate"):
            validate({"schema_version": 1, "stories": [self.sample, s2]})

    def test_invalid_update_order_rejected(self):
        self.sample["updated_at"] = "2026-11-11T10:00:00-05:00"
        with self.assertRaisesRegex(InvalidStory, "precedes"):
            validate({"schema_version": 1, "stories": [self.sample]})

    def test_staged_build_does_not_publish_unapproved_content(self):
        with tempfile.TemporaryDirectory(prefix="story-tests-", dir=ROOT / "tests") as folder:
            base = pathlib.Path(folder)
            private_data = base / "fixture.json"
            private_data.write_text(json.dumps({"schema_version": 1, "stories": [self.sample]}))
            out = self.preview_output(base, "published-snapshot")
            count = build(private_data, out)
            self.assertEqual(count, 1)
            page = out / "greeneville" / (self.sample["slug"] + ".html")
            self.assertTrue(page.exists())
            body = page.read_text()
            self.assertIn("SYNTHETIC TEST", body)
            self.assertIn("https://example.org/synthetic-test-document", body)
            self.assertIn("application/ld+json", body)
            self.assertIn('href="blog-v2.html"', body)
            index = (out / "blog-v2.html").read_text()
            self.assertIn("1 published", index)
            self.assertIn("greeneville/synthetic-test-public-meeting.html", index)
            for original in ("post-high-converting-websites.html",
                             "post-small-business-security.html",
                             "post-site-speed-revenue.html"):
                self.assertTrue((out / original).exists(), original)
            self.assertFalse((out / "content").exists())
            self.assertFalse((out / "backend").exists())
            self.assertFalse((out / "tests").exists())
            ns = {"sm":"http://www.sitemaps.org/schemas/sitemap/0.9"}
            xml = ET.parse(out / "sitemap.xml")
            locs = [n.text for n in xml.findall(".//sm:loc", ns)]
            self.assertIn("https://dsdigitaldesigns.org/greeneville/synthetic-test-public-meeting.html", locs)

    def test_escapes_untrusted_source_text(self):
        s = copy.deepcopy(self.sample)
        s["sections"][0]["paragraphs"].append("<script>alert('bad')</script>")
        with tempfile.TemporaryDirectory(prefix="story-xss-", dir=ROOT / "tests") as folder:
            base = pathlib.Path(folder)
            file = base / "fixture.json"
            file.write_text(json.dumps({"schema_version": 1, "stories": [s]}))
            out = self.preview_output(base, "snapshot")
            build(file, out)
            article = (out / "greeneville" / (s["slug"] + ".html")).read_text()
            self.assertIn("&lt;script&gt;", article)
            self.assertNotIn("<script>alert('bad')</script>", article)

    def test_stable_article_url_on_story_revision(self):
        with tempfile.TemporaryDirectory(prefix="story-revision-", dir=ROOT / "tests") as folder:
            base = pathlib.Path(folder)
            file = base / "fixture.json"
            first = {"schema_version":1, "stories":[self.sample]}
            file.write_text(json.dumps(first))
            out = self.preview_output(base, "snapshot")
            build(file, out)
            expected = out / "greeneville" / "synthetic-test-public-meeting.html"
            self.assertTrue(expected.exists())
            s = copy.deepcopy(self.sample)
            s["updated_at"] = "2026-11-13T10:00:00-05:00"
            s["sections"][0]["paragraphs"].append("A synthetic update was added.")
            file.write_text(json.dumps({"schema_version":1,"stories":[s]}))
            build(file, out)
            self.assertTrue(expected.exists())
            self.assertIn("A synthetic update", expected.read_text())
            self.assertEqual(len(list((out / "greeneville").glob("*.html"))),1)

    def test_output_restricted_to_generated_build_folder(self):
        with self.assertRaises(ValueError):
            build(ROOT / "content" / "local-stories.json", ROOT / "dist")


if __name__ == "__main__":
    BUILD_ROOT.mkdir(exist_ok=True)
    unittest.main(verbosity=2)