const componentFallbacks = {
  'header-slot': `
<header class="site-header">
  <div class="header-inner">
    <a href="index.html" class="logo">
      <img src="0193CA57-3463-4528-AE1F-50F2BCD64BFB.png" alt="DS Digital Designs logo">
      <span>DS Digital Designs</span>
    </a>
    <button class="menu-btn" id="menuBtn" aria-label="Open menu" aria-controls="menu" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </div>
</header>`,
  'nav-slot': `
<nav class="site-nav" id="menu">
  <a href="index.html">Home</a>
  <a href="services-v2.html">Services</a>
  <a href="quote-v2.html">Get a Quote</a>
  <a href="contact-v2.html">Contact</a>
  <a href="blog-v2.html">Blog</a>
  <a href="portfolio-v3.html">Portfolio</a>
  <a href="about-v2.html">About</a>
</nav>`,
  'footer-slot': `
<footer class="site-footer">
  <p>&copy; 2026 DS Digital Designs. All rights reserved.</p>
</footer>`
};

const shellVersion = '2026-04-26-quote-menu-fix';

function componentUrl(path) {
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}v=${shellVersion}`;
}

async function loadComponent(targetId, path) {
  const target = document.getElementById(targetId);
  if (!target) return;

  try {
    const res = await fetch(componentUrl(path), { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load ${path}`);
    target.innerHTML = await res.text();
  } catch (err) {
    console.error(err);
    if (componentFallbacks[targetId]) {
      target.innerHTML = componentFallbacks[targetId];
    }
  }
}

async function loadSiteShell() {
  await Promise.all([
    loadComponent('header-slot', 'components/header.html'),
    loadComponent('nav-slot', 'components/nav.html'),
    loadComponent('footer-slot', 'components/footer.html')
  ]);

  if (window.initializeSiteShell) {
    window.initializeSiteShell();
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadSiteShell);
} else {
  loadSiteShell();
}
