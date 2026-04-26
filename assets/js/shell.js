window.initializeSiteShell = function initializeSiteShell() {
  const menuBtn = document.getElementById('menuBtn');
  const menu = document.getElementById('menu');
  if (!menuBtn || !menu) return;

  const closeMenu = () => {
    menu.classList.remove('active');
    menuBtn.classList.remove('active');
    menuBtn.setAttribute('aria-expanded', 'false');
  };

  menuBtn.setAttribute('aria-expanded', 'false');
  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = menu.classList.toggle('active');
    menuBtn.classList.toggle('active', isOpen);
    menuBtn.setAttribute('aria-expanded', String(isOpen));
  });

  menu.addEventListener('click', (e) => {
    if (e.target.matches('a')) closeMenu();
    e.stopPropagation();
  });

  document.addEventListener('click', closeMenu);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMenu();
  });

  const current = window.location.pathname.split('/').pop() || 'index.html';
  menu.querySelectorAll('a').forEach((link) => {
    const href = link.getAttribute('href');
    if (href === current) {
      link.classList.add('active-link');
      link.setAttribute('aria-current', 'page');
    }
  });
};
