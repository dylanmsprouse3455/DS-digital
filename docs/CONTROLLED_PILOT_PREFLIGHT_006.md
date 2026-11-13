# DS Digital Designs — Controlled Production Pilot Preflight 006

Date: November 12, 2026
Branch: feature/ds-production-pilot-preflight-006
Parent: feature/ds-blog-production-gates-checkpoint-005
Status: GUARDED PRIVATE PREFLIGHT — NOT PUBLISHED.

## Intent

Kali keeps raw records. The Writer drafts every two hours; a separate
Editor checks and eventually publishes; Traffic Watch checks analytics.
Target one useful new article a day if genuinely supported by evidence;
strict maximum four new articles per America/New_York calendar day.
Publish no manufactured filler. Email the actual live article URL only
after it is verified. Do not activate unattended publishing or new
collection schedules during this one-article pilot.

## Completed: Persistent production publication quota

scripts/production_quota.py and scripts/pilot_preflight.py implement a
private SQLite release ledger at:
/var/lib/kali-ai-remote/ds-blog-production-pilot-state-006/publication-ledger.sqlite3

The private directory is owner-only 0700, and the ledger file is 0600.
It was initialized after independently matching a clean local main
checkout to the actual remote GitHub main:
9ac82e6a6997e678db2b01c96f6a9aec8c55331b

At inspection, main had zero local-news article files. The current
Eastern date had 0 reserved/verified new articles and 4 available slots.
The database is durable, survives restarts, and uses transactional locks
for concurrent requests. It blocks an attempted fifth article, enforces
independent editor approval tied to immutable official source hashes,
rejects stale main commits, and never frees uncertain releases
automatically. The live_verified action independently checks actual
GitHub main SHA and exact HTTPS article bytes before it can record an
article as public.

This quota governs the single controlled publication pipeline. Writers
that bypass the ledger through unrelated direct repository permissions
remain outside its scope, so an exclusive release actor and main-branch
change reconciliation are necessary before unattended deployment.
The one-post minimum is a quality-gated target only.

22 new quota tests passed, including concurrency, Eastern midnight,
restarts, source evidence, stale main and crash/failure states.

## Completed: Authenticated GitHub release-path preflight

GitHub connector permissions were checked. On a NEW isolated branch
test/ds-blog-release-lease-preflight-006, branched from actual main,
the authorized GitHub tools successfully:
- created a tree containing one harmless documentation file only,
- committed with the actual main SHA as its parent,
- updated ONLY that test branch using expected_sha and force=false,
- verified the exact resulting difference against main.

The isolated test branch has exactly one new documentation file and
is one commit ahead of unchanged main. The preflight does not
test a real public website deployment or live rollback.

Branch: https://github.com/dylanmsprouse3455/DS-digital/tree/test/ds-blog-release-lease-preflight-006

Prior Checkpoint 005 already tested a local-only fast-forward and
revert rollback. Production GitHub Pages/CDN propagation remains untested.

## Completed: Real independently sourced editorial DRAFT (NOT published)

Town of Greeneville official pages used:
https://www.greenevilletn.gov/events
https://www.greenevilletn.gov/page/historic-zoning-commission

Live Chromium verified the November 17, 2026 Historic Zoning
Commission meeting scheduled from 8:30–9:30 a.m. at Greeneville Energy
Authority, in the G. Thomas Love Board Room, 110 N. College St.
The Town event calendar states commission members' November 10 visit
to 300 N. Main Street to examine the rear of a house was to evaluate
a requested alteration; no formal vote was to happen at that site
visit, and the matter was expected on the November 17 agenda.

The meeting is scheduled, not a reported outcome. Do not claim any
change was approved or denied; listed agendas and meeting times
remain subject to change.

The original browser-rendered official-source text and SHA-256 hashes
were privately preserved at:
/var/lib/kali-ai-remote/ds-blog-pilot-evidence-006/

The factual draft has three evidence references linking to two exact
official source captures. It passed the Checkpoint 002 article schema
and raw-source evidence validation. It was submitted to a private
editorial queue with state needs_review.

The production ledger correctly REFUSED to reserve a publication slot
because this specific draft has not received a genuinely distinct
editor review. No approval was forged. No public story or email exists.

Six source-capture/draft integrity tests passed (28 total new pilot tests).

## Current task access blocker

The three original ChatGPT tasks remain enabled. Their displayed
environment selection is inherited and the saved environment details
are unavailable. No completed unattended run was observed.

The Writer Run Now action was exercised for this pilot but returned
an inline run inside the current conversation. This confirms connected
Kali access in this conversation, NOT the scheduled tasks' access
to Kali when running independently later.

No schedules were added or altered.

## Remaining conditions before ONE permitted live pilot

1. Independently verify an actual unattended task can work with Kali
   and shared private staging.
2. A separate editor must review the real draft and approve it based
   on original sources and the distinction between schedule and outcome.
3. Guard main with current remote SHA, exclusively reserve one new-post
   slot, build and validate an exact five-file first-release delta:
   blog-v2.html, sitemap.xml, assets/css/blog-local.css,
   assets/js/blog-local.js, and the one original story HTML page.
4. Execute an authorized production GitHub commit (not tested here),
   then verify its exact public HTTPS article URL, canonical and content.
5. Only after publication verification, send one authorized Gmail
   notification to the verified connected recipient. Save Gmail's
   actual message ID, avoiding uncertain duplicate retries.

## Explicit non-actions

No GitHub main update, public website publication, real email send,
scheduling change, DNS/Tailscale/security change, or changes to original
DS DATA VAULT, DS OVERWATCH, protected monitoring, or the Checkpoint 003
collector. The real draft and official-source snapshots remain private.

## Safe status commands

cd /var/lib/kali-ai-remote/ds-blog-production-pilot-006
python3 scripts/pilot_preflight.py preflight
python3 scripts/pilot_preflight.py status

No command here deploys or sends an email.