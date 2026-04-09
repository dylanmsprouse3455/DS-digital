# DS Digital Designs - Modular Rebuild Notes

## A1 - LOCKED ANCHOR
- `index.html`
- Leave this as the QR-safe home page.
- Do not rename or move it.

## B1 - SHARED STYLE
- `assets/css/theme.css`
- Shared visual system for modular pages.

## B2 - SHARED BEHAVIOR
- `assets/js/shell.js`
- Handles menu open/close and active-link behavior.

## B3 - COMPONENT LOADER
- `assets/js/load-components.js`
- Pulls reusable HTML pieces into each modular page.

## B4 - SHARED HEADER
- `components/header.html`

## B5 - SHARED NAV
- `components/nav.html`
- Current modular nav paths:
  - Home -> `index.html`
  - Services -> `services-v2.html`
  - Quote -> `quote-v2.html`
  - Contact -> `contact-v2.html`
  - Portfolio -> `portfolio-v3.html`

## B6 - SHARED FOOTER
- `components/footer.html`

## C1 - MODULAR PORTFOLIO
- `portfolio-v3.html`

## C2 - MODULAR SERVICES
- `services-v2.html`

## C3 - MODULAR CONTACT
- `contact-v2.html`

## C4 - MODULAR QUOTE
- `quote-v2.html`

## HOW TO EDIT FAST
1. Change nav for all modular pages -> edit `components/nav.html`
2. Change shared colors/layout -> edit `assets/css/theme.css`
3. Change menu behavior -> edit `assets/js/shell.js`
4. Change one page only -> edit that page file directly

## IMPORTANT
- `index.html` still uses its old built-in menu until you manually swap it later.
- The new modular pages are ready now, but the home page will not link to them until you update `index.html`.
