#!/usr/bin/env python3
"""Private, fail-closed staging coordinator for DS Digital Designs local reporting.

Checkpoint 004: NO live GitHub writes, deployment, email, or scheduling commands.
Synthetic end-to-end tests validate bounded releases and notification previews.
"""
from __future__ import annotations

from datetime import datetime
from contextlib import closing, contextmanager
from hashlib import sha256
from html import unescape
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
from urllib.request import urlopen
from zoneinfo import ZoneInfo

try:
    from build_local_stories import build, validate, BUILD_ROOT, SITE_BASE
except ImportError:
    from scripts.build_local_stories import build, validate, BUILD_ROOT, SITE_BASE

EASTERN = ZoneInfo("America/New_York")
MAX_NEW_PER_DAY = 4
DAILY_TARGET = 1
RELEASE_PATHS = ("blog-v2.html", "sitemap.xml")
DEFAULT_COLLECTOR = Path("/var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/state/local-information.sqlite3")
DEFAULT_PRIVATE = Path("/var/lib/kali-ai-remote/ds-local-publishing-private-004")

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS drafts (
  story_id TEXT PRIMARY KEY, slug TEXT NOT NULL, payload_json TEXT NOT NULL,
  payload_sha TEXT NOT NULL, writer_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  story_id TEXT NOT NULL REFERENCES drafts(story_id),
  payload_sha TEXT NOT NULL, reviewer_id TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('approved','rejected')),
  reviewed_at TEXT NOT NULL, note TEXT NOT NULL,
  PRIMARY KEY(story_id, payload_sha)
);
CREATE TABLE IF NOT EXISTS releases (
  release_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL REFERENCES drafts(story_id),
  payload_sha TEXT NOT NULL,
  mode TEXT NOT NULL CHECK(mode='simulation'),
  kind TEXT NOT NULL CHECK(kind IN ('new','update')),
  local_date TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('reserved','staged','simulated','aborted')),
  expected_url TEXT NOT NULL,
  preview_sha TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(story_id, payload_sha, mode)
);
CREATE TABLE IF NOT EXISTS simulated_published (
  story_id TEXT PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  first_simulated_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_previews (
  release_id TEXT PRIMARY KEY REFERENCES releases(release_id),
  status TEXT NOT NULL CHECK(status='NOT_SENT'),
  subject TEXT NOT NULL, body TEXT NOT NULL,
  mock_url TEXT NOT NULL, proposed_public_url TEXT NOT NULL,
  prepared_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_release_date ON releases(local_date,kind,state);
"""


class GateError(ValueError):
    """One of the independent release and evidence gates was not satisfied."""


def canon(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(obj: object) -> str:
    return sha256(canon(obj).encode("utf-8")).hexdigest()


def utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise GateError("timezone-aware datetime required")
    return dt.isoformat(timespec="seconds")


def read_only_collector(db_path: Path = DEFAULT_COLLECTOR) -> dict:
    """Read only metadata; never export unpublished raw source bodies."""
    if not db_path.is_file():
        raise GateError("collector database unavailable")
    with closing(sqlite3.connect("file:" + str(db_path.resolve()) + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        result = {
            "sources": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "revisions": conn.execute("SELECT COUNT(*) FROM revisions").fetchone()[0],
            "unreviewed_buckets": conn.execute("SELECT COUNT(*) FROM story_buckets WHERE status='unreviewed'").fetchone()[0],
            "candidates": [
                {"bucket_key": r[0], "title": r[1], "topic": r[2], "last_observed": r[3],
                 "editorial_approval": False, "public": False}
                for r in conn.execute(
                    "SELECT key,title,topic,updated_at FROM story_buckets ORDER BY updated_at DESC LIMIT 50")
            ],
        }
    return result


def require_source_evidence(story: dict, collector_path: Path) -> None:
    """Bind each proposed article source to immutable raw bytes and a verbatim quote.

    This checks citations actually point to data; human/editorial reasoning must
    still validate that the quote supports the whole claim and can be reused.
    """
    evidence = story.get("evidence_refs")
    sources = story.get("sources")
    if not isinstance(evidence, list) or not isinstance(sources, list) or len(evidence) < len(sources):
        raise GateError("every cited source requires raw revision evidence")
    if len(evidence) > 25:
        raise GateError("evidence count exceeds bound")
    evidenced_urls = set()
    with closing(sqlite3.connect("file:" + str(collector_path.resolve()) + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        for ref in evidence:
            if not isinstance(ref, dict) or not isinstance(ref.get("revision_id"), int):
                raise GateError("revision_id must be an integer")
            h = ref.get("sha256")
            quote = ref.get("quote")
            if not isinstance(h, str) or not re.fullmatch("[a-f0-9]{64}", h):
                raise GateError("invalid SHA-256 reference")
            if not isinstance(quote, str) or len(quote.strip()) < 8 or len(quote) > 1000:
                raise GateError("a meaningful original source quote is required")
            row = conn.execute("""
                SELECT r.raw_body,r.sha256,r.source_url,d.source_id
                FROM revisions r JOIN documents d ON d.id=r.document_id
                WHERE r.id=?
                """, (ref["revision_id"],)).fetchone()
            if not row or row[1] != h or sha256(row[0]).hexdigest() != h:
                raise GateError("source revision/hash mismatch")
            text = unescape(row[0].decode("utf-8", "replace"))
            if quote.strip() not in text:
                raise GateError("quoted evidence not found verbatim in source snapshot")
            if row[2] not in {s.get("url") for s in sources}:
                raise GateError("evidence URL not listed in article sources")
            evidenced_urls.add(row[2])
    if evidenced_urls != {s.get("url") for s in sources}:
        raise GateError("all article sources need original immutable evidence")


def public_story_payload(draft: dict) -> dict:
    """Discard evidence/agent metadata from public manifest; set approval explicitly."""
    keys = (
        "id", "slug", "title", "summary", "location", "category", "verification_status",
        "published_at", "updated_at", "sources", "sections", "sensitive"
    )
    public = {k: draft[k] for k in keys if k in draft}
    public["publication_status"] = "approved"
    validate({"schema_version": 1, "stories": [public]})
    return public


class Store:
    """All state here is for staging simulations; it is NOT a live publication ledger."""

    def __init__(self, private_dir: Path):
        path = Path(private_dir)
        if path.is_symlink():
            raise GateError("private state directory cannot be a symlink")
        repo_root = BUILD_ROOT.parent.resolve()
        real = path.resolve()
        if real == repo_root or real.is_relative_to(repo_root):
            raise GateError("private state cannot be stored in the public repository")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        real = path.resolve()
        os.chmod(real, 0o700)
        self.private_dir = real
        self.path = real / "simulation.sqlite3"
        if self.path.is_symlink():
            raise GateError("private ledger cannot be symlinked")
        self._init()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        os.chmod(self.path, 0o600)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @contextmanager
    def _transaction(self):
        db = self._connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init(self) -> None:
        db = self._connect()
        try:
            db.executescript(SCHEMA)
        finally:
            db.close()

    def submit(self, draft: dict, writer_id: str, at: datetime) -> str:
        if not isinstance(draft, dict) or not isinstance(writer_id, str) or len(writer_id.strip()) < 3:
            raise GateError("writer identity and draft required")
        if draft.get("publication_status") not in (None, "draft"):
            raise GateError("writer cannot self-approve")
        public_story_payload(draft)  # validate schema, not editorial truth
        if not draft.get("evidence_refs"):
            raise GateError("unsubstantiated draft is not eligible")
        story_id = draft["id"]
        payload_sha = digest(draft)
        with self._transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT slug,payload_sha FROM drafts WHERE story_id=?", (story_id,)).fetchone()
            if existing and existing["slug"] != draft["slug"]:
                raise GateError("cannot change a story's canonical slug")
            published = db.execute("SELECT slug FROM simulated_published WHERE story_id=?", (story_id,)).fetchone()
            if published and published["slug"] != draft["slug"]:
                raise GateError("cannot change an already used canonical slug")
            if existing and existing["payload_sha"] != payload_sha and db.execute(
                "SELECT 1 FROM releases WHERE story_id=? AND state IN ('reserved','staged')",
                (story_id,)
            ).fetchone():
                raise GateError("cannot replace draft with an active release reservation")
            db.execute("""INSERT INTO drafts(story_id,slug,payload_json,payload_sha,writer_id,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(story_id) DO UPDATE SET
                payload_json=excluded.payload_json,payload_sha=excluded.payload_sha,
                writer_id=excluded.writer_id,created_at=excluded.created_at""",
                (story_id,draft["slug"],canon(draft),payload_sha,writer_id.strip(),utc_text(at)))
        return payload_sha

    def review(
        self, story_id: str, reviewer_id: str, decision: str,
        collector_path: Path, at: datetime, note: str
    ) -> None:
        if decision not in ("approved","rejected"):
            raise GateError("editorial decision must be approved or rejected")
        if not isinstance(note, str) or len(note.strip()) < 10:
            raise GateError("editor must record a substantive review note")
        with self._transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            draft = db.execute("SELECT * FROM drafts WHERE story_id=?", (story_id,)).fetchone()
            if not draft:
                raise GateError("draft not found")
            if reviewer_id == draft["writer_id"] or not reviewer_id or len(reviewer_id) < 3:
                raise GateError("reviewer must be independent of writer")
            payload = json.loads(draft["payload_json"])
            if decision == "approved":
                public_story_payload(payload)
                if payload.get("sensitive") is not False:
                    raise GateError("sensitive content requires separate escalation")
                require_source_evidence(payload, collector_path)
                if not any(s.get("kind") == "official" for s in payload["sources"]):
                    raise GateError("local information requires an official supporting source")
            db.execute("""INSERT INTO reviews(story_id,payload_sha,reviewer_id,verdict,reviewed_at,note)
                VALUES(?,?,?,?,?,?) ON CONFLICT(story_id,payload_sha) DO UPDATE SET
                reviewer_id=excluded.reviewer_id,verdict=excluded.verdict,
                reviewed_at=excluded.reviewed_at,note=excluded.note""",
                (story_id,draft["payload_sha"],reviewer_id,decision,utc_text(at),note.strip()))

    def reserve(self, story_id: str, at: datetime) -> dict:
        """SQLite-wide serialized quota across processes, runs, and task retries."""
        at_text = utc_text(at)
        day = at.astimezone(EASTERN).date().isoformat()
        with self._transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            draft = db.execute("SELECT * FROM drafts WHERE story_id=?", (story_id,)).fetchone()
            if not draft:
                raise GateError("no submitted draft")
            review = db.execute("SELECT verdict,reviewer_id FROM reviews WHERE story_id=? AND payload_sha=?",
                                (story_id,draft["payload_sha"])).fetchone()
            if not review or review["verdict"] != "approved":
                raise GateError("current draft needs an independent approving review")
            kind = "update" if db.execute(
                "SELECT 1 FROM simulated_published WHERE story_id=?", (story_id,)
            ).fetchone() else "new"
            # Same revision gives the same release attempt even after retries.
            release_id = sha256(("simulation:" + kind + ":" + story_id + ":" + draft["payload_sha"]).encode()).hexdigest()[:32]
            existing = db.execute("SELECT * FROM releases WHERE release_id=?", (release_id,)).fetchone()
            if existing:
                return dict(existing)
            if kind == "new":
                occupied = db.execute("""SELECT COUNT(*) FROM releases
                    WHERE kind='new' AND local_date=? AND state IN ('reserved','staged','simulated')""",(day,)).fetchone()[0]
                if occupied >= MAX_NEW_PER_DAY:
                    raise GateError("four new posts already reserved or simulated this Eastern day")
                collision = db.execute("SELECT story_id FROM simulated_published WHERE slug=?",(draft["slug"],)).fetchone()
                if collision:
                    raise GateError("canonical slug already owned by another story")
            url = SITE_BASE + "/greeneville/" + draft["slug"] + ".html"
            db.execute("""INSERT INTO releases(release_id,story_id,payload_sha,mode,kind,local_date,
                       state,expected_url,updated_at) VALUES(?,?,?,'simulation',?,?, 'reserved',?,?)""",
                       (release_id,story_id,draft["payload_sha"],kind,day,url,at_text))
            return dict(db.execute("SELECT * FROM releases WHERE release_id=?", (release_id,)).fetchone())

    def _approved_manifest(self, db: sqlite3.Connection, story_id: str) -> dict:
        stories = {
            r["story_id"]: json.loads(r["payload_json"]) for r in db.execute("SELECT * FROM simulated_published")
        }
        draft = db.execute("SELECT payload_json FROM drafts WHERE story_id=?", (story_id,)).fetchone()
        stories[story_id] = public_story_payload(json.loads(draft["payload_json"]))
        return {"schema_version":1, "stories":list(stories.values())}

    def stage(self, release_id: str, at: datetime) -> dict:
        with self._transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            rel = db.execute("SELECT * FROM releases WHERE release_id=?",(release_id,)).fetchone()
            if not rel or rel["state"] not in ("reserved","staged","simulated"):
                raise GateError("unknown or aborted release")
            current = db.execute("SELECT payload_sha FROM drafts WHERE story_id=?",(rel["story_id"],)).fetchone()
            if current["payload_sha"] != rel["payload_sha"]:
                raise GateError("release snapshot no longer matches draft")
            manifest = self._approved_manifest(db,rel["story_id"])
        # Safe private manifest, never committed to public repository.
        input_dir = self.private_dir / "manifests"
        input_dir.mkdir(mode=0o700, exist_ok=True)
        input_file = input_dir / (release_id + ".json")
        input_file.write_text(canon(manifest),encoding="utf-8")
        os.chmod(input_file,0o600)
        output = BUILD_ROOT / ("release-" + release_id)
        build(input_file,output)
        expected_rel_path = "greeneville/" + next(
            s["slug"] for s in manifest["stories"] if s["id"] == rel["story_id"]
        ) + ".html"
        if not (output / expected_rel_path).is_file():
            raise GateError("expected staged article not generated")
        # The delta bundle changes only these three classes of live files.
        files = [*RELEASE_PATHS]
        files += sorted("greeneville/" + s["slug"] + ".html" for s in manifest["stories"])
        bundle = {
            "mode":"SIMULATION_ONLY",
            "release_id":release_id,
            "kind":rel["kind"],
            "story_id":rel["story_id"],
            "proposed_public_url":rel["expected_url"],
            "paths":[],
            "forbidden_actions":["push-to-main","publish","send-email","enable-schedule"],
        }
        for name in files:
            blob=(output / name).read_bytes()
            bundle["paths"].append({"path":name,"sha256":sha256(blob).hexdigest(),"bytes":len(blob)})
        manifest_path=input_dir / (release_id + ".release-bundle.json")
        manifest_path.write_text(json.dumps(bundle,indent=2),encoding="utf-8")
        os.chmod(manifest_path,0o600)
        with self._transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE releases SET state='staged',preview_sha=?,updated_at=? WHERE release_id=? AND state IN ('reserved','staged')",
                       (sha256((output/expected_rel_path).read_bytes()).hexdigest(),utc_text(at),release_id))
        return {"release":release_id,"preview_root":str(output),"article_rel_path":expected_rel_path,
                "bundle":str(manifest_path),"file_count":len(files),"paths":files}

    def simulate(self, release_id: str, at: datetime) -> dict:
        """Mock release to a local loopback HTTP endpoint, never to public domain."""
        with self._transaction() as db:
            rel = db.execute("SELECT * FROM releases WHERE release_id=?",(release_id,)).fetchone()
            if not rel or rel["state"] not in ("staged","simulated"):
                raise GateError("release must be staged first")
            if rel["state"] == "simulated":
                prev = db.execute("SELECT * FROM notification_previews WHERE release_id=?",(release_id,)).fetchone()
                return {"release_id":release_id,"replay":True,"email_status":prev["status"],"mock_url":prev["mock_url"]}
            draft = json.loads(db.execute("SELECT payload_json FROM drafts WHERE story_id=?",
                                          (rel["story_id"],)).fetchone()[0])
        article_rel = "greeneville/" + draft["slug"] + ".html"
        stage_dir = BUILD_ROOT / ("release-" + release_id)
        if not stage_dir.is_dir():
            raise GateError("staged site unavailable")
        bundle_path = self.private_dir / "manifests" / (release_id + ".release-bundle.json")
        bundle = json.loads(bundle_path.read_text())
        for f in bundle["paths"]:
            if sha256((stage_dir/f["path"]).read_bytes()).hexdigest() != f["sha256"]:
                raise GateError("release bundle integrity failure")
        # Deliberately use a fresh temporary mock, NOT a real website or GitHub API.
        with tempfile.TemporaryDirectory(prefix="ds-mock-release-",dir=str(self.private_dir)) as tmp:
            sandbox=Path(tmp)
            for f in bundle["paths"]:
                source=stage_dir/f["path"]
                target=sandbox/f["path"]
                target.parent.mkdir(exist_ok=True,parents=True)
                shutil.copy2(source,target)
            class QuietHandler(http.server.SimpleHTTPRequestHandler):
                def __init__(self,*args,**kwargs):
                    super().__init__(*args,directory=str(sandbox),**kwargs)
                def log_message(self,*_): pass
            server=http.server.ThreadingHTTPServer(("127.0.0.1",0),QuietHandler)
            t=threading.Thread(target=server.serve_forever,daemon=True)
            t.start()
            try:
                mock_url="http://127.0.0.1:"+str(server.server_port)+"/"+article_rel
                with urlopen(mock_url,timeout=5) as resp:
                    if resp.status != 200:
                        raise GateError("mock release HTTP verification failed")
                    content=resp.read(500_000)
                expected=(stage_dir/article_rel).read_bytes()
                if content!=expected or sha256(content).hexdigest()!=rel["preview_sha"]:
                    raise GateError("mock release returned unexpected page bytes")
                if ('<link rel="canonical" href="'+rel["expected_url"]+'"').encode() not in content:
                    raise GateError("released article canonical mismatch")
                subject="SIMULATION ONLY — " + ("New post: " if rel["kind"]=="new" else "Updated post: ") + draft["title"]
                body=("NOT SENT. This is a mock publication-verification receipt.\n\n"
                      "Article: "+draft["title"]+"\nProposed public URL: "+rel["expected_url"]+
                      "\nMock HTTP check: status 200 and exact staged bytes.\n"
                      "No real website change or email occurred.")
                with self._transaction() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current=db.execute("SELECT state FROM releases WHERE release_id=?",(release_id,)).fetchone()
                    if current["state"]!="staged":
                        raise GateError("release state changed concurrently")
                    db.execute("UPDATE releases SET state='simulated',updated_at=? WHERE release_id=?",
                               (utc_text(at),release_id))
                    db.execute("""INSERT INTO simulated_published(story_id,slug,payload_json,first_simulated_at,updated_at)
                        VALUES(?,?,?,?,?)
                        ON CONFLICT(story_id) DO UPDATE SET payload_json=excluded.payload_json,
                            updated_at=excluded.updated_at""",
                        (rel["story_id"],draft["slug"],canon(public_story_payload(draft)),utc_text(at),utc_text(at)))
                    db.execute("""INSERT INTO notification_previews(release_id,status,subject,body,mock_url,
                        proposed_public_url,prepared_at) VALUES(?,'NOT_SENT',?,?,?,?,?)""",
                        (release_id,subject,body,"loopback-HTTP-200-verified",rel["expected_url"],utc_text(at)))
                return {"release_id":release_id,"mock_http":200,"expected_sha256":rel["preview_sha"],
                        "replay":False,"kind":rel["kind"],"email_status":"NOT_SENT",
                        "live_published":False,"proposed_public_url":rel["expected_url"]}
            finally:
                server.shutdown()
                server.server_close()

    def queue(self) -> dict:
        """Private editorial handoff: writer drafts awaiting independent review."""
        with self._transaction() as db:
            records=[]
            for r in db.execute("""
                SELECT d.story_id,d.slug,d.writer_id,d.payload_sha,
                       r.verdict,r.reviewer_id
                FROM drafts d LEFT JOIN reviews r ON
                r.story_id=d.story_id AND r.payload_sha=d.payload_sha
                ORDER BY d.created_at ASC LIMIT 100""").fetchall():
                records.append({
                    "story_id":r["story_id"],"slug":r["slug"],"writer_id":r["writer_id"],
                    "current_payload_sha256":r["payload_sha"],
                    "review":r["verdict"] or "needs_review",
                    "reviewer_id":r["reviewer_id"]
                })
            return {"mode":"private-editorial-staging","count":len(records),
                    "records":records,"public_deployment_enabled":False}

    def status(self, at: datetime) -> dict:
        day=at.astimezone(EASTERN).date().isoformat()
        with self._transaction() as db:
            counts={x["state"]:x["n"] for x in db.execute("SELECT state,COUNT(*) n FROM releases GROUP BY state")}
            new_count=db.execute("""SELECT COUNT(*) FROM releases WHERE kind='new' AND local_date=?
                AND state IN ('reserved','staged','simulated')""",(day,)).fetchone()[0]
            outbox=db.execute("SELECT COUNT(*) FROM notification_previews").fetchone()[0]
            return {"mode":"simulation-only","local_date":day,
                    "new_posts_reserved_or_simulated":new_count,
                    "new_posts_remaining":max(0,MAX_NEW_PER_DAY-new_count),
                    "daily_target":DAILY_TARGET,"daily_max":MAX_NEW_PER_DAY,
                    "releases":counts,"notification_previews_not_sent":outbox,
                    "live_posts_verified":0,"actual_emails_sent":0}