#!/usr/bin/env python3
"""Checkpoint 005: simulated fast-forward publish and reversible local rollback.

Safety: accepts ONLY a local bare Git remote under a temporary directory
whose name begins ds-blog-transport-fixture-. It cannot push to GitHub,
ssh, https, a user repository, or any production branch.
"""
from __future__ import annotations
from pathlib import Path
import re
import subprocess
import tempfile


class TransportBlocked(ValueError):
    pass


def git(*args: str, cwd: Path) -> str:
    r=subprocess.run(["git",*args],cwd=cwd,capture_output=True,text=True,timeout=30)
    if r.returncode:
        raise TransportBlocked(f"local test Git action failed: {args[0]} {r.stderr.strip()[:220]}")
    return r.stdout.strip()


def verify_local_bare(remote: Path) -> Path:
    remote=Path(remote).resolve()
    temp_root=Path(tempfile.gettempdir()).resolve()
    if (not remote.is_relative_to(temp_root) or
        not any(part.startswith("ds-blog-transport-fixture-") for part in remote.relative_to(temp_root).parts) or
        not remote.is_dir() or (remote/".git").exists()):
        raise TransportBlocked("only an isolated local test bare remote is allowed")
    if git("rev-parse","--is-bare-repository",cwd=remote)!="true":
        raise TransportBlocked("test remote is not a bare Git repository")
    return remote


def get_branch_sha(remote: Path) -> str:
    return git("rev-parse","refs/heads/main",cwd=remote)


def simulated_fast_forward_push(candidate_git: Path, remote: Path,
                                pinned_main_sha: str) -> dict:
    remote=verify_local_bare(remote)
    checkout=Path(candidate_git).resolve()
    if not re.fullmatch("[a-f0-9]{40}",pinned_main_sha):
        raise TransportBlocked("invalid pinned SHA")
    base=get_branch_sha(remote)
    if base!=pinned_main_sha:
        raise TransportBlocked("main head changed since release was prepared")
    candidate_sha=git("rev-parse","HEAD",cwd=checkout)
    parent=git("rev-parse","HEAD^",cwd=checkout)
    if parent!=pinned_main_sha:
        raise TransportBlocked("candidate is not a direct child of baseline main")
    if git("status","--porcelain",cwd=checkout):
        raise TransportBlocked("candidate checkout is dirty")
    # Plain push, never --force. Git itself rejects a race / non-fast-forward.
    git("push",str(remote),candidate_sha+":refs/heads/main",cwd=checkout)
    actual=get_branch_sha(remote)
    if actual!=candidate_sha:
        raise TransportBlocked("test remote new commit not verified")
    return {"mode":"LOCAL_SIMULATION_ONLY","old_sha":base,"new_sha":actual,
            "simulated_published":True,"actual_live_published":False}


def simulated_revert_rollback(remote: Path, candidate_sha: str, original_sha: str) -> dict:
    remote=verify_local_bare(remote)
    if not re.fullmatch("[a-f0-9]{40}",candidate_sha) or not re.fullmatch("[a-f0-9]{40}",original_sha):
        raise TransportBlocked("invalid Git revision")
    if get_branch_sha(remote)!=candidate_sha:
        raise TransportBlocked("cannot roll back after intervening test commits")
    with tempfile.TemporaryDirectory(prefix="ds-blog-revert-") as tmp:
        git("clone","-q","--branch","main",str(remote),tmp,cwd=remote)
        checkout=Path(tmp)
        git("-c","user.name=DS Staging Test","-c","user.email=staging@localhost.invalid",
            "revert","--no-edit",candidate_sha,cwd=checkout)
        new_sha=git("rev-parse","HEAD",cwd=checkout)
        prior_tree=git("rev-parse",original_sha+"^{tree}",cwd=checkout)
        reverted_tree=git("rev-parse","HEAD^{tree}",cwd=checkout)
        if prior_tree!=reverted_tree:
            raise TransportBlocked("local revert did not restore old site tree")
        git("push",str(remote),new_sha+":refs/heads/main",cwd=checkout)
        if get_branch_sha(remote)!=new_sha:
            raise TransportBlocked("local rollback commit not verified")
    return {"mode":"LOCAL_SIMULATION_ONLY","rollback_commit":new_sha,
            "tree_restored":True,"live_rollback_executed":False}