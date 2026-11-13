#!/usr/bin/env python3
"""DS Digital Designs pilot production ledger — durable release gate, not a deployer.

Rules:
- America/New_York daily cap: four new posts across this publishing pipeline.
- Must validate the independently approved exact draft against immutable raw evidence.
- Must verify that a clean local main matches the independently observed remote SHA.
- First initialization refuses an unknown existing local-article inventory.
- Never auto-clear ambiguous reservations after crashes or network failures.
- No GitHub writes, production deployment, notifications, or schedules in this file.

A repository writer bypassing this ledger cannot be controlled by software here.
Unexpected main changes therefore block the next pilot until reconciled.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from zoneinfo import ZoneInfo

from release_coordinator import require_source_evidence, public_story_payload, digest
from verified_notification import read_public_article, DeliveryBlocker

TZ = ZoneInfo("America/New_York")
MAX_DAILY_NEW = 4
DEFAULT_ROOT = Path("/var/lib/kali-ai-remote/ds-blog-production-pilot-state-006")
ARTICLE = re.compile(r"greeneville/[a-z0-9]+(?:-[a-z0-9]+)*\.html\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
H64 = re.compile(r"[0-9a-f]{64}\Z")

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS control (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS release_intents (
  release_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  slug TEXT NOT NULL,
  payload_sha TEXT NOT NULL,
  local_day TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('new','update')),
  status TEXT NOT NULL CHECK(status IN (
    'reserved','prepared','publishing','live_verified','notified',
    'uncertain','aborted')),
  expected_main_sha TEXT NOT NULL,
  proposed_url TEXT NOT NULL,
  desired_html_sha TEXT,
  candidate_commit_sha TEXT,
  observed_remote_commit TEXT,
  approved_reviewer TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  error TEXT,
  UNIQUE(story_id, payload_sha)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_first_new_per_story
  ON release_intents(story_id) WHERE kind='new' AND status!='aborted';
CREATE UNIQUE INDEX IF NOT EXISTS ix_first_slug
  ON release_intents(slug) WHERE kind='new' AND status!='aborted';
CREATE INDEX IF NOT EXISTS ix_new_per_day
  ON release_intents(local_day,kind,status);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  release_id TEXT, action TEXT NOT NULL, at TEXT NOT NULL,
  main_sha TEXT, detail TEXT NOT NULL
);
"""

class QuotaBlocked(ValueError):
    pass

def utc_text(at: datetime) -> str:
    if not isinstance(at,datetime) or at.tzinfo is None:
        raise QuotaBlocked("timezone-aware datetime is required")
    return at.isoformat(timespec="seconds")

def run_git(cwd: Path,*args: str) -> str:
    p=subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,timeout=30)
    if p.returncode:
        raise QuotaBlocked("read-only Git inspection failed: "+args[0])
    return p.stdout.strip()

def inspect_current_main(local_main: Path, remotely_observed_main_sha: str) -> tuple[str,set[str]]:
    """Fail closed unless local checkout exactly matches independently read remote head."""
    path=Path(local_main).resolve()
    if not path.is_dir() or not SHA.fullmatch(remotely_observed_main_sha):
        raise QuotaBlocked("main checkout or independently observed SHA missing")
    sha=run_git(path,"rev-parse","HEAD")
    if (run_git(path,"branch","--show-current")!="main"
            or run_git(path,"status","--porcelain")
            or sha!=remotely_observed_main_sha):
        raise QuotaBlocked("clean main checkout does not match the observed remote main")
    inventory=set(run_git(path,"ls-tree","-r","--name-only","HEAD").splitlines())
    articles={p for p in inventory if ARTICLE.fullmatch(p)}
    return sha,articles

