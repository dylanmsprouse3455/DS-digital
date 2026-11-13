# DS Digital Designs — Checkpoint 009: Permission, Handoff, and Recovery Readiness

**Date:** November 12, 2026 (America/New_York)
**State:** OFFLINE / SAFE CHECKS COMPLETED — UNATTENDED PRODUCTION PUBLISHING NOT ACTIVATED.
**Development branch:** feature/ds-publishing-auth-recovery-009
**Staging checkout on connected Kali:** /var/lib/kali-ai-remote/ds-blog-checkpoint-009/
**All private production records and original source snapshots remain outside GitHub.**

## Boundaries honored

The user's approved scope was to verify real scheduled Writer-to-Editor access, implement and test dedicated publishing permissions, release locks, persistent Eastern-time quota, recovery/rollback, source-linked editorial evidence and Gmail verification while leaving public production unchanged.

This checkpoint:
- **Did not** merge, deploy or commit to GitHub main;
- **Did not** publish another article, email anyone, install a service, schedule a collector, or enable unattended publishing;
- **Did not** read or export existing secrets or create credentials, modify protected monitoring, Tailscale, Seagate, other projects, DNS or source databases;
- **Did not** impersonate a separate reviewer or pretend role labels prove credential separation.

## 1. REAL scheduled Writer run — VERIFIED

The original Writer automation (ID 6af653c250308191983a15e52dc0b466) has a verified provider-reported **completed** scheduled run:
- Scheduled for November 12, 2026 at 10:00 PM EST (2026-11-13 03:00Z);
- Started 03:04:53Z and completed 03:05:37Z;
- Source review read 4 existing official-source revisions;
- The writer correctly rejected insufficiently specific/old source-page text and did not manufacture a fifth news story or duplicate the already-published November 17 commission article;
- Its private, owner-only (0600) handoff receipt was written at 22:05:07 EST to:
  /var/lib/kali-ai-remote/ds-blog-continuous-private-008/handoff-probe/writer-receipt.json
- Receipt confirms the expected probe ID, role=writer, four read-only revisions and publication_performed=false;
- The private review cursor is at revision 4; no new article drafts.

The Editor automation (ID 6af653c34f208191894ecf1a46304445) had a previous completed 8:30 PM scheduled Kali read-only run, but had not yet independently acknowledged this *specific* 10 PM Writer receipt. The matching Editor acknowledgement was absent on disk at the last checkpoint check.

**Result: Writer unattended execution VERIFIED; full cross-run Writer→Editor private acknowledgement NOT YET VERIFIED.** The task schedules are unchanged.

## 2. Editorial identity permissions and signatures — STAGED

New code:
- scripts/signed_review.py
- scripts/role_audit.py
- tests/test_signed_review.py
- tests/test_role_audit.py
- ops/staged-policy/ROLE_CUSTODY_009.md

The signature verifier cryptographically checks an Ed25519 editorial attestation bound to the exact draft digest, source story ID, reviewer, repository, purpose, issue time and bounded expiry. Synthetic tests cover changed payload, forged reviewer, wrong key, tampering, expiry, replay on other stories, malformed input and file permissions.

Actual Kali role audit:
- current authorized remote process UID is 996 (kali-ai-remote);
- dedicated ds-blog-writer, ds-blog-editor, and ds-blog-publisher OS principals are **absent**;
- a separately provisioned editor signing key and pinned administrative public-key trust policy are **absent**;
- ChatGPT Writer and Editor are connected through a shared remote user, which is not a security/credential boundary.

The verifier is a staged component, NOT proof that live writing and reviewing identities are separated. The connected GitHub principal has admin and push privileges, broader than desirable for an autonomous publisher. No GitHub or Gmail credentials were copied or created here.

**Result: policy/test implementation complete; trusted dedicated identities and bounded credentials NOT provisioned.**

## 3. REAL-main Git rollback rehearsal — VERIFIED LOCALLY, NOT ON CDN

New code:
- scripts/recovery_plan.py
- tests/test_recovery_plan.py

The real public GitHub main remained:
4707b655ec2ad6958382a50761b9fdf699f9bb62

