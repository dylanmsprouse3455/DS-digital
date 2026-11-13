#!/usr/bin/env python3
"""Checkpoint 005: gated, durable post-publication notification outbox.

NO Gmail sending here. Actual Gmail invocation must be performed by an
approved connected task after owner activation. Only a *real* HTTPS probe of
the exact published page creates a verified outbox entry; unit tests inject
mock responses. Ambiguous sends are never retried automatically.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import os
import sqlite3
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler


class DeliveryBlocker(ValueError):
    pass


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, newurl):
        raise DeliveryBlocker("public verification redirects are not followed")


SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
  release_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  expected_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('verified','sending','sent','uncertain')),
  verified_at TEXT NOT NULL,
  last_changed TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  gmail_message_id TEXT,
  CHECK((status='sent' AND gmail_message_id IS NOT NULL) OR
        (status!='sent' AND gmail_message_id IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_notifications_status ON notifications(status);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_target(url: str) -> str:
    if not isinstance(url,str) or len(url)>500:
        raise DeliveryBlocker("missing or oversized article URL")
    parsed=urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "dsdigitaldesigns.org" or parsed.query or parsed.fragment:
        raise DeliveryBlocker("only the canonical HTTPS domain can be verified")
    if not re.fullmatch(r"/greeneville/[a-z0-9]+(?:-[a-z0-9]+)*\.html", parsed.path):
        raise DeliveryBlocker("URL is not a local article URL")
    return url


def read_public_article(url: str, expected_sha256: str, fetch=None) -> dict:
    """Verify final public HTTPS URL, status and exact static article bytes.

    fetch injects a mocked opener in tests; production uses urllib.request.urlopen.
    An HTTP 200 from localhost is not eligible for this production verification.
    """
    validate_target(url)
    if not isinstance(expected_sha256,str) or not re.fullmatch(r"[a-f0-9]{64}",expected_sha256):
        raise DeliveryBlocker("expected release content SHA-256 required")
    opener=fetch or build_opener(RejectRedirect()).open
    request=Request(url,headers={"User-Agent":"DSDigitalDesignsReleaseVerifier/0.1","Accept":"text/html"})
    try:
        response=opener(request,timeout=15)
        with response as r:
            if r.geturl()!=url:
                raise DeliveryBlocker("redirected public URL differs from expected canonical")
            if r.status!=200:
                raise DeliveryBlocker("public page does not return HTTP 200")
            body=r.read(500_001)
            if len(body)>500_000:
                raise DeliveryBlocker("public article exceeds verification size bound")
            if r.headers.get_content_type()!="text/html":
                raise DeliveryBlocker("public article is not HTML")
    except (OSError,TimeoutError) as exc:
        raise DeliveryBlocker("public URL cannot be verified") from exc
    if sha256(body).hexdigest()!=expected_sha256:
        raise DeliveryBlocker("public article bytes differ from the approved release")
    canonical=('<link rel="canonical" href="'+url+'"').encode()
    if canonical not in body:
        raise DeliveryBlocker("canonical HTML does not match intended URL")
    return {"url":url,"sha256":expected_sha256,"response_code":200,
            "verified_at":utc_now(),"public_bytes":len(body)}


class NotificationOutbox:
    """State machine for approved later use; never performs Gmail calls."""

    def __init__(self, state_dir: Path):
        path=Path(state_dir)
        root=path.resolve()
        if path.is_symlink() or root == Path("/"):
            raise DeliveryBlocker("unsafe outbox state directory")
        repo=Path(__file__).resolve().parents[1]
        if root==repo or root.is_relative_to(repo) or ".git" in root.parts:
            raise DeliveryBlocker("outbox must be outside the Git repository")
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(root,0o700)
        self.root=root
        self.path=root/"notification-outbox.sqlite3"
        if self.path.is_symlink():
            raise DeliveryBlocker("outbox DB symlink rejected")
        with self.transaction() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        os.chmod(self.path,0o600)
        db.row_factory=sqlite3.Row
        try:
            yield db
            db.commit()
        except:
            db.rollback()
            raise
        finally:
            db.close()

    def verify_and_queue(
        self,release_id: str,url: str,expected_sha256: str,
        title: str, fetch=None
    ) -> dict:
        if not isinstance(release_id,str) or not re.fullmatch("[a-f0-9]{32}",release_id):
            raise DeliveryBlocker("invalid release ID")
        if not isinstance(title,str) or not 5<=len(title)<=180:
            raise DeliveryBlocker("article title required")
        # Network proof must be obtained *before* enqueue.
        verified=read_public_article(url,expected_sha256,fetch)
        subject="New DS Digital Designs article: "+title
        body=("A new local article has been published and verified.\n\n"
              +title+"\n"+url+"\n\n"
              +"Verified HTTP 200 with matching released content hash.")
        with self.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            existing=db.execute("SELECT * FROM notifications WHERE release_id=?",(release_id,)).fetchone()
            if existing:
                if existing["url"]!=url or existing["expected_sha256"]!=expected_sha256:
                    raise DeliveryBlocker("release ID already has a different published receipt")
                return {"release_id":release_id,"status":existing["status"],
                        "new":False,"public_page_verified":True}
            db.execute("""INSERT INTO notifications
                (release_id,url,expected_sha256,status,verified_at,last_changed,subject,body)
                VALUES(?,?,?,'verified',?,?,?,?)""",
                (release_id,url,expected_sha256,verified["verified_at"],
                 verified["verified_at"],subject,body))
        return {"release_id":release_id,"status":"verified","new":True,"public_page_verified":True}

    def claim(self,release_id: str) -> dict:
        """One caller may obtain the send-intent; no automatic retries."""
        with self.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM notifications WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"]!="verified":
                raise DeliveryBlocker("send not available: already claimed, sent, uncertain, or unverified")
            db.execute("UPDATE notifications SET status='sending',last_changed=? WHERE release_id=?",
                       (utc_now(),release_id))
            return {"release_id":release_id,"subject":row["subject"],"body":row["body"],
                    "url":row["url"],"delivery_status":"SENDING_NOT_YET_SENT"}

    def record_sent(self,release_id: str,gmail_message_id: str) -> None:
        """Caller must pass a real Gmail connector response ID, after actual send."""
        if not isinstance(gmail_message_id,str) or not re.fullmatch("[a-zA-Z0-9_-]{8,256}",gmail_message_id):
            raise DeliveryBlocker("Gmail connector message ID required")
        with self.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM notifications WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"]!="sending":
                raise DeliveryBlocker("no active send attempt to confirm")
            db.execute("UPDATE notifications SET status='sent',gmail_message_id=?,last_changed=? WHERE release_id=?",
                       (gmail_message_id,utc_now(),release_id))

    def mark_uncertain(self,release_id: str,reason: str) -> None:
        """Ambiguous connector failure: stop; reconcile Gmail before retrying."""
        if not isinstance(reason,str) or len(reason.strip())<8:
            raise DeliveryBlocker("a meaningful delivery diagnostic is required")
        with self.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT status FROM notifications WHERE release_id=?",(release_id,)).fetchone()
            if not row or row["status"]!="sending":
                raise DeliveryBlocker("no in-progress send to mark uncertain")
            db.execute("UPDATE notifications SET status='uncertain',last_changed=? WHERE release_id=?",
                       (utc_now(),release_id))

    def status(self) -> list[dict]:
        with self.transaction() as db:
            return [
                {"release_id":r["release_id"],"status":r["status"],
                 "url":r["url"],"gmail_id_present":r["gmail_message_id"] is not None}
                for r in db.execute("SELECT * FROM notifications ORDER BY verified_at")
            ]