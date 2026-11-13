# DS Digital Designs — Continuous Publishing Checkpoint 008

Date: November 12, 2026 (America/New_York)
State: OFFLINE TESTED AND STAGED; CONTINUOUS AUTOMATIC PUBLICATION NOT ACTIVATED.
Branch: feature/ds-unattended-publishing-gates-008
Checkout: /var/lib/kali-ai-remote/ds-blog-continuous-checkpoint-008/

## Already published live pilot (unchanged during this checkpoint)

- Public original: https://dsdigitaldesigns.org/greeneville/greeneville-historic-zoning-commission-november-17-2026.html
- Public GitHub main remains at release SHA: 4707b655ec2ad6958382a50761b9fdf699f9bb62
- Production SQLite pilot records a verified publication with a confirmed Gmail sent receipt.
- The next controlled release must reconcile that actual main SHA and one published post.
- No public article, email, GitHub main change, or new schedule was executed in Checkpoint 008.

## 1. Scheduled official-source collector — staged only

The existing Checkpoint 003 collector maintains all raw source bytes privately.
Source-cycle wrapper:
  scripts/source_cycle.py

Staged systemd units:
  ops/staged-systemd/ds-blog-official-sources.service
  ops/staged-systemd/ds-blog-official-sources.timer

The calendar is syntax-verified to run at even local hours, :45:
  00:45, 02:45, 04:45, ..., 22:45 America/New_York.
This places source collection 15 minutes before the following even-hour Writer run.
No unit was installed, enabled or started.

Each cycle requests at most THREE official index pages, alternating:
  Group A: town-agendas, town-events, town-events-program
  Group B: county-notices, county-purchasing

All five pages must match the immutable approved source registry. The
original collector re-checks robots.txt before each official HTTPS request,
denies redirects, respects crawl delay, and captures at most 2 MB/page.
It does NOT crawl linked documents, publish raw page contents, or
represent source-page snapshots as verified event stories.

The wrapper:
- always defaults to plan/read-only;
- refuses live collection without an owner-created activation.json with
  the registry SHA and explicit owner approval;
- requires --execute even with that activation file;
- serializes collection through a host-local flock;
- stores durable per-slot SQLite receipts; refuses duplicate/retry
  of completed, failed or crash-interrupted slots without reconciliation;
- caps private DB growth to 24 MB per Eastern day;
- requires at least 1 GiB of free filesystem space before collection;
- preserves original private source DB, unrelated projects and services.

At development audit, Kali had roughly 5.6 GiB free (95% full).
No new live source was fetched.

The exact private live source directory was untouched. The current raw
collector still had 5 official registered sources and 4 saved revisions.

## 2. Writer/Editor unattended shared-workspace probe — scheduled only

Script: scripts/unattended_probe.py

ID: ds-blog-shared-kali-008-20261112

The existing Writer and Editor ChatGPT automation prompts were updated
to execute this one-shot **harmless shared-Kali probe in their actual
scheduled runs**:
- Writer: 22:00 Eastern, writes a private receipt after a read-only check
  of the private collector's revision count.
- Editor: 22:30 Eastern, verifies the Writer's exact receipt hash and
  checks production ledger metadata read-only.
- Both tasks preserve the same original schedules and staging-only
  publication constraints. No new task was created.
- The ChatGPT scheduled-run record must independently corroborate the
  matching two receipts. Merely running commands manually in a chat
  does NOT prove unattended access.

Probe receipts will be stored under:
  /var/lib/kali-ai-remote/ds-blog-continuous-private-008/handoff-probe/

At completion of this checkpoint, no actual scheduled Writer receipt
or Editor acknowledgement had been observed. The Editor had a completed
read-only run earlier in the day; the Writer had not yet completed an
unattended run. Their inherited environment selections remained
unresolved. Therefore cross-run write/read access remains UNVERIFIED.

## 3. Exclusive production release preflight

Script: scripts/publication_gate.py

One host-local publishing lock, backed by the already persistent private
production ledger and a separately required owner activation file.
Preflight verifies:
- exact current GitHub main commit against pinned local checkout/ledger;
- no in-flight, uncertain, or previously released duplicate article;
- remaining daily slots before reserve (absolute 4 new/day Eastern cap);
- distinct editor approval and original raw evidence revision SHA;
- approved official-source endpoints, freshness, proposal status,
  article identity, and high-risk wording escalation;
- target new-article URL and expected content digest.

The policy intentionally marks automatic screening as NOT a substitute
for human/independent editorial fact checking. Critically, an editor
identity stored as a string is NOT cryptographically authenticated.
Production separation will require a trusted task identity, permission
separation and reliable scheduled run evidence before activation.

