# DS Digital Designs — Final Publishing Integration 004

**Date:** November 12, 2026
**State:** Isolated staging only. No production publication, real email, scheduled collector or GitHub merge was activated.

## Owner's intended workflow

Kali collects raw local evidence -> Writer every 2 hours creates and updates source-linked drafts -> Independent Editor every 2 hours validates facts, corrections, and (after separate production approval) publishes -> Email verified live links -> Site Traffic Watch every 2 hours reads GA4 and Search Console.

Daily policy uses America/New_York: target at least ONE truly useful verified NEW article/day if trustworthy information exists; hard maximum FOUR NEW published articles/day. Do not invent filler news. Edits/corrections to existing articles do not use the new-post budget.

## What has actually been integrated and tested

1. Read-only collector packets from /var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/state/local-information.sqlite3. Packets preserve revision ID, source URL, exact SHA-256, topic, timestamp, and bounded visible page text. No raw source mutation or uncontrolled crawling.
2. Writer draft submission and an independent editor's evidence check. Draft JSON follows the Checkpoint 002 blog schema, with publication_status=draft and a private evidence_refs array: revision_id, sha256, and a verbatim source quote. The reviewer must have a distinct task ID, record meaningful notes, and approve the current draft version. Every cited source must match immutable source data. Source-quote matches do NOT independently prove the broader article is factually correct: responsible human/editorial judgment and sensitive-item escalation remain necessary.
3. Private SQLite SIMULATION ledger stores drafts, reviews, reservations, simulated releases, and notification previews. Transactions serialize concurrent reservations and enforce four new slots per Eastern calendar day. Duplicate release attempts return the same stable ID. An existing story update does not use a new-post slot. Never treat simulation reservations as real published article counts.
4. Existing Checkpoint 002 generator produces article HTML, a blog card and sitemap changes. The release manifest is intentionally a DELTA: blog-v2.html, sitemap.xml, and approved greeneville/*.html story pages. It does not delete or replace unrelated site files, CNAME, tools, images, etc.
5. Mock publication copies only delta files into a temporary 127.0.0.1 server, verifies HTTP 200, expected article bytes and SHA-256 and the intended canonical URL, then stores ONE simulation-only NOT SENT email preview with the proposed article URL. No actual GitHub deployment, external email or Google indexing request.

## Locations

- Isolated connected Kali development checkout:
  /var/lib/kali-ai-remote/ds-blog-release-checkpoint-004/
- GitHub branch:
  feature/ds-local-publishing-integration-004
  (based on feature/greeneville-blog-content-checkpoint-002, not on production main)
- Existing raw collector, strictly read-only to this integration:
  /var/lib/kali-ai-remote/ds-local-intelligence-checkpoint-003/
- PRIVATE simulator state, outside public GitHub:
  /var/lib/kali-ai-remote/ds-local-publishing-private-004/
- Temporary ignored page outputs:
  /var/lib/kali-ai-remote/ds-blog-release-checkpoint-004/build/

## Safe CLI actions (all local and staging-only)

Run in the isolated checkout:

    python3 scripts/pipeline_cli.py collector-status
    python3 scripts/pipeline_cli.py collector-packets --after-revision 0 --limit 4
    python3 scripts/pipeline_cli.py queue
    python3 scripts/pipeline_cli.py status

For an independently prepared and privately saved draft:

    python3 scripts/pipeline_cli.py submit-draft --file /PRIVATE/draft.json --writer-id writer-task
    python3 scripts/pipeline_cli.py queue
    python3 scripts/pipeline_cli.py review --story-id <id> --reviewer-id editor-task --decision approved --note "Evidence checked against original source, including proposal status."
    python3 scripts/pipeline_cli.py reserve --story-id <id>
    python3 scripts/pipeline_cli.py stage --release-id <release-id>
    python3 scripts/pipeline_cli.py simulate --release-id <release-id>

There is deliberately NO production deploy, send-email, change-DNS, update-main or schedule command. Do not submit unapproved raw snapshots as if they were confirmed articles.

## Tests

    python3 -Werror::ResourceWarning -m unittest tests.test_release_coordinator tests.test_collector_packets tests.test_local_stories -q
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/blog_ui_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/local_stories_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/full_pipeline_browser_test.cjs

The comprehensive tests use fictional source data. They cover attempts to self-approve, unsupported or altered claims, stale draft review, wrong hashes/quotes/URLs, sensitive-content blocking, 4-new-post Eastern-day cap under concurrent runs, stable canonical URLs, updates, retries, corrupted HTML, source/database privacy, mock HTTP integrity, local browser layouts and NOT SENT notification preview. No live email or public page is created.

## Existing scheduled tasks

Do not duplicate, reschedule or re-enable unrelated tasks.

- DS Local Blog Writer — starting 8:00 PM Eastern, repeating every two hours
- DS Blog Editor Publisher — starting 8:30 PM Eastern, repeating every two hours
- DS Website Traffic Watch — starting 9:00 PM Eastern, repeating every two hours

The tasks' inherited tool/computer environments are not yet independently proven to access this private Kali workspace; verify with actual run receipts. Their staging handoff must use the CLI and private workspace rather than relying on ChatGPT memory alone.

## Blockers BEFORE production activation

1. No automatic raw-source collection schedule; current collector was invoked manually, and its four raw buckets are source pages rather than verified local news stories. Source extraction and substantive news judgments are not yet fully automated.
2. No approved live release transport. The production static website is served from the existing GitHub main branch, whereas the new blog/publishing code remains on isolated branches. A future publisher must reconcile CURRENT main and all previously published stories, preserve unrelated files, backup the exact pre-release main commit, serialize releases, and support rollback and correction history.
3. The tested SQLite quota ledger is simulation-only. A production ledger must reconcile real public release receipts, failures, partial deployments, concurrency, late retries and days spanning midnight in Eastern.
4. Public HTTP 200 and exact content verification after actual deployment have not been tested. The mock 127.0.0.1 response is not proof that a live article exists.
5. Gmail is connected for account information, but NO Gmail send was attempted or verified. Only after publicly confirmed publication should an authorized Gmail action send the real URL and record success, with safe retry handling for "published but email failed".
6. The editor needs an approved unattended publishing policy, source and reuse rules, human escalation for serious accusations/safety events, clear bylines and correction/retraction process. The one-post minimum is a quality-gated target, not permission to invent news.
7. ChatGPT scheduled tasks must be confirmed able to reach the connected Kali and persist the same shared ledger. Current inherited environments alone do not prove access.
8. Google Search Console account is authenticated for dsdigitaldesigns.org, but search-performance reporting yielded no rows; GA4 property's association with website measurement ID still needs confirmation.

## Next guarded production release (requires a new explicit owner approval)

Independent source-backed review -> snapshot production main + existing story registry -> production SQLite quota reservation -> minimal delta release built/tested against the CURRENT branch -> guarded GitHub publication -> real public HTTPS article verification -> send real Gmail notification -> persist both verifiable receipts. Never claim production success on a simulation receipt.

No GitHub main change, merge, deployment, production email, scheduled collection activation, DNS/Tailscale/security change, or modification to original raw source records occurred.