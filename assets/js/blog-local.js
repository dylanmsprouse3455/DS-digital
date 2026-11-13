/* Blog-only search and category filters. No network calls or publishing actions. */
(() => {
  'use strict';
  const root = document.querySelector('.local-blog');
  if (!root) return;
  const search = root.querySelector('#local-blog-search');
  const filters = [...root.querySelectorAll('[data-blog-filter]')];
  const cards = [...root.querySelectorAll('[data-blog-article]')];
  const result = root.querySelector('#local-blog-result');
  const empty = root.querySelector('#local-blog-empty');
  let active = 'all';

  function update() {
    const query = search.value.toLocaleLowerCase().trim();
    let visible = 0;
    cards.forEach(card => {
      const category = (card.dataset.category || '').split(/\s+/);
      const region = card.dataset.region || '';
      const categoryMatch = active === 'all' || (
        active === 'local' ? region === 'greeneville' : category.includes(active)
      );
      const haystack = (card.dataset.search || card.textContent || '').toLocaleLowerCase();
      const matches = categoryMatch && (!query || haystack.includes(query));
      card.hidden = !matches;
      if (matches) visible += 1;
    });
    result.textContent = 'Showing ' + visible + ' article' + (visible === 1 ? '' : 's');
    empty.hidden = visible > 0;
    if (!visible) {
      empty.textContent = query
        ? 'No articles match that search. Try another term or clear the search.'
        : (active === 'all'
          ? 'There are no published articles yet.'
          : 'No published articles in this category yet. Verified local updates will appear here when available.');
    }
  }
  filters.forEach(button => button.addEventListener('click', () => {
    active = button.dataset.blogFilter;
    filters.forEach(filter => filter.setAttribute('aria-pressed', String(filter === button)));
    update();
  }));
  search.addEventListener('input', update);
  update();
})();