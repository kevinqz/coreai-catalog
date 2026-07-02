/**
 * Core AI Catalog — Explorer v5
 * Tighter, cleaner, faster.
 */
(function () {
  'use strict';

  var DATA_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/search-index.json';
  var TASKS_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/tasks/index.json';

  var MODELS = [];
  var FILTERED = [];
  var CAPABILITIES = {};
  var searchTimer = null;
  var deviceFilters = { iphone: true, ipad: true, mac: true };

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
    return { official: 'Apple', zoo: 'Community', external: 'External' }[sg] || '';
  }
  function licClass(cu) { return cu === 'likely' ? 'lic-ok' : 'lic-warn'; }
  function licIcon(cu) { return cu === 'likely' ? '' : ''; }

  // ── Score factor computation (matches catalog.py readiness_score) ──
  function scoreFactors(m) {
    var max = 100;
    var factors = [];
    function add(label, pts, condition) {
      factors.push({ label: label, points: pts, earned: condition });
    }
    var artAvail = (m.artifact && m.artifact.availability === 'available');
    add('Artifact available', 15, artAvail);
    add('License: commercial likely', 10, m.commercial_use === 'likely');
    var devs = m.devices || [];
    add('iPhone supported', 10, devs.indexOf('iphone') >= 0);
    add('Mac supported', 10, devs.indexOf('mac') >= 0);
    add('Has benchmark', 10, !!(m.benchmarks && m.benchmarks.length));
    add('Stock runtime', 10, m.stock_runtime === true);
    add('No custom kernel', 5, m.custom_kernel === false);
    add('No patch needed', 5, m.patch_required === false);
    add('No AOT needed', 5, m.aot_required === false);
    add('Status: confirmed', 10, m.status === 'confirmed');
    var confPts = 0;
    if (m.confidence === 'high') confPts = 5;
    else if (m.confidence === 'medium') confPts = 3;
    else if (m.confidence === 'low') confPts = -10;
    add('Confidence: ' + (m.confidence || 'unknown') + ' (' + (confPts >= 0 ? '+' : '') + confPts + ')', confPts, confPts !== 0);
    add('Maturity: stable/active', 5, m.maturity === 'stable' || m.maturity === 'active');
    var earned = factors.filter(function (f) { return f.earned; }).reduce(function (s, f) { return s + f.points; }, 0);
    return { factors: factors, earned: Math.max(0, Math.min(100, earned)), max: max };
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
      $('model-grid').innerHTML = '<div class="empty-state"><p>Failed to load data.</p></div>';
      $('result-count').textContent = 'Error';
    }
  }

  // ── Filter ──
  function applyFilters() {
    var search = $('search-box').value.toLowerCase().trim();
    var cap = $('filter-capability').value;
    var lic = $('filter-license').value;
    var src = $('filter-source').value;
    var sort = $('sort-by').value;

    FILTERED = MODELS.filter(function (m) {
      if (search) {
        var hay = (m.name + ' ' + m.id + ' ' + (m.capabilities || []).join(' ') + ' ' + (m.family || '')).toLowerCase();
        if (hay.indexOf(search) < 0) return false;
      }
      if (cap && (m.capabilities || []).indexOf(cap) < 0) return false;
      var devs = m.devices || [];
      var anyDevice = deviceFilters.iphone || deviceFilters.ipad || deviceFilters.mac;
      if (anyDevice) {
        var ok = false;
        if (deviceFilters.iphone && devs.indexOf('iphone') >= 0) ok = true;
        if (deviceFilters.ipad && devs.indexOf('ipad') >= 0) ok = true;
        if (deviceFilters.mac && devs.indexOf('mac') >= 0) ok = true;
        if (!ok) return false;
      }
      if (lic && m.commercial_use !== lic) return false;
      if (src && m.source_group !== src) return false;
      return true;
    });

    if (sort === 'name') FILTERED.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (sort === 'params') FILTERED.sort(function (a, b) { return paramSortValue(a.parameters) - paramSortValue(b.parameters); });
    else FILTERED.sort(function (a, b) { return b.readiness_score - a.readiness_score; });

    renderPills(search, cap, lic, src);
    renderGrid();
  }

  // ── Filter pills ──
  function renderPills(search, cap, lic, src) {
    var pills = [];
    if (search) pills.push({ label: '"' + search + '"', clear: function () { $('search-box').value = ''; } });
    if (cap) pills.push({ label: cap.replace(/-/g, ' '), clear: function () { $('filter-capability').value = ''; } });
    if (!deviceFilters.iphone) pills.push({ label: 'no iPhone', clear: function () { toggleDevice('iphone', true); } });
    if (!deviceFilters.ipad) pills.push({ label: 'no iPad', clear: function () { toggleDevice('ipad', true); } });
    if (!deviceFilters.mac) pills.push({ label: 'no Mac', clear: function () { toggleDevice('mac', true); } });
    if (lic) pills.push({ label: lic === 'likely' ? 'Commercial: likely' : 'Check license', clear: function () { $('filter-license').value = ''; } });
    if (src) pills.push({ label: sourceLabel(src), clear: function () { $('filter-source').value = ''; } });

    var c = $('active-filters');
    if (!pills.length) { c.innerHTML = ''; return; }
    c.innerHTML = pills.map(function (p, i) {
      return '<span class="filter-pill" data-idx="' + i + '">' + escapeHtml(p.label) + '</span>';
    }).join('');
    c.querySelectorAll('.filter-pill').forEach(function (el, i) {
      el.addEventListener('click', function () { pills[i].clear(); applyFilters(); });
    });
  }

  function toggleDevice(d, val) {
    deviceFilters[d] = val;
    var btn = document.querySelector('.seg[data-filter="' + d + '"]');
    if (btn) { val ? btn.classList.add('active') : btn.classList.remove('active'); }
  }

  // ── Render ──
  function renderGrid() {
    var grid = $('model-grid');
    $('result-count').textContent = FILTERED.length + ' of ' + MODELS.length + ' models';

    if (!FILTERED.length) {
      grid.innerHTML = '<div class="empty-state">No models match your filters.</div>';
      return;
    }

    grid.innerHTML = FILTERED.map(function (m, i) {
      var s = m.readiness_score;
      var caps = (m.capabilities || []).slice(0, 3).map(function (c) {
        return '<span class="' + capChip(c) + '">' + c.replace(/-/g, ' ') + '</span>';
      }).join('');
      var bench = m.benchmarks && m.benchmarks.length ? '<span class="card-bench">' + m.benchmarks.length + ' bench</span>' : '';
      var delay = Math.min(i * 10, 120);

      return '<div class="model-card" data-id="' + m.id + '" style="animation-delay:' + delay + 'ms">' +
        '<div class="card-top">' +
          '<span class="card-name">' + escapeHtml(m.name) + '</span>' +
          '<span class="card-score ' + scoreClass(s) + '" title="Click to see score breakdown">' + s + ' ' + gradeLetter(s) + '</span>' +
        '</div>' +
        '<div class="card-caps">' + caps + '</div>' +
        '<div class="card-bottom">' +
          '<span class="card-meta">' +
            '<span>' + devLabel(m.devices || []) + '</span>' +
            '<span> · ' + escapeHtml(sourceLabel(m.source_group)) + '</span>' +
          '</span>' +
          '<span class="card-meta">' +
            bench +
            '<span class="card-license ' + licClass(m.commercial_use) + '">' + escapeHtml(m.license || '') + '</span>' +
          '</span>' +
        '</div>' +
      '</div>';
    }).join('');

    grid.querySelectorAll('.model-card').forEach(function (card) {
      card.addEventListener('click', function () { showDetail(card.dataset.id); });
    });

    // Score badge click → toggle inline breakdown (not card click)
    grid.querySelectorAll('.card-score').forEach(function (badge) {
      badge.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleScoreBreakdown(badge);
      });
    });
  }

  // ── Score Breakdown (card inline) ──
  function scoreBreakdownHTML(m) {
    var s = scoreFactors(m);
    var earned = s.earned;
    var grade = gradeLetter(earned);
    var desc = '';
    if (earned >= 85) desc = 'Production-ready';
    else if (earned >= 70) desc = 'Good, minor gaps';
    else if (earned >= 55) desc = 'Usable, verify caveats';
    else if (earned >= 40) desc = 'Experimental';
    else desc = 'Early / unverified';

    var rows = s.factors.map(function (f) {
      var cls = f.earned ? 'sb-earned' : 'sb-missed';
      var sign = f.points >= 0 ? '+' : '';
      var icon = f.earned ? '&#10003;' : '&middot;';
      return '<div class="sb-row ' + cls + '">' +
        '<span class="sb-icon">' + icon + '</span>' +
        '<span class="sb-label">' + escapeHtml(f.label) + '</span>' +
        '<span class="sb-pts">' + sign + f.points + '</span>' +
      '</div>';
    }).join('');

    return '<div class="sb-header">' +
      '<span class="card-score ' + scoreClass(earned) + '">' + earned + ' ' + grade + '</span>' +
      '<span class="sb-desc">' + escapeHtml(desc) + '</span>' +
      '<span class="sb-total">' + earned + ' / 100</span>' +
    '</div>' +
    '<div class="sb-factors">' + rows + '</div>';
  }

  function toggleScoreBreakdown(badge) {
    var card = badge.closest('.model-card');
    if (!card) return;
    // Remove existing
    var existing = card.querySelector('.score-breakdown');
    if (existing) { existing.remove(); badge.classList.remove('active'); return; }

    // Close any other open breakdowns
    document.querySelectorAll('.score-breakdown').forEach(function (el) { el.remove(); });
    document.querySelectorAll('.card-score.active').forEach(function (el) { el.classList.remove('active'); });

    var m = MODELS.find(function (x) { return x.id === card.dataset.id; });
    if (!m) return;
    badge.classList.add('active');
    var div = document.createElement('div');
    div.className = 'score-breakdown';
    div.innerHTML = scoreBreakdownHTML(m);
    div.addEventListener('click', function (e) { e.stopPropagation(); });
    card.appendChild(div);
  }

  // ── Modal ──
  function closeModal() { $('modal-overlay').style.display = 'none'; }

  function showDetail(id) {
    var m = MODELS.find(function (x) { return x.id === id; });
    if (!m) return;
    var s = m.readiness_score;
    var art = m.artifact || {};
    var hfUrl = art.huggingface_url || '';
    var hfRepo = art.huggingface_repo || '';
    var devList = (m.devices || []).map(function (d) {
      return '<span class="chip">' + (d.charAt(0).toUpperCase() + d.slice(1)) + '</span>';
    }).join('');
    var capsList = (m.capabilities || []).map(function (c) {
      return '<span class="' + capChip(c) + '">' + c + '</span>';
    }).join('');
    var benchRows = (m.benchmarks || []).map(function (b) {
      return '<tr><td>' + (b.metric || '') + '</td><td><strong>' + b.value + '</strong> ' + (b.unit || '') + '</td><td>' + (b.device || '') + '</td><td>' + (b.compute_unit || '') + '</td></tr>';
    }).join('');

    $('modal-content').innerHTML =
      '<button class="modal-close" id="modal-close-btn" aria-label="Close">&times;</button>' +
      '<h2>' + escapeHtml(m.name) + '</h2>' +
      '<p class="modal-id">' + m.id + ' &middot; ' + escapeHtml(sourceLabel(m.source_group)) + '</p>' +
      '<div class="modal-score-breakdown">' +
        scoreBreakdownHTML(m) +
      '</div>' +
      (capsList ? '<div class="modal-section"><h4>Capabilities</h4><div class="card-caps">' + capsList + '</div></div>' : '') +
      (devList ? '<div class="modal-section"><h4>Devices</h4><div class="card-caps">' + devList + '</div></div>' : '') +
      '<table class="modal-table">' +
        '<tr><td>Parameters</td><td>' + (m.parameters || 'not published') + '</td></tr>' +
        '<tr><td>Precision</td><td>' + (m.precision || 'unknown') + '</td></tr>' +
        '<tr><td>Quantization</td><td>' + (m.quantization || 'unknown') + '</td></tr>' +
        '<tr><td>License</td><td>' + escapeHtml(m.license || '?') + ' (' + escapeHtml(m.commercial_use || '?') + ')</td></tr>' +
        '<tr><td>Runtime</td><td>' + (m.runtime || 'unknown') + '</td></tr>' +
      '</table>' +
      (benchRows ? '<div class="modal-section"><h4>Benchmarks</h4><table class="modal-table"><tr><td>Metric</td><td>Value</td><td>Device</td><td>Compute</td></tr>' + benchRows + '</table></div>' : '') +
      (m.notes ? '<div class="modal-section"><h4>Notes</h4><p style="font-size:.8rem;color:var(--text-2)">' + escapeHtml(m.notes) + '</p></div>' : '') +

      '<div class="modal-section"><h4>Provenance</h4>' +
        '<div class="provenance-chain">' +
          (art.huggingface_repo ?
            '<div class="prov-step"><span class="prov-dot"></span>' +
            '<span class="prov-text">Artifact: <a href="' + (hfUrl || '#') + '" target="_blank" rel="noopener">' + escapeHtml(art.huggingface_repo) + '</a></span></div>' : '') +
          (art.github_source ?
            '<div class="prov-step"><span class="prov-dot"></span>' +
            '<span class="prov-text">Conversion: <a href="https://github.com/' + escapeHtml(art.github_source) + '" target="_blank" rel="noopener">' + escapeHtml(art.github_source) + '</a></span></div>' : '') +
          (art.apple_export_recipe !== undefined ?
            '<div class="prov-step"><span class="prov-dot ' + (art.apple_export_recipe ? 'prov-dot-apple' : 'prov-dot-community') + '"></span>' +
            '<span class="prov-text">' + (art.apple_export_recipe ? 'Apple official recipe' : (art.community_packaged ? 'Community packaged' : 'Independent')) + '</span></div>' : '') +
          (art.apple_hosted_artifact === false ?
            '<div class="prov-step"><span class="prov-dot prov-dot-muted"></span>' +
            '<span class="prov-text">Not hosted by Apple</span></div>' : '') +
        '</div>' +
      '</div>' +

      '<div class="modal-section"><h4>Install</h4><div class="code-inline"><pre><code>coreai-catalog install ' + m.id + '</code></pre></div></div>';

    $('modal-overlay').style.display = 'flex';
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
      $('task-list').innerHTML = '<div class="empty-state">Failed to load.</div>';
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

  // ── Device segmented buttons ──
  function initDeviceSegs() {
    document.querySelectorAll('.seg').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var f = btn.dataset.filter;
        toggleDevice(f, !deviceFilters[f]);
        applyFilters();
      });
    });
  }

  // ── Copy buttons (generic) ──
  function initCopyButtons() {
    document.querySelectorAll('.btn-copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var targetId = btn.dataset.copyTarget;
        var text = '';
        if (targetId) {
          var el = $(targetId);
          text = el ? (el.querySelector('code') ? el.querySelector('code').textContent : el.textContent) : '';
        } else {
          var parent = btn.closest('.mcp-client');
          if (parent) {
            var code = parent.querySelector('code');
            text = code ? code.textContent : '';
          }
        }
        text = text.trim();

        function flash() {
          var orig = btn.textContent;
          btn.textContent = 'Copied';
          btn.classList.add('copied');
          setTimeout(function () { btn.textContent = orig; btn.classList.remove('copied'); }, 1500);
        }

        if (navigator.clipboard) {
          navigator.clipboard.writeText(text).then(flash, flash);
        } else {
          var ta = document.createElement('textarea');
          ta.value = text; document.body.appendChild(ta); ta.select();
          try { document.execCommand('copy'); } catch (e) {}
          document.body.removeChild(ta); flash();
        }
      });
    });
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initTabs();
    initDeviceSegs();
    loadData();

    $('search-box').addEventListener('input', function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(applyFilters, 150);
    });
    ['filter-capability', 'filter-license', 'filter-source', 'sort-by'].forEach(function (id) {
      $(id).addEventListener('change', applyFilters);
    });

    $('reset-filters').addEventListener('click', function () {
      $('search-box').value = '';
      $('filter-capability').value = '';
      $('filter-license').value = '';
      $('filter-source').value = '';
      $('sort-by').value = 'score';
      ['iphone', 'ipad', 'mac'].forEach(function (d) { toggleDevice(d, true); });
      applyFilters();
    });

    $('modal-overlay').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeModal();
    });

    initCopyButtons();
  });
})();
