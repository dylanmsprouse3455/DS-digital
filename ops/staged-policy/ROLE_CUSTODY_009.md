# DS Digital Designs — Checkpoint 009 permission and custody contract (STAGED)

State: Proposal only. No OS identities, user units, OAuth tokens, secrets, branch protection, automation schedules, or public websites were changed.

## Principals and least privilege

| Principal | Needs | Must not have |
|---|---|---|
| ds-blog-collector | Read allowlisted official public HTTPS pages; append private immutable source snapshots under a bounded disk quota | GitHub writes, Gmail send, editor-signing keys, public deployment |
| ds-blog-writer | Read private source snapshots; write drafts and progress cursor to a private handoff inbox | Editor signing key, editorial approval write authority, GitHub writes, Gmail send |
| ds-blog-editor | Read drafts and original evidence; review or reject; sign an exact draft SHA via a separately held Ed25519 key | GitHub production writes, Gmail send, raw source revisions |
| ds-blog-publisher | Read verified editor attestation and draft; check production ledger; publish only allowed GitHub files through a dedicated constrained identity; verify HTTPS; queue Gmail notification and record receipt | Source editing, writing review signatures, arbitrary filesystem writes, force pushes, unrelated repositories |

All principals must be independent authorized identities with meaningful access separation; displaying different labels for one Linux user does not count. The current kali-ai-remote UID 996 can access the connected device, but dedicated principals are NOT present and MUST NOT be fabricated by changing role strings.

## Review signing and trust

The staged scripts/signed_review.py verifies deterministic Ed25519 signatures over exactly: repository, article ID, current draft SHA-256, reviewer ID, issue time, expiry, and purpose. It rejects expired, replayed-on-another-draft, altered or unrecognized key IDs. Tests generate ephemeral fictional keys; **no real private key is created**.

A future owner-provisioned editorial signing key must be non-exportable or held in a separate OS account/credential provider unavailable to the Writer and Publisher. Pin its public key fingerprint inside a trusted administrative policy outside the repo. The prototype verifier is an offline primitive, NOT sufficient production authentication without that external custody boundary. The current signer root is missing.

## Remote GitHub and Gmail

The connected GitHub account currently has admin and push privileges for DS-digital, which is broader than necessary for an unattended publisher. Do not store its existing credentials in a repository, staging artifact, task prompt, or private SQLite ledger. A future scoped publisher identity should be restricted to the single approved repository and release process, with fast-forward/expected-SHA checks and auditable rollback approval. Confirm branch-protection and token scope before granting unattended write permission.

The first Gmail notification from the supervised pilot was verified read-only in Gmail Sent with the expected article link and destination account. Future send capability must be limited to owner-addressed publication notifications, with a persistent per-release outbox and explicit confirmation. Ambiguous Gmail send responses must be reconciled before retrying; no direct email send occurs in Checkpoint 009.

## Quota, collector, and recovery

The real production ledger persists in /var/lib/kali-ai-remote/ds-blog-production-pilot-state-006/, owned by kali-ai-remote with 0700/0600 permissions. It records one verified/notified article on November 12 Eastern, leaving three slots. A strictly exclusive publisher must hold a host-local file lock plus SQLite transaction while reconciling any remote commit and email state; external GitHub writers remain out of scope unless branch protection/rules guarantee they cannot bypass the ledger.

The existing official-source collector remains staging-only; it does not continuously run. Root filesystem was 95% used with around 5.55 GiB free during this checkpoint. The staged readiness policy requires at least 10 GiB of sustainable free capacity before a continuous archive is approved. Do not modify/remount Seagate storage without separate authorization.

Rollback code in scripts/recovery_plan.py created a private revert plan from the actual pilot commit and proved the exact pre-release Git tree is recoverable locally. It does not prove public CDN rollback propagation, which remains a blocker. No automatic rollback, GitHub force operation, or public website edit was performed.

## Current handoff evidence

The actual 10 PM November 12 scheduled Writer run completed and placed its private receipt under:
/var/lib/kali-ai-remote/ds-blog-continuous-private-008/handoff-probe/writer-receipt.json.
Its receipt records four raw revisions and no publication, and its completion is corroborated by the independently retrieved scheduled-run record. The Editor's separate scheduled acknowledgement was not present at the time of this checkpoint. The first Editor scheduled Kali read-only run succeeded earlier but does not establish cross-run acknowledgement of this specific Writer receipt.

## Default policy

No activation or collection marker is created by these scripts. Nothing in Checkpoint 009 starts a new service, installs users, changes credentials, deploys GitHub main, sends an email, or changes an existing ChatGPT automation schedule.

**Next security acceptance:** independently provision the identities and signer custody, verify the Editor's actual scheduled acknowledgement, bind a least-privilege GitHub/Gmail publisher identity, and exercise a separately authorized bounded CDN recovery test. Automatic publishing is not authorized by this document.