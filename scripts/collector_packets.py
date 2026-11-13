"""Read-only bounded evidence packets for the scheduled blog writer.

This helper never changes the collector database or approves publication.
A text excerpt from an HTML index is not an independently verified story.
"""
from __future__ import annotations
from contextlib import closing
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import sqlite3

COLLECTOR = Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/state/local-information.sqlite3")


class VisibleText(HTMLParser):
    SKIP = {"script", "style", "svg", "noscript", "template"}
    BLOCK = {"p", "li", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "tr", "td", "a"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skipping = []
        self.chunks = []
        self.count = 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping.append(tag)
        if not self.skipping and tag in self.BLOCK:
            self.chunks.append("\n")
    def handle_endtag(self, tag):
        if tag in self.SKIP and tag in self.skipping:
            self.skipping.remove(tag)
        if not self.skipping and tag in self.BLOCK:
            self.chunks.append("\n")
    def handle_data(self, text):
        if not self.skipping and text.strip():
            self.count += len(text)
            if self.count < 150_000:
                self.chunks.append(text)
    def content(self, max_chars=6500):
        lines = []
        seen = set()
        for line in "".join(self.chunks).splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) < 12 or line in seen:
                continue
            seen.add(line)
            lines.append(line)
            if len("\n".join(lines)) >= max_chars:
                break
        return "\n".join(lines)[:max_chars]


def packets(db_path: Path = COLLECTOR, after_revision: int = 0, limit: int = 8, max_chars: int = 6500) -> dict:
    if not 0 <= after_revision <= 2**63 - 1:
        raise ValueError("invalid revision cursor")
    if not 1 <= limit <= 20 or not 500 <= max_chars <= 12000:
        raise ValueError("packet bounds exceeded")
    if not db_path.is_file():
        raise FileNotFoundError("private collector database not available")
    with closing(sqlite3.connect("file:"+str(db_path.resolve())+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.row_factory=sqlite3.Row
        rows=db.execute("""
            SELECT r.id AS revision_id,r.sha256,r.raw_body,r.observed_at,
                   r.source_url,r.title,r.topic,r.region,r.content_type,
                   d.source_id,d.document_key
            FROM revisions r JOIN documents d ON d.id=r.document_id
            WHERE r.id>? ORDER BY r.id ASC LIMIT ?""",(after_revision,limit)).fetchall()
        result=[]
        for row in rows:
            if row["content_type"]=="text/html":
                parser=VisibleText()
                parser.feed(row["raw_body"].decode("utf-8","replace"))
                visible=parser.content(max_chars)
            else:
                visible=unescape(row["raw_body"].decode("utf-8","replace"))[:max_chars]
            result.append({
                "revision_id":row["revision_id"],"source_id":row["source_id"],
                "document_key":row["document_key"],"source_url":row["source_url"],
                "source_sha256":row["sha256"],"observed_at":row["observed_at"],
                "title":row["title"],"topic":row["topic"],"region":row["region"],
                "raw_content_type":row["content_type"],"private_excerpt":visible,
                "review_status":"unreviewed","publication_approval":False,
                "note":"Excerpt of a source page; not proof an individual event occurred."
            })
    return {"schema_version":1,"read_only":True,"after_revision":after_revision,
            "last_revision":result[-1]["revision_id"] if result else after_revision,
            "packets":result,"no_automatic_publication":True}