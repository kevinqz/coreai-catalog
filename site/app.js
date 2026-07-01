/**
 * Core AI Catalog — Explorer v3
 * Professional registry UI. SVG icons. Zero emoji. Vanilla JS.
 */
(function () {
  'use strict';

  const DATA_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/search-index.json';
  const TASKS_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/tasks/index.json';

  let MODELS = [];
  let FILTERED = [];
  let CAPABILITIES = new Set();
  let searchTimer = null;

  const $ = (id) => document.getElementById(id);

  // ── Helpers ──
  function scoreClass(s) {
    if (s >= 85) return 'score-a';
    if (s >= 70) return 'score-b';
    if (s >= 55) return 'score-c';
    if (s >= 40) return 'score-d';
    return 'score-f';
  }
  function gradeLetter(s) {
    if (s >= 85) return 'A';
    if (s >= 70) return 'B';
    if (s >= 55) return 'C';
    if (s >= 40) return 'D';
    return 'F';
  }
  function paramSortValue(p) {
    if (!p || p === 'unknown' || p === 'not_published') return 9999;
    const m = String(p).toUpperCase().match(/([\d.]+)\s*(B|M|K)?/);
    if (!m) return 9999;
    return parseFloat(m[1]) * ({ B: 1000, M: 1, K: 0.001 }[m[2]] || 1000);
  }
  function escapeHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
  function capChip(c) { return 'chip chip-cap-' + (c || '').replace(/_/g, '-'); }
  function devLabel(devs) {
    const parts = [];
    if (devs.includes('iphone')) parts.push('iPhone');
    if (devs.includes('ipad')) parts.push('iPad');
    if (devs.includes('mac')) parts.push('Mac');
    return parts.join(' / ') || 'Unknown';
  }
  function sourceLabel(sg) {
    if (sg === 'official') return 'Apple recipe';
    if (sg === 'zoo') return 'Community';
    if (sg === 'external') return 'External';
    return sg || '';
  }
  function licLabel(cu, name) {
    if (cu === 'likely') return name + ' (likely)';
    if (cu === 'check_license') return name + ' (check)';
    return name || 'Unknown';
  }

  // ── Data ──
  async function loadData() {
    try {
      const resp = await fetch(DATA_URL);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      MODELS = data.models || [];

      CAPABILITIES = new Set();
      MODELS.forEach(m => (m.capabilities || []).forEach(c => CAPABILITIES.add(c)));

      const sel = $('filter-capability');
      Array.from(CAPABILITIES).sort().forEach(cap => {
        const opt = document.createElement('option');
        opt.value = cap;
        opt.textContent = cap.replace(/-/g, ' ');
        sel.appendChild(opt);
      });

      $('search-box').placeholder = 'Search ' + MODELS.length + ' models\u2026';
      applyFilters();
    } catch (err) {
      $('model-grid').innerHTML = '<div class="empty-state"><p>Failed to load catalog data.</p><p><small>' + err.message + '</small></p></div>';
      $('result-count').textContent = 'Error';
    }
  }

  // ── Filter ──
  function applyFilters() {
    const search = $('search-box').value.toLowerCase().trim();
    const cap = $('filter-capability').value;
    const sI = $('filter-iphone').checked, sP = $('filter-ipad').checked, sM = $('filter-mac').checked;
    const lic = $('filter-license').value, src = $('filter-source').value, sort = $('sort-by').value;

    FILTERED = MODELS.filter(m => {
      if (search) {
        const hay = (m.name + ' ' + m.id + ' ' + (m.capabilities || []).join(' ') + ' ' + (m.family || '')).toLowerCase();
        if (!hay.includes(search)) return false;
      }
      if (cap && !(m.capabilities || []).includes(cap)) return false;
      const devs = m.devices || [];
      if (sI || sP || sM) {
        let ok = false;
        if (sI && devs.includes('iphone')) ok = true;
        if (sP && devs.includes('ipad')) ok = true;
        if (sM && devs.includes('mac')) ok = true;
        if (!ok) return false;
      }
      if (lic && m.commercial_use !== lic) return false;
      if (src && m.source_group !== src) return false;
      return true;
    });

    if (sort === 'name') FILTERED.sort((a, b) => a.name.localeCompare(b.name));
    else if (sort === 'params') FILTERED.sort((a, b) => paramSortValue(a.parameters) - paramSortValue(b.parameters));
    else FILTERED.sort((a, b) => b.readiness_score - a.readiness_score);

    renderGrid();
  }

  // ── Render ──
  function renderGrid() {
    const grid = $('model-grid');
    $('result-count').textContent = FILTERED.length + ' of ' + MODELS.length + ' models';

    if (!FILTERED.length) {
      grid.innerHTML = '<div class="empty-state"><p>No models match your filters.</p><p><small>Try adjusting capability, device, or license filters.</small></p></div>';
      return;
    }

    grid.innerHTML = FILTERED.map((m, i) => {
      const s = m.readiness_score;
      const caps = (m.capabilities || []).slice(0, 4).map(c =>
        '<span class="' + capChip(c) + '">' + c.replace(/-/g, ' ') + '</span>'
      ).join('');
      const licClass = m.commercial_use === 'likely' ? 'lic-ok' : 'lic-warn';
      const bench = m.benchmarks && m.benchmarks.length ? '<span class="card-bench">' + m.benchmarks.length + ' benchmarks</span>' : '';
      const delay = Math.min(i * 12, 180);

      return '<div class="model-card" data-id="' + m.id + '" style="animation-delay:' + delay + 'ms">' +
        '<div class="card-top">' +
          '<span class="card-name">' + escapeHtml(m.name) + '</span>' +
          '<span class="card-score ' + scoreClass(s) + '">' + s + ' ' + gradeLetter(s) + '</span>' +
        '</div>' +
        '<div class="card-caps">' + caps + '</div>' +
        '<div class="card-bottom">' +
          '<div class="card-meta-left">' +
            '<span class="card-devices">' + devLabel(m.devices || []) + '</span>' +
            '<span class="card-source">' + escapeHtml(sourceLabel(m.source_group)) + '</span>' +
          '</div>' +
          '<div class="card-meta-left">' +
            bench +
            '<span class="card-license ' + licClass + '">' + escapeHtml(licLabel(m.commercial_use, m.license)) + '</span>' +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');

    grid.querySelectorAll('.model-card').forEach(card =>
      card.addEventListener('click', () => showDetail(card.dataset.id))
    );
  }

  // ── Modal ──
  function showDetail(id) {
    const m = MODELS.find(x => x.id === id);
    if (!m) return;

    const s = m.readiness_score;
    const art = m.artifact || {};
    const hfUrl = art.huggingface_url || '';
    const hfRepo = art.huggingface_repo || '';
    const devList = (m.devices || []).map(d => '<span class="chip">' + d + '</span>').join('');
    const capsList = (m.capabilities || []).map(c => '<span class="' + capChip(c) + '">' + c + '</span>').join('');
    const benchRows = (m.benchmarks || []).map(b =>
      '<tr><td>' + (b.metric || '') + '</td><td><strong>' + b.value + '</strong> ' + (b.unit || '') + '</td><td>' + (b.device || '') + '</td><td>' + (b.compute_unit || '') + '</td></tr>'
    ).join('');

    $('modal-content').innerHTML =
      '<button class="modal-close" onclick="$(\'modal-overlay\').style.display=\'none\'" aria-label="Close">&times;</button>' +
      '<h2>' + escapeHtml(m.name) + '</h2>' +
      '<p class="modal-id">' + m.id + ' &middot; ' + escapeHtml(sourceLabel(m.source_group)) + '</p>' +
      '<div class="modal-score-row">' +
        '<span class="card-score ' + scoreClass(s) + '" style="font-size:.82rem;padding:.18rem.65rem">' + s + ' ' + gradeLetter(s) + '</span>' +
        '<span class="modal-score-desc">Readiness score &middot; ' + escapeHtml(m.maturity || 'unknown') + ' maturity</span>' +
      '</div>' +
      (capsList ? '<div class="modal-section"><h4>Capabilities</h4><div class="card-caps">' + capsList + '</div></div>' : '') +
      (devList ? '<div class="modal-section"><h4>Devices</h4><div class="card-caps">' + devList + '</div></div>' : '') +
      '<table class="modal-table">' +
        '<tr><td>Parameters</td><td>' + (m.parameters || 'not published') + '</td></tr>' +
        '<tr><td>Precision</td><td>' + (m.precision || 'unknown') + '</td></tr>' +
        '<tr><td>Quantization</td><td>' + (m.quantization || 'unknown') + '</td></tr>' +
        '<tr><td>License</td><td>' + escapeHtml(licLabel(m.commercial_use, m.license)) + '</td></tr>' +
        '<tr><td>Runtime</td><td>' + (m.runtime || 'unknown') + '</td></tr>' +
        '<tr><td>Runner</td><td>' + (m.runner || 'unknown') + '</td></tr>' +
      '</table>' +
      (benchRows ? '<div class="modal-section"><h4>Benchmarks</h4><table class="modal-table"><tr><td>Metric</td><td>Value</td><td>Device</td><td>Compute</td></tr>' + benchRows + '</table></div>' : '') +
      (m.notes ? '<div class="modal-section"><h4>Notes</h4><p style="font-size:.85rem;color:var(--text-secondary)">' + escapeHtml(m.notes) + '</p></div>' : '') +
      (hfUrl ? '<div class="modal-section"><h4>Artifact</h4><p><a href="' + hfUrl + '" target="_blank" rel="noopener">' + escapeHtml(hfRepo || hfUrl) + '</a></p></div>' : '') +
      '<div class="modal-section"><h4>Install</h4><pre><code>coreai-catalog install ' + m.id + '</code></pre></div>';

    $('modal-overlay').style.display = 'flex';
  }

  // ── Tasks ──
  async function loadTasks() {
    try {
      const resp = await fetch(TASKS_URL);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();

      const byCap = {};
      data.tasks.forEach(t => t.capabilities.forEach(c => { (byCap[c] = byCap[c] || []).push(t); }));

      $('task-list').innerHTML = Object.keys(byCap).sort().map(cap => {
        const syns = byCap[cap].map(t => t.task).sort();
        return '<div class="task-section">' +
          '<h3>' + cap.replace(/-/g, ' ') + ' <span class="task-count">' + syns.length + '</span></h3>' +
          '<div class="task-synonyms">' + syns.map(s => '<span class="chip">' + s + '</span>').join('') + '</div>' +
        '</div>';
      }).join('');
    } catch (err) {
      $('task-list').innerHTML = '<div class="empty-state"><p>Failed to load tasks.</p></div>';
    }
  }

  // ── Tabs ──
  function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        $(tab.dataset.tab).classList.add('active');
        if (tab.dataset.tab === 'tasks' && !$('task-list').innerHTML) loadTasks();
      });
    });
  }

  // ── Theme ──
  function initTheme() {
    const toggle = $('theme-toggle');
    toggle.addEventListener('click', () => {
      const cur = document.documentElement.getAttribute('data-theme');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('coreai-theme', next);
    });
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    loadData();

    $('search-box').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(applyFilters, 180);
    });
    ['filter-capability', 'filter-license', 'filter-source', 'sort-by'].forEach(id => $(id).addEventListener('change', applyFilters));
    ['filter-iphone', 'filter-ipad', 'filter-mac'].forEach(id => $(id).addEventListener('change', applyFilters));

    $('reset-filters').addEventListener('click', () => {
      $('search-box').value = '';
      $('filter-capability').value = '';
      $('filter-license').value = '';
      $('filter-source').value = '';
      $('filter-iphone').checked = true;
      $('filter-ipad').checked = true;
      $('filter-mac').checked = true;
      $('sort-by').value = 'score';
      applyFilters();
    });

    $('modal-overlay').addEventListener('click', e => { if (e.target === e.currentTarget) e.currentTarget.style.display = 'none'; });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') $('modal-overlay').style.display = 'none'; });
  });
})();
