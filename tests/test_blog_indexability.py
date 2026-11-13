"""Static SEO regression checks for the *existing, deployed* DS blog files.

Does not query Google, modify URLs, publish, or request indexing.
"""
from __future__ import annotations

import pathlib
import unittest
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://dsdigitaldesigns.org/"
BLOG = "blog-v2.html"
POSTS = [
    "post-high-converting-websites.html",
    "post-small-business-security.html",
    "post-site-speed-revenue.html",
]
PAGES = [BLOG] + POSTS
OG_IMAGE = "0193CA57-3463-4528-AE1F-50F2BCD64BFB.png"


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_count = 0
        self.in_title = False
        self.title = ""
        self.h1_count = 0
        self.meta = []
        self.links = []
        self.anchors = []
        self.viewport = False
        self.structured = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "title":
            self.title_count += 1
            self.in_title = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "meta":
            self.meta.append(d)
        elif tag == "link":
            self.links.append(d)
        elif tag == "a":
            self.anchors.append(d)
        elif tag == "script":
            self.scripts.append(d)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data

    def find_meta(self, attribute, value):
        return [m.get("content") for m in self.meta if m.get(attribute, "").lower() == value.lower()]

    def canonical(self):
        return [l.get("href") for l in self.links if "canonical" in (l.get("rel") or "").split()]


class BlogSEOTests(unittest.TestCase):
    def parse(self, filename):
        data = (ROOT / filename).read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(data)
        return parser

    def test_exact_existing_routes_stay_present(self):
        for filename in PAGES:
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).is_file())

    def test_one_correct_self_referencing_https_canonical(self):
        for filename in PAGES:
            with self.subTest(filename=filename):
                self.assertEqual(self.parse(filename).canonical(), [BASE + filename])

    def test_one_title_and_one_h1_each(self):
        for filename in PAGES:
            with self.subTest(filename=filename):
                page = self.parse(filename)
                self.assertEqual(page.title_count, 1)
                self.assertGreater(len(page.title.strip()), 10)
                self.assertEqual(page.h1_count, 1)

    def test_description_and_social_metadata(self):
        for filename in PAGES:
            with self.subTest(filename=filename):
                page = self.parse(filename)
                desc = page.find_meta("name", "description")
                self.assertEqual(len(desc), 1)
                self.assertGreater(len(desc[0]), 50)
                self.assertEqual(len(page.find_meta("property", "og:title")), 1)
                self.assertEqual(page.find_meta("property", "og:url"), [BASE + filename])
                self.assertEqual(page.find_meta("property", "og:image"), [BASE + OG_IMAGE])
                self.assertTrue(page.find_meta("name", "twitter:card"))

    def test_no_index_restriction_on_four_preferred_urls(self):
        for filename in PAGES:
            with self.subTest(filename=filename):
                values = self.parse(filename).find_meta("name", "robots")
                self.assertFalse(any("noindex" in (x or "").lower() for x in values))

    def test_old_duplicate_urls_are_explicitly_deindexed(self):
        for filename, target in [
            ("blog.html", BLOG),
            ("why-site-speed-impacts-revenue.html", POSTS[-1]),
        ]:
            with self.subTest(filename=filename):
                page = self.parse(filename)
                self.assertEqual(page.canonical(), [BASE + target])
                self.assertTrue(any("noindex" in x.lower() for x in page.find_meta("name", "robots")))

    def test_blog_links_to_all_existing_articles(self):
        page = self.parse(BLOG)
        linked = {a.get("href") for a in page.anchors}
        self.assertTrue(set(POSTS).issubset(linked))

    def test_article_backlinks_to_blog(self):
        for filename in POSTS:
            with self.subTest(filename=filename):
                self.assertIn(BLOG, {a.get("href") for a in self.parse(filename).anchors})

    def test_sitemap_is_valid_and_contains_all_four(self):
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        tree = ET.parse(ROOT / "sitemap.xml")
        locs = [x.text for x in tree.iter(ns + "loc")]
        self.assertEqual(len(locs), len(set(locs)))
        self.assertTrue(set(BASE + f for f in PAGES).issubset(set(locs)))
        self.assertGreaterEqual(len(locs), 14)
        for url in locs:
            parts = urlparse(url)
            self.assertEqual(parts.scheme, "https")
            self.assertEqual(parts.hostname, "dsdigitaldesigns.org")
            path = unquote(parts.path).lstrip("/")
            file = ROOT / path
            self.assertTrue(file.is_file() or (file.is_dir() and (file / "index.html").exists()), url)

    def test_sitemap_lastmods_are_valid_dates(self):
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        import datetime
        tree = ET.parse(ROOT / "sitemap.xml")
        for entry in tree.getroot():
            with self.subTest(loc=entry.findtext(ns + "loc")):
                lm = entry.findtext(ns + "lastmod")
                self.assertIsNotNone(lm)
                datetime.date.fromisoformat(lm)

    def test_robots_advertises_sitemap_and_allows_crawling(self):
        robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Sitemap: " + BASE + "sitemap.xml", robots)
        self.assertNotIn("Disallow: /", robots)

    def test_social_image_exists_in_repository(self):
        self.assertTrue((ROOT / OG_IMAGE).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)