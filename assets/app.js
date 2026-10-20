/* Tech Brief: lightweight, dependency-free, safe static RSS news viewer. */
(() => {
  'use strict';

  const PUBLISHERS = {
    verge: { name: 'The Verge', short: 'V', website: 'https://www.theverge.com', label: 'THE VERGE' },
    wired: { name: 'WIRED', short: 'W', website: 'https://www.wired.com', label: 'WIRED' },
    mit: { name: 'MIT Technology Review', short: 'M', website: 'https://www.technologyreview.com', label: 'MIT TECHNOLOGY REVIEW' },
    ars: { name: 'Ars Technica', short: 'A', website: 'https://arstechnica.com', label: 'ARS TECHNICA' }
  };

  const $ = (selector) => document.querySelector(selector);
  const cfg = window.TECH_BRIEF_CONFIG || {};
  const pageSize = Number.isInteger(cfg.pageSize) && cfg.pageSize > 0 ? Math.min(cfg.pageSize, 60) : 18;
  const state = { articles: [], sources: {}, updatedAt: null, source: 'all', query: '', range: 'all', visible: pageSize, pending: false, hasLoaded: false };

  const brand = $('#brandName');
  if (typeof cfg.siteName === 'string') brand.textContent = cfg.siteName;
  if (typeof cfg.eyebrow === 'string') $('#eyebrow').textContent = cfg.eyebrow;

  function safeUrl(input) {
    try {
      const url = new URL(input);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
    } catch { return null; }
  }
  function parseTime(input) {
    if (!input) return NaN;
    const ms = Date.parse(input);
    return Number.isFinite(ms) ? ms : NaN;
  }
  function relativeTime(input) {
    const ts = parseTime(input);
    if (!Number.isFinite(ts)) return 'Date unavailable';
    const difference = Math.max(0, Date.now() - ts);
    const minutes = Math.floor(difference / 60000);
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(ts));
  }
  function dateTitle(input) {
    const ts = parseTime(input);
    return Number.isFinite(ts) ? new Date(ts).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Date unavailable';
  }
  function tag(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function emptyState(title, message, source) {
    const el = tag('div', 'empty-state');
    el.append(tag('div', 'empty-mark', '✳'), tag('h3', '', title), tag('p', '', message));
    if (source && PUBLISHERS[source]) {
      const a = tag('a', 'empty-link', `Visit ${PUBLISHERS[source].name} ↗`);
      a.href = PUBLISHERS[source].website;
      a.target = '_blank'; a.rel = 'noopener noreferrer';
      el.append(a);
    }
    return el;
  }

  function createCard(item) {
    const publisher = PUBLISHERS[item.source];
    const articleUrl = safeUrl(item.url);
    if (!publisher || !articleUrl || !item.title) return null;
    const card = tag('a', 'news-card');
    card.href = articleUrl; card.target = '_blank'; card.rel = 'noopener noreferrer';
    card.setAttribute('aria-label', `${item.title} — ${publisher.name} (opens in a new tab)`);
    const visual = tag('div', 'card-visual');
    const fallback = tag('div', `card-placeholder ${item.source}`);
    fallback.append(tag('span', '', publisher.short));
    visual.append(fallback);
    const imageUrl = safeUrl(item.image);
    if (imageUrl) {
      const img = document.createElement('img');
      img.className = 'card-photo'; img.src = imageUrl; img.alt = '';
      img.loading = 'lazy'; img.decoding = 'async';
      img.addEventListener('error', () => { img.classList.add('image-failed'); });
      visual.append(img, tag('div', 'image-overlay'));
    }
    const article = tag('div', 'card-article');
    const kicker = tag('div', 'card-kicker');
    kicker.append(tag('span', `publisher-dot ${item.source}`), tag('span', 'card-publisher', publisher.name));
    if (item.category) kicker.append(tag('span', 'card-category', item.category));
    article.append(kicker, tag('h3', 'card-title', item.title));
    if (item.summary) article.append(tag('p', 'card-summary', item.summary));
    const meta = tag('div', 'card-meta');
    const time = tag('time', '', relativeTime(item.published_at));
    if (item.published_at) { time.dateTime = item.published_at; time.title = dateTitle(item.published_at); }
    const readLink = tag('span', 'card-link-label', 'Read article');
    readLink.append(tag('span', '', '↗'));
    meta.append(time, readLink);
    article.append(meta); card.append(visual, article);
    return card;
  }

  function matchedArticles() {
    const now = Date.now();
    const query = state.query.trim().toLocaleLowerCase();
    const windowMs = state.range === 'day' ? 86400000 : state.range === 'week' ? 7 * 86400000 : 0;
    return state.articles.filter((article) => {
      if (state.source !== 'all' && article.source !== state.source) return false;
      if (query && !`${article.title || ''} ${article.summary || ''} ${article.category || ''}`.toLocaleLowerCase().includes(query)) return false;
      if (windowMs) {
        const ts = parseTime(article.published_at);
        if (!Number.isFinite(ts) || ts > now + 3600000 || now - ts > windowMs) return false;
      }
      return true;
    });
  }

  function paintCounts() {
    $('#count-all').textContent = state.articles.length || '0';
    for (const key of Object.keys(PUBLISHERS)) {
      const count = state.articles.filter((a) => a.source === key).length;
      $(`#count-${key}`).textContent = count;
    }
  }

  function render() {
    const label = state.source === 'all' ? 'ALL PUBLICATIONS' : PUBLISHERS[state.source].label;
    $('#sourceHeadingLabel').textContent = label;
    $('#sectionTitle').textContent = state.source === 'all' ? 'Latest stories' : PUBLISHERS[state.source].name;
    const matched = matchedArticles();
    $('#storyTotal').textContent = matched.length;
    const grid = $('#feedGrid');
    grid.replaceChildren();
    grid.setAttribute('aria-busy', 'false');
    if (!state.hasLoaded && state.pending) return;
    if (!state.articles.length) {
      grid.append(emptyState('Your newsroom is nearly ready', 'The first RSS update has not completed yet. In GitHub, open Actions → Update tech news → Run workflow. The headlines will appear here automatically after the JSON file is published.', state.source === 'all' ? null : state.source));
    } else if (!matched.length) {
      grid.append(emptyState('No stories in this view', 'Try another publication, expand the date range, or clear the search to see more articles.', state.source === 'all' ? null : state.source));
    } else {
      const fragment = document.createDocumentFragment();
      for (const item of matched.slice(0, state.visible)) {
        const card = createCard(item);
        if (card) fragment.append(card);
      }
      grid.append(fragment);
    }
    $('#loadMoreArea').hidden = state.visible >= matched.length;
    $('#loadMore').textContent = `Load more stories (${Math.min(pageSize, Math.max(0, matched.length - state.visible))} more) ↓`;
    paintCounts();
  }

  function setSource(source) {
    if (source !== 'all' && !PUBLISHERS[source]) return;
    state.source = source;
    state.visible = pageSize;
    for (const button of document.querySelectorAll('.source-button')) {
      const active = button.dataset.source === source;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    render();
    $('#mainScroll').scrollTo({ top: 0, behavior: 'auto' });
  }
  document.querySelectorAll('[data-source]').forEach((button) => {
    button.addEventListener('click', () => setSource(button.dataset.source));
  });
  $('#searchInput').addEventListener('input', (event) => {
    state.query = event.target.value;
    state.visible = pageSize;
    render();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === '/' && !event.altKey && !event.metaKey && !event.ctrlKey
        && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      event.preventDefault();
      $('#searchInput').focus();
    }
    if (event.key === 'Escape' && document.activeElement === $('#searchInput')) {
      $('#searchInput').value = '';
      state.query = '';
      state.visible = pageSize;
      render();
    }
  });
  $('#dateFilter').addEventListener('change', (event) => {
    state.range = event.target.value;
    state.visible = pageSize;
    render();
  });
  $('#loadMore').addEventListener('click', () => {
    state.visible += pageSize;
    render();
  });

  const storedTheme = (() => { try { return localStorage.getItem('tech-brief-theme'); } catch { return null; } })();
  if (storedTheme === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
  $('#themeToggle').addEventListener('click', () => {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (dark) document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', 'dark');
    try { localStorage.setItem('tech-brief-theme', dark ? 'light' : 'dark'); } catch { /* storage may be blocked in embeds */ }
  });

  async function loadNews() {
    if (state.pending) return;
    state.pending = true;
    $('#refreshButton').classList.add('is-busy');
    $('#refreshButton').disabled = true;
    try {
      const response = await fetch(`./data/news.json?v=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!data || !Array.isArray(data.articles)) throw new Error('Unexpected feed format');
      state.articles = data.articles.filter((article) => article && typeof article === 'object' && PUBLISHERS[article.source] && safeUrl(article.url) && article.title)
        .sort((a, b) => (parseTime(b.published_at) || 0) - (parseTime(a.published_at) || 0));
      state.updatedAt = data.updated_at || null;
      state.sources = data.sources && typeof data.sources === 'object' ? data.sources : {};
      state.hasLoaded = true;
      const broken = Object.entries(state.sources).filter(([, stat]) => stat && stat.status !== 'ok');
      const notice = $('#notice');
      if (broken.length && state.articles.length) {
        const names = broken.map(([id]) => PUBLISHERS[id]?.name || id).join(', ');
        notice.textContent = `Some sources could not be reached on the last update (${names}). Cached headlines are shown where available.`;
        notice.hidden = false;
      } else {
        notice.hidden = true;
      }
      if (state.updatedAt) {
        const title = dateTitle(state.updatedAt);
        $('#updatedLabel').textContent = `Feed updated ${relativeTime(state.updatedAt)}`;
        $('#updatedLabel').title = `Published snapshot: ${title}`;
        $('#sidebarStatus').textContent = `Latest snapshot: ${relativeTime(state.updatedAt)}`;
      } else {
        $('#updatedLabel').textContent = 'Awaiting the first news update';
        $('#sidebarStatus').textContent = 'First update pending';
      }
      if (state.articles.length && !broken.length) {
        $('#sidebarStatus').textContent = `${state.articles.length} stories ready to explore`;
      }
    } catch (error) {
      state.hasLoaded = true;
      const notice = $('#notice');
      notice.textContent = 'Unable to load the published feed file. Confirm data/news.json is in the GitHub repository and refresh the page.';
      notice.hidden = false;
      $('#updatedLabel').textContent = 'Feed temporarily unavailable';
      $('#sidebarStatus').textContent = 'News connection unavailable';
      console.error('Tech Brief fetch failed:', error);
    } finally {
      state.pending = false;
      $('#refreshButton').classList.remove('is-busy');
      $('#refreshButton').disabled = false;
      render();
    }
  }
  $('#refreshButton').addEventListener('click', loadNews);
  loadNews();
})();
