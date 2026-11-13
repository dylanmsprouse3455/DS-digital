# DS Digital Designs — Blog URL Indexing Audit
**Audit date:** 2026-11-12 (US Eastern)
**Target Search Console property:** sc-domain:dsdigitaldesigns.org
**Repository:** dylanmsprouse3455/DS-digital
**Branch:** audit/blog-search-indexing-2026-11-12 (created from main)
**Scope:** owner-authorized read-only public audit and isolated regression-test staging.

## Executive findings

All four existing preferred blog URLs returned HTTPS 200, had matching self-referencing canonicals, and had no noindex directive or HTTP X-Robots-Tag. The sitemap and robots.txt are valid and reachable. No proven blog HTML-level indexing blocker was found; therefore no change to existing page sources is justified yet.

**One hosting-level configuration issue:** the plain HTTP blog URL and plain HTTP article URL returned HTTP 200 rather than a redirect to HTTPS. Their document canonical links point to HTTPS, reducing risk of duplicate indexing, but the preferred fix is a 301 or 308 redirect configured at the CDN/hosting level. Static HTML alone cannot enforce a real HTTP redirect. That hosting change is outside the authorization for this checkpoint and was NOT attempted.

**Google indexing status remains unknown.** Search performance and sitemap reports returning empty rows cannot tell whether individual URLs are indexed.

## Audited existing blog URLs

1. https://dsdigitaldesigns.org/blog-v2.html
2. https://dsdigitaldesigns.org/post-high-converting-websites.html
3. https://dsdigitaldesigns.org/post-small-business-security.html
4. https://dsdigitaldesigns.org/post-site-speed-revenue.html

## Verified live website checks

- All four pages return direct HTTPS 200 without redirecting elsewhere.
- Exactly one corresponding HTTPS canonical is declared by each page.
- Each has a distinct title, one H1, descriptive meta description, viewport metadata, Open Graph title/description/URL, social image and Twitter card.
- None has a noindex meta robots directive or X-Robots-Tag response header.
- The blog links to all three existing articles using crawlable HTML anchors, and each article links back to the blog.
- Two older duplicate paths, /blog.html and /why-site-speed-impacts-revenue.html, have noindex,follow and the preferred HTTPS canonical.
- robots.txt returns HTTP 200, allows general crawling and references the sitemap.
- sitemap.xml returns HTTP 200 and contains 14 unique URLs, including all four blog URLs; all 14 were reachable at audit time.
- Shared stylesheet, JavaScript components and social preview image returned HTTP 200.
- HTTPS www. requests redirect to the canonical HTTPS non-www address with HTTP 301.
- Plain HTTP requests for the main blog and a blog article returned HTTP 200 with no redirect.
- None of the four pages has Blog/BlogPosting JSON-LD. This is an OPTIONAL semantic enhancement, not proven to be an indexing blocker; do not invent dates or bylines.
- Sitemap lastmod dates were not artificially advanced. A May 16 Git update affected only a GA4 tracking identifier, not substantive article content.

## Offline and local Chromium validation

Tests were run from an isolated checkout, with no public web actions:
- 12 Python checks validate core canonical, metadata, links, sitemap and robots contracts.
- 13 Chromium checks run the four pages at 375px, 768px and 1440px, with no horizontal overflow, valid page headings and mobile navigation.
- Main blog article links and text are accessible without JavaScript.
- Browser traffic was limited to an ephemeral 127.0.0.1 local server. No external scripts were fetched in these tests.

Run checks from the isolated checkout:
    python3 -m unittest tests.test_blog_indexability -v
    NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/blog_indexability_browser_test.cjs

Passing these tests does not establish whether Google has indexed the pages.

## Connected Search Console evidence

The Supermetrics Search Console account recognizes property sc-domain:dsdigitaldesigns.org. Search performance over the past 90 days and the available sitemap report returned no rows. This is NOT proof of zero visits, zero indexed URLs, or sitemap rejection.

The available reporting connector does NOT expose Google's per-URL URL Inspection verdict, last crawl time, indexing reason or Google-selected canonical. No indexed/not-indexed verdict was invented and no Request Indexing action was invoked.

## Remaining owner-side URL Inspection step

Open https://search.google.com/search-console, select dsdigitaldesigns.org and inspect the four exact URLs above. For each page, record:
- URL is on Google / URL is not on Google and stated reason.
- Page indexing: page fetch, crawl allowed, indexing allowed, last crawl date.
- User-declared canonical and Google-selected canonical.
- If not indexed, use Test live URL to check current accessibility; it does not guarantee indexing.

Provide those URL Inspection results to determine whether any further site code fix is genuinely necessary. Do not request indexing without separate authorization.

## Future hosting correction, not performed

With separate approval, inspect the current Cloudflare/GitHub Pages setup and safely enforce a server-side 301/308 from HTTP to HTTPS for the canonical host, without changing existing paths, unrelated assets, DNS, security protections, or analytics. Validate the live redirect after implementation. Do not substitute a JavaScript/meta refresh redirect for a proper HTTP redirect.

## Preservation of user systems

This checkpoint creates the branch audit/blog-search-indexing-2026-11-12 from main. The earlier isolated blog redesign branches remain untouched and are NOT the currently deployed blog. Only this report and test files are added to the audit branch. No production HTML, sitemap, robots.txt, DNS, CDN, GitHub main, Tailscale, schedules, automation, emails, index requests, deployment, or unrelated projects have been changed.