def verified_editorial_record(editorial_db: Path, collector_db: Path, story_id: str) -> dict:
    if not Path(editorial_db).is_file() or not Path(collector_db).is_file():
        raise QuotaBlocked("approved editorial ledger or raw collector unavailable")
    with closing(sqlite3.connect("file:"+str(Path(editorial_db).resolve())+"?mode=ro",uri=True)) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        row=db.execute("SELECT * FROM drafts WHERE story_id=?",(story_id,)).fetchone()
        if not row:
            raise QuotaBlocked("no private draft exists for story")
        approval=db.execute("""
            SELECT reviewer_id,verdict FROM reviews
            WHERE story_id=? AND payload_sha=?
            """,(story_id,row["payload_sha"])).fetchone()
        if not approval or approval["verdict"]!="approved" or approval["reviewer_id"]==row["writer_id"]:
            raise QuotaBlocked("current draft lacks a distinct editor's approval")
        story=json.loads(row["payload_json"])
        if digest(story)!=row["payload_sha"]:
            raise QuotaBlocked("saved draft digest mismatch")
        if story["sensitive"] is not False:
            raise QuotaBlocked("sensitive story requires human escalation")
        if story.get("publication_status")!="draft":
            raise QuotaBlocked("writer cannot pre-approve public publication")
        public_story_payload(story)
        try:
            require_source_evidence(story,Path(collector_db))
        except Exception as exc:
            raise QuotaBlocked("current draft evidence re-verification failed") from exc
        return {"story":story,"payload_sha":row["payload_sha"],
                "reviewer_id":approval["reviewer_id"]}

