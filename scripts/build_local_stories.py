#!/usr/bin/env python3
"""Build a REVIEWABLE static preview from explicitly approved local stories.

No network calls, credential access, publishing, commits, uploads, or schedules.
Copies public site assets into an isolated build/ directory, then generates
SEO-friendly HTML article pages, index cards, and sitemap entries.

Raw collections and draft records must NOT be placed in the public manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
import pathlib
import re
import shutil
import subprocess
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build"
DEFAULT_INPUT = ROOT / "content" / "local-stories.json"
SITE_BASE = "https://dsdigitaldesigns.org"
MARKER_BEGIN = "<!-- LOCAL_STORIES_START -->"
MARKER_END = "<!-- LOCAL_STORIES_END -->"
VALID_CATEGORIES = {"government", "business", "events", "community", "infrastructure"}
VALID_STATUS = {"proposed", "confirmed", "updated"}
VALID_SOURCE_KIND = {"official", "firsthand", "other_reporting"}
TRACKED_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".png", ".jpg", ".jpeg",
    ".svg", ".webp", ".ico", ".txt", ".xml", ".woff", ".woff2"
}


class InvalidStory(ValueError):
    pass


def require_text(data: dict, field: str, limit: int = 500) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise InvalidStory(f"{field}: nonempty text up to {limit} chars is required")
    return value.strip()


def check_date(value: str, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise InvalidStory(f"{field}: timezone-aware ISO 8601 required") from exc


def check_source(src: dict) -> None:
    if not isinstance(src, dict):
        raise InvalidStory("source must be an object")
    require_text(src, "title", 180)
    url = require_text(src, "url", 1500)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise InvalidStory("source url must be a direct HTTPS URL with hostname and no credentials")
    kind = require_text(src, "kind", 32)
    if kind not in VALID_SOURCE_KIND:
        raise InvalidStory(f"invalid source kind: {kind}")


def validate(manifest: dict) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise InvalidStory("schema_version must be 1")
    stories = manifest.get("stories")
    if not isinstance(stories, list):
        raise InvalidStory("stories must be an array")
    ids, slugs = set(), set()
    for s in stories:
        if not isinstance(s, dict):
            raise InvalidStory("each story must be an object")
        id_ = require_text(s, "id", 70)
        slug = require_text(s, "slug", 90)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or slug in {"index", "assets"}:
            raise InvalidStory(f"unsafe slug: {slug}")
        if id_ in ids or slug in slugs:
            raise InvalidStory("duplicate story id or slug")
        ids.add(id_)
        slugs.add(slug)
        if s.get("publication_status") != "approved":
            raise InvalidStory(f"{slug}: only approved records allowed in public manifest")
        if s.get("sensitive") is not False:
            raise InvalidStory(f"{slug}: sensitive or unclassified stories require separate review")
        require_text(s, "title", 180)
        require_text(s, "summary", 500)
        require_text(s, "location", 100)
        category = require_text(s, "category", 32)
        if category not in VALID_CATEGORIES:
            raise InvalidStory(f"{slug}: unrecognized category")
        status = require_text(s, "verification_status", 32)
        if status not in VALID_STATUS:
            raise InvalidStory(f"{slug}: unrecognized verification status")
        if status == "proposed" and not re.search(
            r"\b(proposed?|proposal|consider(?:ed|ing)?|discuss(?:ed|ion)?|plans?)\b",
            s["title"], re.IGNORECASE
        ):
            raise InvalidStory(f"{slug}: proposed items must be clearly labeled in headline")
        published = require_text(s, "published_at", 45)
        updated = require_text(s, "updated_at", 45)
        check_date(published, "published_at")
        check_date(updated, "updated_at")
        if datetime.fromisoformat(updated) < datetime.fromisoformat(published):
            raise InvalidStory(f"{slug}: updated_at precedes published_at")
        sources = s.get("sources")
        if not isinstance(sources, list) or not (1 <= len(sources) <= 20):
            raise InvalidStory(f"{slug}: at least one attributable source required")
        for src in sources:
            check_source(src)
        if status == "confirmed" and not any(src["kind"] in {"official", "firsthand"} for src in sources):
            raise InvalidStory(f"{slug}: confirmed status requires official or firsthand evidence")
        if status == "proposed" and not any(src["kind"] == "official" for src in sources):
            raise InvalidStory(f"{slug}: proposed public action needs an official documentary source")
        sections = s.get("sections")
        if not isinstance(sections, list) or not (1 <= len(sections) <= 15):
            raise InvalidStory(f"{slug}: at least one original article section required")
        for section in sections:
            if not isinstance(section, dict):
                raise InvalidStory("section must be an object")
            require_text(section, "heading", 150)
            paras = section.get("paragraphs")
            if not isinstance(paras, list) or not (1 <= len(paras) <= 12):
                raise InvalidStory("section paragraphs required")
            if any(not isinstance(p, str) or not p.strip() or len(p) > 2500 for p in paras):
                raise InvalidStory("invalid paragraph")
    return sorted(stories, key=lambda x: x["updated_at"], reverse=True)


def create_card(s: dict) -> str:
    category = escape(s["category"], quote=True)
    title = escape(s["title"])
    summary = escape(s["summary"])
    safe_slug = escape(s["slug"], quote=True)
    status = escape(s["verification_status"].capitalize())
    location = escape(s["location"])
    search_text = escape(f'{s["title"]} {s["summary"]} {s["location"]} {s["category"]}', quote=True)
    return f"""<article class="lb-card" data-blog-article data-category="{category}" data-region="greeneville" data-search="{search_text}">
      <div class="lb-card-tags"><span class="lb-chip">Local · {escape(s["category"].title())}</span><span class="lb-chip lb-chip-plain">{status}</span></div>
      <h3>{title}</h3>
      <p>{summary}</p>
      <div class="lb-card-footer"><span>{location} · {escape(s["updated_at"][:10])}</span><a href="greeneville/{safe_slug}.html">Read verified report →</a></div>
    </article>"""


def create_article(s: dict) -> str:
    title = escape(s["title"])
    summary = escape(s["summary"], quote=True)
    url = f'{SITE_BASE}/greeneville/{s["slug"]}.html'
    status = escape(s["verification_status"].capitalize())
    paragraphs = []
    for section in s["sections"]:
        paragraphs.append(f'<section><h2>{escape(section["heading"])}</h2>')
        paragraphs.extend(f'<p>{escape(p)}</p>' for p in section["paragraphs"])
        paragraphs.append('</section>')
    sources = "\n".join(
        f'<li><a href="{escape(src["url"], quote=True)}" rel="noopener noreferrer" target="_blank">{escape(src["title"])}</a> <small>({escape(src["kind"])})</small></li>'
        for src in s["sources"]
    )
    structured = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": s["title"],
        "description": s["summary"],
        "datePublished": s["published_at"],
        "dateModified": s["updated_at"],
        "mainEntityOfPage": url,
        "author": {"@type": "Organization", "name": "DS Digital Designs"},
        "publisher": {"@type": "Organization", "name": "DS Digital Designs"},
    }
    json_ld = json.dumps(structured, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="/">
  <title>{title} | DS Digital Designs Greeneville Local</title>
  <meta name="description" content="{summary}">
  <link rel="canonical" href="{escape(url, quote=True)}">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{escape(s["title"], quote=True)}">
  <meta property="og:description" content="{summary}">
  <meta property="og:url" content="{escape(url, quote=True)}">
  <meta property="article:published_time" content="{escape(s["published_at"], quote=True)}">
  <meta property="article:modified_time" content="{escape(s["updated_at"], quote=True)}">
  <link rel="stylesheet" href="assets/css/theme.css">
  <link rel="stylesheet" href="assets/css/blog-local.css">
  <script type="application/ld+json">{json_ld}</script>
</head>
<body>
  <div id="header-slot"></div><div id="nav-slot"></div>
  <main class="local-blog local-article" id="main-content">
    <div class="lb-mini-nav"><div class="lb-container lb-mini-nav-inner"><span>DS Digital Designs · Local Intelligence</span><a href="blog-v2.html">← All articles</a></div></div>
    <div class="lb-container lb-article-body">
      <nav class="lb-breadcrumb" aria-label="Breadcrumb"><a href="index.html">Home</a> / <a href="blog-v2.html">Local intelligence</a> / Article</nav>
      <div class="lb-eyebrow"><span class="lb-dot" aria-hidden="true"></span>{escape(s["location"])} · {escape(s["category"].title())}</div>
      <h1>{title}</h1>
      <div class="lb-article-meta"><span class="lb-chip">{status}</span> Published <time datetime="{escape(s["published_at"], quote=True)}">{escape(s["published_at"][:10])}</time> · Updated <time datetime="{escape(s["updated_at"], quote=True)}">{escape(s["updated_at"][:10])}</time></div>
      <p class="lb-article-summary">{escape(s["summary"])}</p>
      <div class="lb-article-content">{"".join(paragraphs)}</div>
      <section class="lb-sources"><h2>Primary sources and references</h2><ul>{sources}</ul><p>Publication labels indicate how this report was categorized. Read the linked documents for the original context. This page is not an official government notice.</p></section>
      <p><a class="lb-text-link" href="blog-v2.html">← Return to all articles</a></p>
    </div>
  </main>
  <div id="footer-slot"></div>
  <script src="assets/js/shell.js"></script>
  <script src="assets/js/load-components.js?v=2026-04-26-menu-seo"></script>
  <script src="chat-widget.js"></script>
</body>
</html>"""


