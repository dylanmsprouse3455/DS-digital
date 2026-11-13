#!/usr/bin/env python3
"""Checkpoint 005: prepare a guarded GitHub release candidate, with NO remote writes.

Inputs: approved Checkpoint 004 simulated release bundle + current local main
checkout. Output: private local candidate commit and provenance/rollback plan.
There is deliberately no git push, hosting deploy, or email send action.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

BOOTSTRAP_ASSETS = ("assets/css/blog-local.css", "assets/js/blog-local.js")
BASE_DELTA = ("blog-v2.html", "sitemap.xml")
ARTICLE = re.compile(r"greeneville/[a-z0-9]+(?:-[a-z0-9]+)*\.html\Z")


class ReleaseBlocker(ValueError):
    pass


def cmd(*args: str, cwd: Path, check: bool = True) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                            timeout=60, check=False)
    if check and result.returncode != 0:
        raise ReleaseBlocker(f"git command failed: {args[1]} (exit {result.returncode}): {result.stderr[:240]}")
    return result.stdout.strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixed_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ReleaseBlocker("invalid release path")
    p = PurePosixPath(value)
    if str(p) != value or p.is_absolute() or ".." in p.parts:
        raise ReleaseBlocker("release path traversal not permitted")
    if value in BASE_DELTA or ARTICLE.fullmatch(value):
        return value
    raise ReleaseBlocker(f"release file not in allowed blog delta: {value}")


def _atomic_json(file: Path, data: dict) -> None:
    temporary = file.with_suffix(file.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(file)


@dataclass
class Candidate:
    root: Path
    commit_sha: str
    base_sha: str
    file_paths: list[str]
    report: dict


def prepare_candidate(
    main_checkout: Path, staged_build: Path, bundle_path: Path,
    source_repo: Path, private_output: Path, expected_main_sha: str
) -> Candidate:
    """Assemble a *local* commit based on the exact previously observed main.

    Local main checkout and source repo must be independent Git worktrees.
    Outputs stay in a private scratch directory outside both repositories.
    """
    main = main_checkout.resolve()
    build = staged_build.resolve()
    source = source_repo.resolve()
    target = private_output.resolve()
    if target == main or target.is_relative_to(main) or target == source or target.is_relative_to(source):
        raise ReleaseBlocker("private candidate must be outside Git checkouts")
    if main == source:
        raise ReleaseBlocker("main and source checkouts must be different")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_main_sha):
        raise ReleaseBlocker("valid full pinned main SHA required")
    if not main.is_dir() or not build.is_dir() or not source.is_dir():
        raise ReleaseBlocker("missing local main checkout, build or source")
    current_sha = cmd("git", "rev-parse", "HEAD", cwd=main)
    branch = cmd("git", "branch", "--show-current", cwd=main)
    if branch != "main" or current_sha != expected_main_sha:
        raise ReleaseBlocker("main has moved or wrong baseline branch")
    if cmd("git", "status", "--porcelain", cwd=main):
        raise ReleaseBlocker("main checkout has uncommitted changes")
    if cmd("git", "status", "--porcelain", cwd=source):
        raise ReleaseBlocker("source branch has uncommitted changes")
    raw = json.loads(bundle_path.read_text(encoding="utf-8"))
    if raw.get("mode") != "SIMULATION_ONLY" or not re.fullmatch(r"[0-9a-f]{32}",raw.get("release_id","")):
        raise ReleaseBlocker("not a valid independently staged release bundle")
    entries = raw.get("paths")
    if not isinstance(entries, list) or len(entries) < 3 or len(entries) > 35:
        raise ReleaseBlocker("release bundle count out of range")
    files: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ReleaseBlocker("malformed release entry")
        name = fixed_path(item.get("path"))
        if name in files:
            raise ReleaseBlocker("duplicate release file")
        path = build / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(build):
            raise ReleaseBlocker("staged release file missing or symlinked")
        data = path.read_bytes()
        if sha256(data) != item.get("sha256") or len(data) != item.get("bytes"):
            raise ReleaseBlocker("staged file hashes do not match verified bundle")
        files.append(name)
    if not all(x in files for x in BASE_DELTA) or not any(ARTICLE.fullmatch(x) for x in files):
        raise ReleaseBlocker("blog index, sitemap and at least one article required")
    public_url = raw.get("proposed_public_url")
    if not isinstance(public_url, str):
        raise ReleaseBlocker("public target URL missing")
    parsed = urlsplit(public_url)
    expected_article_path = parsed.path.lstrip("/")
    if (parsed.scheme != "https" or parsed.netloc != "dsdigitaldesigns.org"
            or parsed.query or parsed.fragment or not ARTICLE.fullmatch(expected_article_path)
            or expected_article_path not in files):
        raise ReleaseBlocker("public URL must refer to an included canonical article")
    expected_article = (build / expected_article_path).read_text(encoding="utf-8")
    if ('<link rel="canonical" href="'+public_url+'"') not in expected_article:
        raise ReleaseBlocker("stage article canonical URL mismatch")
    # The first production deployment must include the currently missing
    # stylesheet and client-side search/filter JS.
    bootstrap = []
    for name in BOOTSTRAP_ASSETS:
        if not (main / name).is_file():
            source_asset = source / name
            if not source_asset.is_file() or source_asset.is_symlink():
                raise ReleaseBlocker("required blog bootstrap asset is missing")
            bootstrap.append(name)
        else:
            # Existing production assets must not silently be overwritten.
            # Explicit migration is a different approval, not this release.
            source_asset = source / name
            if source_asset.is_file() and source_asset.read_bytes() != (main / name).read_bytes():
                raise ReleaseBlocker("existing blog bootstrap asset differs from staging; review required")
    allowed = sorted(files + bootstrap)
    if target.exists() or target.is_symlink():
        raise ReleaseBlocker("refusing to reuse candidate output directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700)
    # Copies main into private candidate. Local clone; NO push; NO worktree edits to main.
    clone = target / "git"
    cmd("git", "clone", "--quiet", "--no-hardlinks", "--branch", "main", str(main), str(clone), cwd=target)
    if cmd("git", "rev-parse", "HEAD", cwd=clone) != expected_main_sha:
        raise ReleaseBlocker("candidate clone base does not match pinned main")
    for name in allowed:
        original = (source / name) if name in bootstrap else (build / name)
        output = clone / name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, output)
    # Sanity check that the blog page references CSS and JS which now exist.
    html = (clone / "blog-v2.html").read_text(encoding="utf-8")
    for asset in BOOTSTRAP_ASSETS:
        if asset not in html or not (clone / asset).is_file():
            raise ReleaseBlocker(f"blog requires missing asset: {asset}")
    for name in allowed:
        if not (clone / name).is_file():
            raise ReleaseBlocker("candidate file vanished")
    cmd("git","add","--",*allowed,cwd=clone)
    changed = cmd("git","diff","--cached","--name-only",cwd=clone).splitlines()
    if not changed:
        raise ReleaseBlocker("no delta changes to publish")
    if sorted(changed) != sorted(allowed):
        raise ReleaseBlocker("candidate altered more or fewer files than authorized")
    cmd("git","-c","user.name=DS Digital Designs Staging",
        "-c","user.email=staging@localhost.invalid",
        "commit","--quiet","-m",f"PROPOSED ONLY: local blog release {raw['release_id']}",cwd=clone)
    candidate_sha = cmd("git","rev-parse","HEAD",cwd=clone)
    if cmd("git","rev-parse","HEAD^",cwd=clone) != expected_main_sha:
        raise ReleaseBlocker("candidate must be a direct child of pinned main")
    if cmd("git","status","--porcelain",cwd=clone):
        raise ReleaseBlocker("candidate Git checkout is dirty")
    fingerprint = {name:sha256((clone/name).read_bytes()) for name in allowed}
    report = {
        "mode":"RELEASE_CANDIDATE_NOT_PUBLISHED",
        "release_id":raw["release_id"],
        "pinned_main_sha":expected_main_sha,
        "candidate_commit_sha":candidate_sha,
        "changed_files":allowed,
        "sha256_by_file":fingerprint,
        "proposed_url":raw["proposed_public_url"],
        "rollback_plan":{
            "baseline_main_sha":expected_main_sha,
            "strategy":"new git revert commit after verifying actual remote HEAD; never force-reset or clobber concurrent edits",
            "automatic_rollback_executed":False
        },
        "remote_deployment_permitted":False,
        "email_delivery_permitted":False,
        "published_verification":False,
        "created_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _atomic_json(target/"candidate.json",report)
    return Candidate(root=target,commit_sha=candidate_sha,
                     base_sha=expected_main_sha,file_paths=allowed,report=report)