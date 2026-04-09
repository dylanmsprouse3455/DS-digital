window.initializeSiteShell = function initializeSiteShell() {
  const menuBtn = document.getElementById('menuBtn');
  const menu = document.getElementById('menu');
  if (!menuBtn || !menu) return;

  const closeMenu = () => {
    menu.classList.remove('active');
    menuBtn.classList.remove('active');
  };

  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('active');
    menuBtn.classList.toggle('active');
  });

  menu.addEventListener('click', (e) => e.stopPropagation());

  document.addEventListener('click', closeMenu);

  const current = window.location.pathname.split('/').pop() || 'index.html';
  menu.querySelectorAll('a').forEach((link) => {
    const href = link.getAttribute('href');
    if (href === current) {
      link.classList.add('active-link');
    }
  });
};
