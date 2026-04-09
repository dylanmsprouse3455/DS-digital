async function loadComponent(targetId, path) {
  const target = document.getElementById(targetId);
  if (!target) return;
  try {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`Failed to load ${path}`);
    target.innerHTML = await res.text();
  } catch (err) {
    console.error(err);
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

document.addEventListener('DOMContentLoaded', loadSiteShell);
