# DS Digital Designs — Checkpoint 005: Guarded Release and Notification Gates

**Date:** November 12, 2026
**State:** PRIVATE STAGING AND SIMULATION ONLY. No production release or real email.
**Development branch:** feature/ds-blog-production-gates-checkpoint-005
**Parent:** feature/ds-local-publishing-integration-004

## User's exact design

Kali raw local sources → Blog Writer every two hours → independent Editor every
two hours → safe public website release → owner email with verified live URL.
A separate Traffic Watch checks the website every two hours.

Daily TARGET = at least 1 new meaningful article, when sourced and verifiable.
Absolute MAXIMUM = 4 NEW articles on each America/New_York calendar day.
Corrections/updates to an existing article do not count as new posts.
No fabricated, duplicated, misleading or poorly sourced stories to hit a quota.

## New components built

### Release candidate builder — scripts/release_candidate.py

Reads a pinned, clean, read-only local checkout of GitHub main. Checks
the baseline SHA matches the actual selected main revision. Verifies
Checkpoint 004's staged release-bundle manifest and SHA-256 for every file.
Prepares a PRIVATE local commit, never a GitHub push. Only these site paths
are authorized: blog-v2.html, sitemap.xml, and greeneville/<slug>.html.

Important first-release fix: detects the missing blog UI assets in the
real production main branch and includes assets/css/blog-local.css and
assets/js/blog-local.js in the initial five-file delta. It preserves every
existing article, asset, CNAME, hosting setting and unrelated file.
Unexpected files or concurrent branch changes stop the release.

The report includes the pinned original main SHA, new local candidate commit
and SHA-256 fingerprints. Rollback uses a safe revert commit after checking
current branch state; never a forced reset that could lose later changes.

### Git transport safety mock — scripts/local_git_transport.py

Only accepts a disposable local bare Git repository under a temporary
test folder whose name begins ds-blog-transport-fixture-. It has no
permission or code path to push to a real GitHub URL. Tested:
- ordinary fast-forward push to local bare main
- stale expected-main revision rejection
- rollback through a new revert commit
- restored original tree after local rollback
- intervening changes prevent unsafe rollback

### Verified notification outbox — scripts/verified_notification.py

Stores durable private notification states in owner-only SQLite.
Only an exact public HTTPS URL on dsdigitaldesigns.org/greeneville/...,
HTTP 200, correct article HTML content type, expected canonical URL,
and exact approved file SHA-256 qualify a notification for sending.
Redirects and mismatched content are rejected.

States are verified, sending, sent, uncertain. One atomic claim avoids
duplicate concurrent sends. If Gmail delivery is uncertain, stop and
reconcile rather than send again automatically. Only a Gmail connector
message-ID confirmation can be recorded as sent. **There is NO real
Gmail send call in this module.** Tests use a fake public response and
fictional Gmail response IDs, and do not send messages.

## Main branch read-only audit

At checkpoint inspection:
- Main SHA: 9ac82e6a6997e678db2b01c96f6a9aec8c55331b
- Original three blog article files remain present on main.
- The new CSS and JavaScript assets are not yet on main.
- An actual-main-based PRIVATE sample release candidate was built,
  verified at 375px, 768px and 1440px, and did NOT deploy.
- The candidate is a deliberately fictional synthetic test article,
  NOT real Greeneville reporting. Never publish it as news.
- The demo candidate is at:
  /var/lib/kali-ai-remote/ds-blog-release-candidate-demo-005/
- Its local commit is cac1eabf8fb77dda4c91277eaea7a185d9a0a965

## Tests

Run inside the Checkpoint 005 development checkout on Kali:

    python3 -Werror::ResourceWarning -m unittest tests.test_local_stories tests.test_release_coordinator tests.test_collector_packets tests.test_release_candidate tests.test_verified_notification tests.test_local_git_transport -q

    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/blog_ui_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/local_stories_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/full_pipeline_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/actual_candidate_browser_test.cjs /var/lib/kali-ai-remote/ds-blog-release-candidate-demo-005/git

All article, source, Git and email fixtures in these tests are synthetic.
The public website and email inbox were never modified by this checkpoint.

## Remaining blockers to separately authorize before activation

1. The actual authenticated GitHub production push/merge adapter, safe
   rollback with GitHub Pages/CDN propagation, and a **production** article
   quota ledger across all publishers and retries are NOT yet deployed.
   Current quotas are verified in simulation only.
2. Gmail can be accessed through a ChatGPT connector, but no real mail was
   sent and no production sending workflow is wired. Confirm destination
   address, separately approve a bounded test, and record real Gmail receipt.
3. The existing scheduled writer/editor task environment is inherited and
   does not show a verified connected Kali execution environment. Verify
   actual scheduled run receipts before claiming unattended access works.
4. The current raw collector has only four source-page snapshots, not four
   verified news stories, and does not run automatically. Story extraction,
   sourcing and rights policy still need a complete live review.
5. Google Search Console is connected; search reports currently return
   no rows. GA4's exact DS Digital Designs property remains unconfirmed.
6. Public HTTPS post-publication content verification has not been
   exercised after a real GitHub Pages release. CDN byte transformation
   may require controlled release testing.
7. Independent editorial rules, sensitive-topic escalation, correction
   history, and ongoing owner accountability must be operationally agreed.

Before the final activation, obtain explicit owner permission for production
website changes, automatic collection, unattended publication and actual Gmail
notifications. Preserve all other Kali projects, Tailscale, protected
monitoring, raw-source databases and unrelated production files.