def copy_site(dest: pathlib.Path) -> None:
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    for path_text in filter(None, paths):
        rel = pathlib.Path(path_text)
        if rel.parts[0] in {"backend", "tests", "scripts", "content", "reports", "tools", ".github"}:
            continue
        if rel.suffix.lower() not in TRACKED_EXTENSIONS:
            continue
        src = ROOT / rel
        if not src.is_file() or src.is_symlink():
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)


def render_index(dest: pathlib.Path, stories: list[dict]) -> None:
    blog = dest / "blog-v2.html"
    html_text = blog.read_text(encoding="utf-8")
    if html_text.count(MARKER_BEGIN) != 1 or html_text.count(MARKER_END) != 1:
        raise InvalidStory("blog index is missing exactly one pair of story markers")
    start, end = html_text.index(MARKER_BEGIN), html_text.index(MARKER_END)
    if start >= end:
        raise InvalidStory("blog index story markers out of order")
    cards = "\n".join(create_card(s) for s in stories)
    html_text = html_text[:start + len(MARKER_BEGIN)] + "\n" + cards + "\n" + html_text[end:]
    if stories:
        old_count = 'id="local-story-count">Not published yet'
        old_status = 'id="local-coverage-status">In preparation'
        if html_text.count(old_count) != 1 or html_text.count(old_status) != 1:
            raise InvalidStory("blog index local story status anchors missing")
        html_text = html_text.replace(old_count, f'id="local-story-count">{len(stories)} published')
        html_text = html_text.replace(old_status, 'id="local-coverage-status">Verified stories available')
    blog.write_text(html_text, encoding="utf-8")


