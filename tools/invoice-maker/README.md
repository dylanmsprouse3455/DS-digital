# Free Invoice Maker

A persistent static tool at `/tools/invoice-maker/`, integrated with the existing DS Digital Designs Free Tools page. No server, accounts, remote fonts or invoice telemetry. All demonstration contacts are fictional.

## Structure

- `model.js`: invoice schema, fictional example, integer-cent totals and validation.
- `storage.js`: IndexedDB version 1, atomic backup restore, sequential invoice numbering.
- `document.js`: shared text/vector layout for SVG previews and US Letter PDFs. Embedded Liberation fonts and jsPDF 4.2.1 (licenses in `vendor/`). No screenshot-to-PDF conversion.
- `app.js`: six-step wizard, autosave, customer reuse, saved invoices and backup controls.
- `styles.css`: scoped site-compatible presentation and mobile navigation.

## Data and arithmetic

USD only. Quantities and rates accept two decimal places. Round each line to cents, apply the invoice discount, then calculate and round tax on the discounted subtotal. Maximum 200 services; descriptions support 6,000 characters, notes 2,000. Long lines wrap and continue across pages.

IndexedDB stores sender profiles, customers, saved invoices, the active draft, numbering and UI preferences. Each edit is queued for autosave after 300ms; navigation flushes writes. A Web Lock prevents concurrent editing of the active draft in browsers that support it. Invoice numbers allocate inside read/write transactions and skip already saved numbers. Browsers without Web Locks should use one editing tab.

A new browser starts with a clearly marked fictional example. Starting a new invoice clears example contacts. Real sender profiles are reused; example contacts are not added to the user's address book. “Save invoice” keeps a finished invoice separately from the autosaved draft. Creating a new draft confirms before replacing an existing non-demo draft.

Backup format `ds-digital-invoices`, version 1, includes all six stores. Restore validates the entire backup before clearing or writing any store in one transaction. Backups preserve unfinished drafts, including temporarily invalid numeric fields. Browser storage errors are visible and allow current-draft recovery export. Persistent storage is requested when starting a new invoice and through Backup & storage; the browser can decline it. Backups remain necessary.

## Development and tests

From the repository root:

```sh
npm ci --ignore-scripts
npm test
npm run build
python3 -m http.server 8765 --bind 127.0.0.1
# In another terminal with Chromium and Poppler installed:
npm run test:browser
npm run test:challenge
node tests/invoice-maker/regression.mjs
```

`CHROMIUM_PATH` overrides `/usr/bin/chromium`. `INVOICE_BASE_URL` changes the test origin. Browser evidence, PDFs and screenshots are written to ignored `test-results/invoice-maker/`. The preservation regression compares unchanged site files with the pre-integration commit. Set `INVOICE_BASELINE` to a private JSON checksum baseline to also verify pre-existing local work.

`npm run build` validates static output; no framework compilation is needed. The checked-in vendor file must match the pinned npm dependency. Production uses the existing GitHub Pages deployment from `main`.

## Verification limits

Automated mobile tests use Chromium at 390px and 430px. They do not establish physical iPhone/Safari behavior. The WebKit runtime on the development machine requires unavailable host libraries. On iPhone the UI provides an Open PDF link and instructions to use Share → Save to Files.

The embedded fonts support common Latin text, accents, Greek and Cyrillic. This release does not claim comprehensive complex-script shaping or full multilingual typesetting.