The new publication gate itself does not push GitHub or send Gmail.
No activation file was created, and the code rejects unattended
activation by default. Nothing bypassed existing GitHub main SHA checks,
private SQLite quota, or Cloudflare-normalized exact-byte HTTPS proof.

Single-host flock and SQLite transaction protection do not stop an
unrelated third-party actor with direct access to GitHub main.
An exclusive publisher identity/main-branch protection policy and real
transport credentials remain to be provisioned and verified separately.

## 4. Corrections, retractions and rollback

scripts/correction_plan.py stages **body-only** corrected HTML for an
already published article, requiring a new independently approved,
source-hashed draft and a clear correction explanation.

It preserves original slug, published_at, headline, summary and canonical
URL. It fails if live source-controlled HTML has drifted, source review
is missing, modified time did not advance, or another correction is pending.
The visible correction note is embedded in the corrected article body,
and private SQLite saves old/new hashes and editor ID.

Headline/summary amendments, retractions, safety incidents and legal
allegations are deliberately escalated rather than silently published.
No corrections were deployed in this checkpoint.

Rollback had previously passed disposable-local Git revert tests.
This checkpoint's combined offline workflow additionally demonstrates
a full local fake release + reverse revert and a crash-after-push
uncertain state, with no new emails or quota release on ambiguity.
PRODUCTION/CDN rollback remains untested and must be checked by a
bounded separately approved live correction or rollback pilot before
autonomous release deployment.

## 5. Complete offline integrated test

tests/test_continuous_end_to_end.py exercises:

synthetic authorized-source snapshots -> Writer draft ->
independent Editor approval -> read-only policy preflight ->
private quota reservation -> approved static blog build ->
exact allowlist Git candidate -> local bare fast-forward Git
publication -> mock public HTTPS byte proof -> mock email
claim and sent receipt -> durable production ledger notified.

Additional tests force simulated crash-after-push and rollback.
All fixtures are synthetic; no real Gmail or public GitHub writes.

The protected Checkpoint 003 collector deliberately restricts
writes to its own isolated state directory. The test respects that
restriction and uses a temporary synthetic read-only-compatible DB,
not a bypass or change to the original protected collector.

Test commands on Kali:

    cd /var/lib/kali-ai-remote/ds-blog-continuous-checkpoint-008
    python3 -Werror::ResourceWarning -m unittest tests.test_source_cycle tests.test_unattended_probe tests.test_publication_gate tests.test_correction_plan tests.test_continuous_end_to_end tests.test_production_quota tests.test_real_pilot_evidence tests.test_release_candidate tests.test_local_git_transport tests.test_verified_notification tests.test_release_coordinator tests.test_collector_packets tests.test_local_stories -q

    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/blog_ui_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/local_stories_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/full_pipeline_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/actual_candidate_browser_test.cjs /var/lib/kali-ai-remote/ds-blog-release-candidate-demo-005/git

Result: 184 Python + 43 browser = 227 tests passed.
Staged systemd .service and .timer parsed without error.
No package installation, service enable or public GitHub release occurred.

## 6. Blocks to actual unattended activation

1. No completed actual Writer scheduled run and no verified Writer ->
   Editor private receipt handoff. The existing Editor read-only run
   alone is insufficient.
2. No provisioned, identity-separated trusted editor authority; a
   plaintext "reviewer_id" string can be supplied without proof of who
   ran the reviewer. The two scheduled tasks must be verified separately
   and use an authenticated private approval channel.
3. No authorized exclusive unattended GitHub/Gmail transport bound
   to a protected publishing identity. ChatGPT tools used successfully
   during the manually supervised first pilot do not by themselves
   prove unattended scheduled tasks can use the same account or local
   protected credentials.
4. No automatic, source-derived high-quality article extraction and
   editorial judgment validated across multiple real daily cycles.
   Index snapshots are NOT guaranteed publishable news.
5. No real public production/CDN rollback test. The fake local Git
   rollback proves the mechanism, not final hosting recovery.
6. Root filesystem has limited free capacity for a continuous archive.
   Collection rate/disk quotas mitigate this but long-term storage
   should be explicitly planned before activating.
7. Activation policy and secure production-specific credentials need
   separate owner authorization after these conditions are met.

## Do-not-activate restrictions

No unattended production publishing.
No new automated collector schedule.
No changes to existing automation cadences.
No GitHub main merge, production DNS/security/Tailscale changes.
No emails, protected monitoring changes, or raw source modifications.
No disclosure of private source records or Gmail identifiers.

The owner-authorized 1-quality-article/day target remains conditional
on reliable material. The 4-new-article/day hard maximum is enforced by
the persistent production pipeline, not a request to fill all four slots.