def render_sitemap(dest: pathlib.Path, stories: list[dict]) -> None:
    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    tree = ET.parse(dest / "sitemap.xml")
    urlset = tree.getroot()
    existing = {node.findtext(namespace + "loc"): node for node in urlset.findall(namespace + "url")}
    for story in stories:
        loc = f'{SITE_BASE}/greeneville/{story["slug"]}.html'
        if loc in existing:
            raise InvalidStory("generated sitemap URL collides with existing URL")
        node = ET.SubElement(urlset, namespace + "url")
        ET.SubElement(node, namespace + "loc").text = loc
        ET.SubElement(node, namespace + "lastmod").text = story["updated_at"][:10]
        ET.SubElement(node, namespace + "changefreq").text = "weekly"
    if stories:
        main = existing.get(SITE_BASE + "/blog-v2.html")
        if main is not None:
            lastmod = main.find(namespace + "lastmod")
            if lastmod is not None:
                lastmod.text = max(s["updated_at"] for s in stories)[:10]
    tree.write(dest / "sitemap.xml", encoding="utf-8", xml_declaration=True)


def build(input_path: pathlib.Path, output_path: pathlib.Path) -> int:
    build_root = BUILD_ROOT.resolve()
    output = output_path.resolve()
    if output == build_root or not output.is_relative_to(build_root):
        raise ValueError("output must be a child directory of this checkout's build/ folder")
    if input_path.resolve().is_relative_to(build_root):
        raise ValueError("input must not be read from a generated build")
    manifest = json.loads(input_path.read_text(encoding="utf-8"))
    stories = validate(manifest)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    copy_site(output)
    render_index(output, stories)
    target = output / "greeneville"
    target.mkdir(exist_ok=True)
    for story in stories:
        (target / (story["slug"] + ".html")).write_text(create_article(story), encoding="utf-8")
    render_sitemap(output, stories)
    print(f"Static preview: {output} | approved stories: {len(stories)} | live site unchanged")
    return len(stories)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=pathlib.Path, default=BUILD_ROOT / "local-preview")
    args = parser.parse_args()
    build(args.input, args.output)


if __name__ == "__main__":
    main()