class ProductionLedger:
    def __init__(self, directory: Path):
        root=Path(directory).resolve()
        repo=Path(__file__).resolve().parents[1]
        if root==repo or root.is_relative_to(repo) or root==Path("/") or Path(directory).is_symlink():
            raise QuotaBlocked("quota ledger must live privately outside source checkout")
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(root,0o700)
        self.root=root
        self.path=root/"publication-ledger.sqlite3"
        if self.path.is_symlink():
            raise QuotaBlocked("quota database cannot be a symlink")
        with self.tx() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        db=sqlite3.connect(str(self.path),isolation_level=None,timeout=15)
        os.chmod(self.path,0o600)
        db.row_factory=sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def inspect(self,at: datetime) -> dict:
        day=at.astimezone(TZ).date().isoformat()
        with self.tx() as db:
            ct=db.execute("""SELECT count(*) FROM release_intents WHERE local_day=?
                AND kind='new' AND status!='aborted'""",(day,)).fetchone()[0]
            live=db.execute("""SELECT count(*) FROM release_intents
                WHERE local_day=? AND kind='new' AND status IN ('live_verified','notified')""",(day,)).fetchone()[0]
            intents=[dict(r) for r in db.execute(
                "SELECT release_id,story_id,slug,kind,status,local_day FROM release_intents ORDER BY created_at")]
            state=db.execute("SELECT value FROM control WHERE key='verified_main_sha'").fetchone()
        return {"mode":"LIVE_VERIFIED_PILOT" if live > 0 else "GUARDED_NO_LIVE_RELEASE_YET","date_eastern":day,
                "slots_reserved_or_live":ct,"new_verified_live":live,
                "daily_new_cap":MAX_DAILY_NEW,
                "remaining_slots":max(0,MAX_DAILY_NEW-ct),
                "verified_main_sha":state["value"] if state else None,
                "intents":intents}

    def initialize_verified_baseline(self,local_main: Path,observed_remote_sha: str,at: datetime) -> dict:
        sha,articles=inspect_current_main(local_main,observed_remote_sha)
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            previous=db.execute("SELECT value FROM control WHERE key='verified_main_sha'").fetchone()
            if previous:
                if previous["value"]!=sha:
                    raise QuotaBlocked("remote main changed: require an explicit historical reconciliation")
                return {"baseline_sha":sha,"existing_local_pages":len(articles),"new":False}
            if articles:
                raise QuotaBlocked("unknown pre-existing article inventory: manually reconcile historical publications first")
            db.execute("INSERT INTO control(key,value) VALUES('verified_main_sha',?)",(sha,))
            db.execute("INSERT INTO control(key,value) VALUES('initialized_at',?)",(utc_text(at),))
            db.execute("INSERT INTO audit(action,at,main_sha,detail) VALUES('init',?,?,'verified empty local article inventory')",(utc_text(at),sha))
            return {"baseline_sha":sha,"existing_local_pages":0,"new":True}

    def reserve_approved(
        self, story_id: str, local_main: Path, observed_remote_sha: str,
        editorial_db: Path, collector_db: Path, at: datetime
    ) -> dict:
        sha,live_articles=inspect_current_main(local_main,observed_remote_sha)
        approved=verified_editorial_record(editorial_db,collector_db,story_id)
        story=approved["story"]
        path="greeneville/"+story["slug"]+".html"
        if path in live_articles:
            raise QuotaBlocked("this pilot only supports first-time new articles, not updates")
        day=at.astimezone(TZ).date().isoformat()
        release_id=hashlib.sha256(("production:"+story_id+":"+approved["payload_sha"]).encode()).hexdigest()[:32]
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            current=db.execute("SELECT value FROM control WHERE key='verified_main_sha'").fetchone()
            if not current or current["value"]!=sha:
                raise QuotaBlocked("production main not initialized or changed since verified baseline")
            earlier=db.execute("SELECT * FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if earlier:
                return {"release_id":release_id,"status":earlier["status"],"replay":True,
                        "daily_remaining":self._remaining(db,day)}
            if db.execute("""SELECT 1 FROM release_intents WHERE story_id=? AND kind='new'
                               AND status!='aborted'""",(story_id,)).fetchone():
                raise QuotaBlocked("this story already has a new-post reservation")
            if db.execute("""SELECT 1 FROM release_intents WHERE slug=? AND kind='new'
                               AND status!='aborted'""",(story["slug"],)).fetchone():
                raise QuotaBlocked("canonical slug is reserved for another story")
            if self._remaining(db,day)==0:
                raise QuotaBlocked("four new daily slots are already occupied or uncertain")
            url="https://dsdigitaldesigns.org/"+path
            db.execute("""INSERT INTO release_intents
              (release_id,story_id,slug,payload_sha,local_day,kind,status,
               expected_main_sha,proposed_url,approved_reviewer,created_at,updated_at)
               VALUES(?,?,?,?,?,'new','reserved',?,?,?,?,?)""",
               (release_id,story_id,story["slug"],approved["payload_sha"],day,sha,
                url,approved["reviewer_id"],utc_text(at),utc_text(at)))
            db.execute("INSERT INTO audit(release_id,action,at,main_sha,detail) VALUES(?,'reserved',?,?,?)",
                       (release_id,utc_text(at),sha,"approved source-linked new article"))
            return {"release_id":release_id,"status":"reserved","replay":False,
                    "daily_remaining":self._remaining(db,day),"url":url}

    @staticmethod
    def _remaining(db: sqlite3.Connection,day: str) -> int:
        occupied=db.execute("""SELECT COUNT(*) FROM release_intents
               WHERE kind='new' AND local_day=? AND status!='aborted'""",(day,)).fetchone()[0]
        return max(0,MAX_DAILY_NEW-occupied)

    def prepared(self,release_id: str, commit_sha: str,html_sha: str,at: datetime) -> None:
        if not SHA.fullmatch(commit_sha) or not H64.fullmatch(html_sha):
            raise QuotaBlocked("validated commit/hash required")
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            rel=db.execute("SELECT * FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if not rel or rel["status"]!="reserved":
                raise QuotaBlocked("release must be reserved first")
            db.execute("""UPDATE release_intents SET status='prepared',
                candidate_commit_sha=?,desired_html_sha=?,updated_at=? WHERE release_id=?""",
                (commit_sha,html_sha,utc_text(at),release_id))
            db.execute("INSERT INTO audit(release_id,action,at,main_sha,detail) VALUES(?,'prepared',?,?,?)",
                       (release_id,utc_text(at),rel["expected_main_sha"],"candidate hash pinned"))

    def publishing(self,release_id: str,at: datetime) -> None:
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"]!="prepared":
                raise QuotaBlocked("release must be prepared before public push")
            db.execute("UPDATE release_intents SET status='publishing',updated_at=? WHERE release_id=?",
                       (utc_text(at),release_id))

    def mark_uncertain(self,release_id: str,reason: str,at: datetime) -> None:
        if not isinstance(reason,str) or len(reason.strip())<8:
            raise QuotaBlocked("meaningful failure reason required")
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"] not in ("publishing","prepared","reserved"):
                raise QuotaBlocked("only in-flight release may become uncertain")
            db.execute("UPDATE release_intents SET status='uncertain',error=?,updated_at=? WHERE release_id=?",
                       (reason,utc_text(at),release_id))
            db.execute("INSERT INTO audit(release_id,action,at,detail) VALUES(?,'uncertain',?,?)",
                       (release_id,utc_text(at),reason))

    def live_verified(self,release_id: str,at: datetime,
                      *, fetch=None, remote_main_getter=None) -> dict:
        """Independently verify BOTH live GitHub main and real HTTPS article bytes.

        fetch/remote_main_getter are injectable only by unit tests; production
        uses the actual remote GitHub branch and public HTTPS response.
        """
        with self.tx() as db:
            row=db.execute("SELECT * FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"]!="publishing" or not row["candidate_commit_sha"] or not row["desired_html_sha"]:
                raise QuotaBlocked("public verification requires prepared in-flight release")
            expected_commit=row["candidate_commit_sha"]
            url=row["proposed_url"]
            expected_hash=row["desired_html_sha"]
        if remote_main_getter is None:
            response=subprocess.run(
                ["git","ls-remote","https://github.com/dylanmsprouse3455/DS-digital.git","refs/heads/main"],
                capture_output=True,text=True,timeout=15)
            if response.returncode:
                raise QuotaBlocked("unable to read remote GitHub main revision")
            observed=response.stdout.split()[0] if response.stdout.strip() else ""
        else:
            observed=remote_main_getter()
        if observed!=expected_commit:
            raise QuotaBlocked("GitHub main does not match prepared commit")
        try:
            proof=read_public_article(url,expected_hash,fetch=fetch)
        except (DeliveryBlocker,OSError) as exc:
            raise QuotaBlocked("public HTTPS page verification failed") from exc
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if row["status"]!="publishing" or row["candidate_commit_sha"]!=observed:
                raise QuotaBlocked("public release state changed during verification")
            db.execute("""UPDATE release_intents SET status='live_verified',
              observed_remote_commit=?,updated_at=? WHERE release_id=?""",
              (observed,utc_text(at),release_id))
            db.execute("UPDATE control SET value=? WHERE key='verified_main_sha'",(observed,))
            db.execute("INSERT INTO audit(release_id,action,at,main_sha,detail) VALUES(?,'live_verified',?,?,'remote main and live HTTPS both confirmed')",
                       (release_id,utc_text(at),observed))
        return {"release_id":release_id,"public_main_sha":observed,
                "verified_url":url,"page_sha256":expected_hash,
                "public_http":proof["response_code"]}

    def mark_notified(self,release_id: str,outbox_db: Path,at: datetime) -> dict:
        """Close the release only after the private Gmail outbox confirms send.

        Does not call Gmail; reads the outbox's actual persisted sent receipt.
        """
        path=Path(outbox_db)
        if not path.is_file() or path.is_symlink():
            raise QuotaBlocked("Gmail outbox receipt database unavailable")
        with closing(sqlite3.connect("file:"+str(path.resolve())+"?mode=ro",uri=True)) as mail_db:
            mail_db.row_factory=sqlite3.Row
            mail_db.execute("PRAGMA query_only=ON")
            receipt=mail_db.execute(
                "SELECT * FROM notifications WHERE release_id=?",(release_id,)).fetchone()
            if (not receipt or receipt["status"]!="sent" or
                    not receipt["gmail_message_id"]):
                raise QuotaBlocked("no confirmed Gmail sent-message receipt")
            with self.tx() as db:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute("SELECT * FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
                if not row or row["status"] not in ("live_verified","notified"):
                    raise QuotaBlocked("live article must be verified before notification completes")
                if (receipt["url"]!=row["proposed_url"] or
                        receipt["expected_sha256"]!=row["desired_html_sha"]):
                    raise QuotaBlocked("sent email does not refer to the verified article")
                if row["status"]=="live_verified":
                    db.execute("UPDATE release_intents SET status='notified',updated_at=? WHERE release_id=?",
                               (utc_text(at),release_id))
                    db.execute("INSERT INTO audit(release_id,action,at,main_sha,detail) VALUES(?,'notified',?,?,'Gmail sent receipt cross-checked with verified page')",
                               (release_id,utc_text(at),row["candidate_commit_sha"]))
                return {"release_id":release_id,"status":"notified",
                        "gmail_receipt_id_present":True,"public_url":row["proposed_url"]}

    def abort_unsubmitted(self,release_id: str,reason: str,at: datetime) -> None:
        if not isinstance(reason,str) or len(reason)<8:
            raise QuotaBlocked("reason required")
        with self.tx() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM release_intents WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"] not in ("reserved","prepared"):
                raise QuotaBlocked("cannot abort an in-flight or public release automatically")
            db.execute("UPDATE release_intents SET status='aborted',error=?,updated_at=? WHERE release_id=?",
                       (reason,utc_text(at),release_id))