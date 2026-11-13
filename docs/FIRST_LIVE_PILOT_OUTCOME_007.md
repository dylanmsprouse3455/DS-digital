# DS Digital Designs — First Verified Live Article and Gmail Pilot

Date: November 12, 2026, Eastern
Status: ONE live article verified and ONE real Gmail notification sent.
No unattended publisher, new schedules, or new collector jobs were enabled.

## Public result

Verified public article:

https://dsdigitaldesigns.org/greeneville/greeneville-historic-zoning-commission-november-17-2026.html

Title: Greeneville schedules Nov. 17 Historic Zoning Commission meeting; North Main Street item expected.

This is a low-risk scheduled-government-meeting notice. The article explains
that a November 10 site visit at 300 N Main St involved an anticipated
application for structural changes, that no formal vote occurred at the
site visit, and that a November 17 commission meeting is scheduled. The
article does NOT claim the work was approved or any meeting outcome.

Original official sources:
- https://www.greenevilletn.gov/events
- https://www.greenevilletn.gov/page/historic-zoning-commission

Original official web-page snapshots and raw SHA-256 receipts are held
privately outside this public repository:
  /var/lib/kali-ai-remote/ds-blog-pilot-evidence-006/

The writer prepared an original article. A separate manual ChatGPT review
in a subsequent conversation turn checked the two original sources and
approved the specific draft with written review notes. This was NOT an
unattended run of the scheduled Editor automation.

## GitHub and live website

Original production main:
9ac82e6a6997e678db2b01c96f6a9aec8c55331b

One protected, expected-SHA, non-force main update:
4707b655ec2ad6958382a50761b9fdf699f9bb62

The approved release changed exactly five site files:
- blog-v2.html
- sitemap.xml
- assets/css/blog-local.css
- assets/js/blog-local.js
- greeneville/greeneville-historic-zoning-commission-november-17-2026.html

All three older article pages were checked live and still return HTTP 200.
The new blog listing links the article. Main page assets and mobile,
tablet and desktop preview checks passed. The target article's live
HTTP response and all site-critical links were checked using Chromium.

Content SHA-256 for the generated article:
d771e2d5b2d04d4a10d7e115ae3f44746c8c00a185c1044ffdcfcf69f47dcb54

Cloudflare adds a changing challenge script, sometimes accompanied by
its own Web Analytics beacon, to served HTML. The initial exact public
HTTP response differed from the Git release solely due to those two
known injected scripts. A revised guarded verifier recognizes ONLY
those identified Cloudflare injections and then requires an exact match
of every remaining byte to the approved SHA-256. Unknown changes still
fail verification. Tests cover one or both Cloudflare scripts, insertion
order, altered article content, non-200, wrong domain and redirects.

A subsequent live-browser check confirmed the article already declares
<base href="/">. This correctly resolves its CSS, menu JavaScript and
"back to blog" links to the site root; no link correction was required.
One unrelated chat-widget.js request returned 503; that script was
already missing from original main. Its behavior was not changed by
the pilot.

## Persistent production ledger

Private, owner-only state:
  /var/lib/kali-ai-remote/ds-blog-production-pilot-state-006/

Release ID:
1d18aeb2835abec9eb96baf2703ecc31

The release ledger independently checks the original sources, approvals,
current GitHub main SHA and verified public article hash. Its status is
notified. The Gmail outbox independently recorded a real sent-message
receipt from Gmail. The private ledger cross-checked that receipt and
the published article URL/hash before changing the release to notified.

November 12 Eastern daily cap:
- verified new posts: 1
- remaining slots: 3
- strict new-post maximum: 4
- goal: one quality article daily where sources permit; never fabricate
  or republish unsupported content to meet the target

No second email was sent after the public article's status changed.

The verified Gmail message ID and destination email address are NOT
stored in this public GitHub report; the receipt remains in the owner-only
local notification-outbox database.

## Remaining activation blockers

The initial, one-article, manually supervised pilot is COMPLETED.
It does not establish continuous unattended production readiness:

- No Kali raw-source collector schedule has been activated.
- A scheduled Editor task previously reported Kali access, but its
  real candidate review in this pilot was manual. The scheduled
  Writer's unattended Kali access remains unverified.
- The existing two-hour Writer/Editor tasks continue in STAGING-ONLY
  mode. No further public deployments or notification sending are
  authorized through those tasks.
- A single exclusive publisher service/actor is still needed to safely
  enforce the same SQLite quota across future unattended releases.
  The ledger alone cannot stop unrelated direct writes to GitHub main.
- The correct Google Analytics 4 property for the site's tracking ID
  remains unconfirmed; Search Console reporting currently has no rows.
- A production rollback from public GitHub/CDN propagation remains
  untested; local Git revert/rollback tests have passed.
- Any sensitive, disputed or high-risk public news still requires
  owner review/correction safeguards.

No Tailscale, protected monitoring, DS DATA VAULT, DS OVERWATCH, other
Kali projects, source DB, DNS, existing automations or unrelated
production files were altered in this live pilot.