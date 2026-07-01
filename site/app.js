/**
 * Core AI Catalog — Explorer v4
 * Fixed: modal close, CSS shorthand, device labels, active filter pills.
 */
(function () {
  'use strict';

  var DATA_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/search-index.json';
  var TASKS_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/tasks/index.json';

  var MODELS = [];
  var FILTERED = [];
  var CAPABILITIES = {};
  var searchTimer = null;

  function $(id) { return document.getElementById(id); }

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
    var m = String(p).toUpperCase().match(/([\d.]+)\s*(B|M|K)?/);
    if (!m) return 9999;
    return parseFloat(m[1]) * ({ B: 1000, M: 1, K: 0.001 }[m[2]] || 1000);
  }
  function escapeHtml(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }
  function capChip(c) { return 'chip chip-cap-' + (c || '').replace(/_/g, '-'); }

  function devLabel(devs) {
    var parts = [];
    if (devs.indexOf('iphone') >= 0) parts.push('iPhone');
    if (devs.indexOf('ipad') >= 0) parts.push('iPad');
    if (devs.indexOf('mac') >= 0) parts.push('Mac');
    return parts.join(' · ') || 'Unknown';
  }
  function sourceLabel(sg) {
    if (sg === 'official') return 'Apple recipe';
    if (sg === 'zoo') return 'Community';
    if (sg === 'external') return 'External';
    return sg || '';
  }
  function licLabel(cu, name) {
    if (cu === 'likely') return name + ' (likely OK)';
    if (cu === 'check_license') return name + ' (check)';
    return name || 'Unknown';
  }
  function devChipLabel(d) {
    return d.charAt(0).toUpperCase() + d.slice(1);
  }

  // ── Data ──
  async function loadData() {
    try {
      var resp = await fetch(DATA_URL);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();
      MODELS = data.models || [];

      CAPABILITIES = {};
      MODELS.forEach(function (m) {
        (m.capabilities || []).forEach(function (c) { CAPABILITIES[c] = true; });
      });

      var sel = $('filter-capability');
      Object.keys(CAPABILITIES).sort().forEach(function (cap) {
        var opt = document.createElement('option');
        opt.value = cap;
        opt.textContent = cap.replace(/-/g, ' ');
        sel.appendChild(opt);
      });

      $('search-box').placeholder = 'Search ' + MODELS.length + ' models\u2026';
      applyFilters();
    } catch (err) {
      $('model-grid').innerHTML = '<div class="empty-state"><p>Failed to load catalog data.</p></div>';
      $('result-count').textContent = 'Error';
    }
  }

  // ── Filter ──
  function applyFilters() {
    var search = $('search-box').value.toLowerCase().trim();
    var cap = $('filter-capability').value;
    var sI = $('filter-iphone').checked, sP = $('filter-ipad').checked, sM = $('filter-mac').checked;
    var lic = $('filter-license').value, src = $('filter-source').value, sort = $('sort-by').value;

    FILTERED = MODELS.filter(function (m) {
      if (search) {
        var hay = (m.name + ' ' + m.id + ' ' + (m.capabilities || []).join(' ') + ' ' + (m.family || '')).toLowerCase();
        if (hay.indexOf(search) < 0) return false;
      }
      if (cap && (m.capabilities || []).indexOf(cap) < 0) return false;
      var devs = m.devices || [];
      if (sI || sP || sM) {
        var ok = false;
        if (sI && devs.indexOf('iphone') >= 0) ok = true;
        if (sP && devs.indexOf('ipad') >= 0) ok = true;
        if (sM && devs.indexOf('mac') >= 0) ok = true;
        if (!ok) return false;
      }
      if (lic && m.commercial_use !== lic) return false;
      if (src && m.source_group !== src) return false;
      return true;
    });

    if (sort === 'name') FILTERED.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (sort === 'params') FILTERED.sort(function (a, b) { return paramSortValue(a.parameters) - paramSortValue(b.parameters); });
    else FILTERED.sort(function (a, b) { return b.readiness_score - a.readiness_score; });

    renderActiveFilters(search, cap, sI, sP, sM, lic, src);
    renderGrid();
  }

  // ── Active filter pills ──
  function renderActiveFilters(search, cap, sI, sP, sM, lic, src) {
    var pills = [];
    if (search) pills.push({ label: '"' + search + '"', clear: function () { $('search-box').value = ''; } });
    if (cap) pills.push({ label: cap.replace(/-/g, ' '), clear: function () { $('filter-capability').value = ''; } });
    if (!sI) pills.push({ label: 'no iPhone', clear: function () { $('filter-iphone').checked = true; } });
    if (!sP) pills.push({ label: 'no iPad', clear: function () { $('filter-ipad').checked = true; } });
    if (!sM) pills.push({ label: 'no Mac', clear: function () { $('filter-mac').checked = true; } });
    if (lic) pills.push({ label: lic === 'likely' ? 'Commercial: likely' : 'Check license', clear: function () { $('filter-license').value = ''; } });
    if (src) pills.push({ label: sourceLabel(src), clear: function () { $('filter-source').value = ''; } });

    var container = $('active-filters');
    if (!pills.length) { container.innerHTML = ''; return; }

    container.innerHTML = pills.map(function (p, i) {
      return '<span class="filter-pill" data-idx="' + i + '">' + escapeHtml(p.label) + '</span>';
    }).join('');

    container.querySelectorAll('.filter-pill').forEach(function (el, i) {
      el.addEventListener('click', function () {
        pills[i].clear();
        applyFilters();
      });
    });
  }

  // ── Render ──
  function renderGrid() {
    var grid = $('model-grid');
    $('result-count').textContent = FILTERED.length + ' of ' + MODELS.length + ' models';

    if (!FILTERED.length) {
      grid.innerHTML = '<div class="empty-state"><p>No models match your filters.</p><p><small>Try adjusting capability, device, or license filters.</small></p></div>';
      return;
    }

    grid.innerHTML = FILTERED.map(function (m, i) {
      var s = m.readiness_score;
      var caps = (m.capabilities || []).slice(0, 4).map(function (c) {
        return '<span class="' + capChip(c) + '">' + c.replace(/-/g, ' ') + '</span>';
      }).join('');
      var licClass = m.commercial_use === 'likely' ? 'lic-ok' : 'lic-warn';
      var bench = m.benchmarks && m.benchmarks.length ? '<span class="card-bench">' + m.benchmarks.length + ' benchmarks</span>' : '';
      var delay = Math.min(i * 12, 180);

      return '<div class="model-card" data-id="' + m.id + '" style="animation-delay:' + delay + 'ms">' +
        '<div class="card-top">' +
          '<span class="card-name">' + escapeHtml(m.name) + '</span>' +
          '<span class="card-score ' + scoreClass(s) + '">' + s + ' ' + gradeLetter(s) + '</span>' +
        '</div>' +
        '<div class="card-caps">' + caps + '</div>' +
        '<div class="card-bottom">' +
          '<div class="card-meta">' +
            '<span class="card-devices">' + devLabel(m.devices || []) + '</span>' +
          '</div>' +
          '<div class="card-meta">' +
            bench +
            '<span class="card-license ' + licClass + '">' + escapeHtml(m.license || '?') + '</span>' +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');

    grid.querySelectorAll('.model-card').forEach(function (card) {
      card.addEventListener('click', function () { showDetail(card.dataset.id); });
    });
  }

  // ── Modal ──
  function closeModal() {
    $('modal-overlay').style.display = 'none';
  }

  function showDetail(id) {
    var m = MODELS.find(function (x) { return x.id === id; });
    if (!m) return;

    var s = m.readiness_score;
    var art = m.artifact || {};
    var hfUrl = art.huggingface_url || '';
    var hfRepo = art.huggingface_repo || '';
    var devList = (m.devices || []).map(function (d) { return '<span class="chip">' + devChipLabel(d) + '</span>'; }).join('');
    var capsList = (m.capabilities || []).map(function (c) { return '<span class="' + capChip(c) + '">' + c + '</span>'; }).join('');
    var benchRows = (m.benchmarks || []).map(function (b) {
      return '<tr><td>' + (b.metric || '') + '</td><td><strong>' + b.value + '</strong> ' + (b.unit || '') + '</td><td>' + (b.device || '') + '</td><td>' + (b.compute_unit || '') + '</td></tr>';
    }).join('');

    $('modal-content').innerHTML =
      '<button class="modal-close" id="modal-close-btn" aria-label="Close">&times;</button>' +
      '<h2>' + escapeHtml(m.name) + '</h2>' +
      '<p class="modal-id">' + m.id + ' &middot; ' + escapeHtml(sourceLabel(m.source_group)) + '</p>' +
      '<div class="modal-score-row">' +
        '<span class="modal-score ' + scoreClass(s) + '">' + s + ' ' + gradeLetter(s) + '</span>' +
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

    // Wire close button via addEventListener (not inline onclick)
    $('modal-close-btn').addEventListener('click', closeModal);
  }

  // ── Tasks ──
  async function loadTasks() {
    try {
      var resp = await fetch(TASKS_URL);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var data = await resp.json();

      var byCap = {};
      data.tasks.forEach(function (t) { t.capabilities.forEach(function (c) { (byCap[c] = byCap[c] || []).push(t); }); });

      $('task-list').innerHTML = Object.keys(byCap).sort().map(function (cap) {
        var syns = byCap[cap].map(function (t) { return t.task; }).sort();
        return '<div class="task-section">' +
          '<h3>' + cap.replace(/-/g, ' ') + ' <span class="task-count">' + syns.length + '</span></h3>' +
          '<div class="task-synonyms">' + syns.map(function (s) { return '<span class="chip">' + escapeHtml(s) + '</span>'; }).join('') + '</div>' +
        '</div>';
      }).join('');
    } catch (err) {
      $('task-list').innerHTML = '<div class="empty-state"><p>Failed to load tasks.</p></div>';
    }
  }

  // ── Tabs ──
  function initTabs() {
    document.querySelectorAll('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        document.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('active'); });
        document.querySelectorAll('.tab-content').forEach(function (c) { c.classList.remove('active'); });
        tab.classList.add('active');
        $(tab.dataset.tab).classList.add('active');
        if (tab.dataset.tab === 'tasks' && !$('task-list').innerHTML) loadTasks();
      });
    });
  }

  // ── Theme ──
  function initTheme() {
    $('theme-toggle').addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('coreai-theme', next);
    });
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initTabs();
    loadData();

    $('search-box').addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(applyFilters, 180);
    });
    ['filter-capability', 'filter-license', 'filter-source', 'sort-by'].forEach(function (id) {
      $(id).addEventListener('change', applyFilters);
    });
    ['filter-iphone', 'filter-ipad', 'filter-mac'].forEach(function (id) {
      $(id).addEventListener('change', applyFilters);
    });

    $('reset-filters').addEventListener('click', function () {
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

    $('modal-overlay').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeModal();
    });

    // ── MCP copy-to-clipboard ──
    document.querySelectorAll('.btn-copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var target = btn.dataset.copy;
        var el = $('mcp-' + target);
        if (!el) return;
        var text = el.querySelector('code') ? el.querySelector('code').textContent : el.textContent;

        function flashCopied() {
          var orig = btn.textContent;
          btn.textContent = 'Copied';
          btn.classList.add('copied');
          setTimeout(function () { btn.textContent = orig; btn.classList.remove('copied'); }, 1500);
        }

        if (navigator.clipboard) {
          navigator.clipboard.writeText(text.trim()).then(flashCopied, flashCopied);
        } else {
          var ta = document.createElement('textarea');
          ta.value = text.trim();
          document.body.appendChild(ta);
          ta.select();
          try { document.execCommand('copy'); } catch (e) {}
          document.body.removeChild(ta);
          flashCopied();
        }
      });
    });
  });
})();
