# DS Digital Designs — Local Publishing Contract (Checkpoint 002)

**Development branch only. No public deployment, collection job, scheduled task, or email notification is enabled by this checkpoint.**

The existing blog index and three article URLs remain unchanged. Generated local story pages come from an explicitly approved publication manifest, never directly from scraped information. The manifest currently contains zero stories.

## Two data layers
1. **Private raw collection** — permitted public records, raw payloads, source URLs, discovery time, locations, topics, provenance, and revision history remain in separate private storage. Never commit private records, draft stories, personal information, or credentials to this repository.
2. **Approved public manifest** — an editorial review process (not yet implemented) exports only verified, low-risk and approved article records to content/local-stories.json. Proposed matters must remain labeled as proposals. Sensitive claims always need separate review.

## Story data contract
The JSON manifest has schema_version 1 and a stories array. Approved stories require:
- id, immutable slug, title, summary, location, category
- publication_status = approved, sensitive = false
- verification_status = proposed, confirmed, or updated
- published_at, updated_at as timezone-aware ISO 8601 values
- sources: objects containing title, HTTPS url and kind (official, firsthand or other_reporting)
- sections: objects with heading and paragraphs

The builder rejects drafts, unsafe slugs and source links, sensitive or unclassified stories, duplicate IDs/slugs, invalid timestamps, unlabeled proposals and confirmed items without an official or firsthand source. These checks do not independently establish truth or legal publishing rights. Editorial fact-checking is still required.

## Builder and tests
Run inside this branch's isolated checkout:

    python3 scripts/build_local_stories.py
    python3 -m unittest tests.test_local_stories -v
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/blog_ui_browser_test.cjs
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/local_stories_browser_test.cjs

Only the ignored build/ folder is written by the builder. Its preview includes the blog index with new approved story cards, one greeneville/<slug>.html page for each approved story, and an updated sitemap.xml. Existing article links remain intact and article slugs remain stable on update. Browser tests use localhost and block external browser requests. The test article is explicitly fictional and is never a public story.

## Future automated workflow (not installed)
- Collector saves raw records with immutable provenance.
- Every two hours, an editor evaluates which story buckets justify a new post or update.
- Source checks, appropriate review and an explicit publication gate precede release.
- A controlled process generates pages and deploys a validated public build.
- The published HTTPS page is checked for successful response and expected content.
- **Only after verifying publication** does an email with the real article URL get sent.
- Google Search Console and site analytics subsequently measure traffic; rankings cannot be guaranteed.

Corrections should preserve timestamps and a revision trail. Criminal allegations, emergencies, private personal information, and disputed facts require human review before any public posting.

## Rollback and remaining work
This checkpoint is confined to feature/greeneville-blog-content-checkpoint-002, based on the previous isolated UI branch. No merge, DNS, Tailscale, production service, or automation changes. A later release needs user approval, deployment verification, rollback readiness, and notification testing.

Not implemented: real collector, editorial queue, fully automated fact-checking, approved unattended-publishing policy, email integration, production deployment, Google indexing checks, and real iPhone Safari verification.