The immediately preceding pre-release main was:
9ac82e6a6997e678db2b01c96f6a9aec8c55331b

One read-only local clone of the actual current main was examined. A private local Git revert commit was prepared under:
  /var/lib/kali-ai-remote/ds-blog-c009-rollback-plan/

Five paths were verified exactly:
- blog-v2.html
- sitemap.xml
- assets/css/blog-local.css
- assets/js/blog-local.js
- greeneville/greeneville-historic-zoning-commission-november-17-2026.html

The local revert restored the prior full Git tree exactly, preserving all unrelated source files. It checked expected SHA, direct-parent ancestry, exactly allowed file paths, clean main, and rejection of intervening commits.

The private plan **cannot push or deploy** and explicitly requires new owner authorization before any public rollback. Live GitHub Pages/CDN propagation and recovery remain **untested**.

## 4. Durable publication quota and Gmail — CONFIRMED

The original production SQLite ledger, outside GitHub, still records exactly one actual published-and-notified article on November 12 Eastern, with a strict daily maximum of four; **three new-post slots remain**. Existing tests include transaction serialization, crashes, retries, duplicate prevention, and DST/Eastern-day limits.

The prior pilot Gmail message was independently re-read through connected Gmail and confirmed to have the **SENT** label, correct new-article subject, correct public URL and the connected account as recipient. No actual Gmail send took place in this checkpoint. Staged notification tests still enforce public HTTPS verification and no duplicate retries after ambiguous delivery.

The existing Writer and Editor tasks remain staging-only; one manually supervised pilot success does not establish unattended Gmail or GitHub OAuth scopes.

## 5. Central activation-readiness gate and disk safety — STAGED

New code:
- scripts/activation_readiness.py
- tests/test_activation_readiness.py

The read-only gate tests 14 conditions: distinct role custody, real scheduled Writer/Editor records, matching private receipt, signed approval, publisher GitHub/Gmail scope, quota, exact-tree recovery, CDN recovery, prior Gmail receipt, official source collector, reliable article quality, sustainable disk space, and separate owner activation.

Verified positive foundations: persistent quota, exact local rollback proof, prior Gmail receipt, and offline official-source collector.

At inspection root filesystem was **95% full with ~5.55 GiB free**. The staged readiness policy sets a conservative 10 GiB minimum for continuous collection before activation, without making any storage changes.

No owner activation files, services or new timers were created or enabled.

## 6. Testing

Checkpoint 009 tests plus all existing Checkpoint 008 and earlier regression tests:
- 260 Python tests — PASS
- 43 Chromium tests — PASS
- **Total: 303 / 303 PASS**

Tests use synthetic temporary keys, databases, articles, local Git remotes, mocked HTTP and email receipts. The one real GitHub rollback rehearsal was **read-only/local**. These tests are not a substitute for proof of safe, unattended production operation.

The original production main SHA was rechecked and unchanged. The real Writer receipt was inspected without altering it. No staging test modified the live website or sent a new email.

## 7. Remaining blockers before authorization to activate

1. The scheduled Editor must independently read and acknowledge the Writer's 10 PM private probe receipt; confirm via both actual unattended run record and matching private hash.
2. Provision truly separate editor, writer and publisher identities, protected signing key custody and immutable pinned public-key trust, rather than role-name strings under a shared UID.
3. Bind a single authorized, restricted publisher to the exact repo and its protected branch release controls. Confirm unattended Gmail permissions and exclusive source-change authority without exposing tokens.
4. Obtain approval for a bounded live CDN recovery test before claiming autonomous rollback readiness.
5. Validate real source extraction and editorial quality over independent recurring cycles. The current collector captures official page indexes only; an index-page revision is not itself a publishable story.
6. Resolve long-term free disk capacity (5.55 GiB available versus conservative 10 GiB staging requirement).
7. Separately authorize publication and collector activation only after the above checks pass. Keep the quality-gated daily target of one and the hard maximum of four new posts per America/New_York day.

**Final state:** One original public article remains live, the previous Gmail message remains sent, the continuous publishing machinery is staged and tested, but automatic collection and unattended publication are OFF.