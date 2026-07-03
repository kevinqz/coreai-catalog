/**
 * Core AI Catalog — Explorer v5
 * Tighter, cleaner, faster.
 */
(function () {
  'use strict';

  var DATA_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/search-index.json';
  var TASKS_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/tasks/index.json';
  var LEADERBOARD_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/leaderboard.json';
  var FETCH_TIMEOUT_MS = 8000;

  var MODELS = [];
  var FILTERED = [];
  var CAPABILITIES = {};
  var INPUT_MODALITIES = [];
  var OUTPUT_MODALITIES = [];
  var CAPABILITY_OPTIONS = [];
  var INPUT_OPTIONS = [];
  var OUTPUT_OPTIONS = [];
  var LICENSE_OPTIONS = [
    { value: 'likely', label: 'Commercial: likely' },
    { value: 'check_license', label: 'Check license' }
  ];
  var SOURCE_OPTIONS = [
    { value: 'official', label: 'Apple recipe' },
    { value: 'zoo', label: 'Community' }
  ];
  var searchTimer = null;
  var deviceFilters = { iphone: true, ipad: true, mac: true };
  var lastFocusedEl = null;

  // Leaderboard state
  var LB_DATA = [];
  var LB_SORT = { col: 'score', dir: 'desc' };

  function $(id) { return document.getElementById(id); }

  // ── Resilient fetch: timeout + 1 retry ──
  async function fetchJSON(url) {
    var lastErr;
    for (var attempt = 0; attempt < 2; attempt++) {
      var controller = new AbortController();
      var timer = setTimeout(function () { controller.abort(); }, FETCH_TIMEOUT_MS);
      try {
        var resp = await fetch(url, { signal: controller.signal });
        clearTimeout(timer);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return await resp.json();
      } catch (err) {
        clearTimeout(timer);
        lastErr = err;
      }
    }
    throw lastErr;
  }

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

  var CARD_IO_ARROW_SVG = '<span class="card-io-arrow"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></span>';

  // Card In → Out formatter — a divided IN | OUT rectangle, every modality spelled out, nothing abbreviated.
  function cardIoHTML(inputArr, outputArr) {
    inputArr = inputArr || []; outputArr = outputArr || [];
    var inp = inputArr.length ? inputArr.map(function (v) { return v.replace(/-/g, ' '); }).join(', ') : '—';
    var out = outputArr.length ? outputArr.map(function (v) { return v.replace(/-/g, ' '); }).join(', ') : '—';
    return '<span class="card-io-label">In</span> <span class="card-io-value">' + escapeHtml(inp) + '</span>' +
      CARD_IO_ARROW_SVG +
      '<span class="card-io-label">Out</span> <span class="card-io-value">' + escapeHtml(out) + '</span>';
  }
  var DEVICE_LABELS = { iphone: 'iPhone', ipad: 'iPad', mac: 'Mac' };
  function deviceLabel(d) { return DEVICE_LABELS[d] || d; }
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

  // ── Score factor computation (matches catalog.py readiness_score) ──
  function gradeDescription(s) {
    if (s >= 85) return 'Production-ready';
    if (s >= 70) return 'Good, minor gaps';
    if (s >= 55) return 'Usable, verify caveats';
    if (s >= 40) return 'Experimental';
    return 'Early / unverified';
  }
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
      var data = await fetchJSON(DATA_URL);
      MODELS = data.models || [];

      CAPABILITIES = {};
      var inputSet = {}, outputSet = {};
      MODELS.forEach(function (m) {
        (m.capabilities || []).forEach(function (c) { CAPABILITIES[c] = true; });
        (m.input_modalities || []).forEach(function (i) { inputSet[i] = true; });
        (m.output_modalities || []).forEach(function (o) { outputSet[o] = true; });
      });
      INPUT_MODALITIES = Object.keys(inputSet).sort();
      OUTPUT_MODALITIES = Object.keys(outputSet).sort();
      CAPABILITY_OPTIONS = Object.keys(CAPABILITIES).sort().map(function (c) { return { value: c, label: c.replace(/-/g, ' ') }; });
      INPUT_OPTIONS = INPUT_MODALITIES.map(function (v) { return { value: v, label: v.replace(/-/g, ' ') }; });
      OUTPUT_OPTIONS = OUTPUT_MODALITIES.map(function (v) { return { value: v, label: v.replace(/-/g, ' ') }; });

      $('search-box').placeholder = 'Search ' + MODELS.length + ' models\u2026';

      // Data freshness (most recent last_verified across models)
      var freshest = MODELS.reduce(function (max, m) {
        return (m.last_verified && m.last_verified > max) ? m.last_verified : max;
      }, '');
      var freshBadge = $('freshness-badge');
      if (freshBadge && freshest) freshBadge.textContent = 'Data verified ' + freshest;

      // Populate dynamic About stats
      var statModels = $('stat-models');
      if (statModels) statModels.textContent = MODELS.length;
      var totalBench = MODELS.reduce(function (s, m) { return s + ((m.benchmarks && m.benchmarks.length) || 0); }, 0);
      var statBench = $('stat-benchmarks');
      if (statBench) statBench.textContent = totalBench;

      refreshAll();
    } catch (err) {
      $('model-grid').innerHTML = '<div class="empty-state"><p>Failed to load data.</p><button type="button" class="btn-retry" id="retry-load-data">Try again</button></div>';
      $('result-count').textContent = 'Error';
      var retryBtn = $('retry-load-data');
      if (retryBtn) retryBtn.addEventListener('click', loadData);
    }
  }

  // Rebuild any facet <select>'s options with counts relative to ALL the
  // OTHER currently active filters (not just its IO sibling) — always listing
  // every known value (never hiding one) and disabling only the ones with
  // zero matches. Native <select> disabled options are skipped by keyboard
  // nav and screen readers for free.
  function rebuildFacetSelect(selId, options, matchTest, passesOtherFilters, anyLabel) {
    var sel = $(selId);
    if (!sel) return;
    var counts = {};
    MODELS.forEach(function (m) {
      if (!passesOtherFilters(m)) return;
      matchTest(m).forEach(function (v) { if (v) counts[v] = (counts[v] || 0) + 1; });
    });
    var current = sel.value;
    sel.innerHTML = '';
    var optAny = document.createElement('option');
    optAny.value = '';
    optAny.textContent = anyLabel;
    sel.appendChild(optAny);
    var currentStillValid = false;
    options.forEach(function (o) {
      var n = counts[o.value] || 0;
      var opt = document.createElement('option');
      opt.value = o.value;
      opt.textContent = o.label + ' · ' + n;
      if (!n && o.value !== current) opt.disabled = true;
      if (o.value === current) currentStillValid = true;
      sel.appendChild(opt);
    });
    sel.value = currentStillValid ? current : '';
    updateIoRowState(selId);
  }

  function updateIoRowState(selId) {
    var sel = $(selId);
    if (!sel) return;
    var row = sel.closest('.io-row');
    var has = !!sel.value;
    if (row) row.classList.toggle('has-value', has);
    sel.classList.toggle('has-value', has);
  }

  // ── One filter state shared by Explore and Scores — switching tabs never loses your filters ──
  var FILTER_STATE = { search: '', cap: '', inp: '', out: '', lic: '', src: '' };
  var MIRROR_FIELDS = {
    search: ['search-box', 'lb-search'],
    cap: ['filter-capability', 'lb-filter-capability'],
    inp: ['filter-input', 'lb-filter-input'],
    out: ['filter-output', 'lb-filter-output'],
    lic: ['filter-license', 'lb-filter-license'],
    src: ['filter-source', 'lb-filter-source']
  };

  function matchesFilters(m, exclude) {
    var f = FILTER_STATE;
    if (exclude !== 'search' && f.search) {
      var hay = (m.name + ' ' + m.id + ' ' + (m.capabilities || []).join(' ') + ' ' + (m.family || '')).toLowerCase();
      if (hay.indexOf(f.search) < 0) return false;
    }
    if (exclude !== 'cap' && f.cap && (m.capabilities || []).indexOf(f.cap) < 0) return false;
    if (exclude !== 'inp' && f.inp && (m.input_modalities || []).indexOf(f.inp) < 0) return false;
    if (exclude !== 'out' && f.out && (m.output_modalities || []).indexOf(f.out) < 0) return false;
    if (exclude !== 'device') {
      var devs = m.devices || [];
      var anyDevice = deviceFilters.iphone || deviceFilters.ipad || deviceFilters.mac;
      if (anyDevice) {
        var ok = (deviceFilters.iphone && devs.indexOf('iphone') >= 0) ||
          (deviceFilters.ipad && devs.indexOf('ipad') >= 0) ||
          (deviceFilters.mac && devs.indexOf('mac') >= 0);
        if (!ok) return false;
      }
    }
    if (exclude !== 'lic' && f.lic && m.commercial_use !== f.lic) return false;
    if (exclude !== 'src' && f.src && m.source_group !== f.src) return false;
    return true;
  }

  // Rebuilds the same facet in every tab that shows it (e.g. filter-capability AND lb-filter-capability).
  function rebuildMirroredFacet(ids, options, matchTest, exclude, anyLabel) {
    ids.forEach(function (id) {
      rebuildFacetSelect(id, options, matchTest, function (m) { return matchesFilters(m, exclude); }, anyLabel);
    });
  }

  function refreshAllFacets() {
    rebuildMirroredFacet(MIRROR_FIELDS.cap, CAPABILITY_OPTIONS, function (m) { return m.capabilities || []; }, 'cap', 'All');
    rebuildMirroredFacet(MIRROR_FIELDS.inp, INPUT_OPTIONS, function (m) { return m.input_modalities || []; }, 'inp', 'Any input');
    rebuildMirroredFacet(MIRROR_FIELDS.out, OUTPUT_OPTIONS, function (m) { return m.output_modalities || []; }, 'out', 'Any output');
    rebuildMirroredFacet(MIRROR_FIELDS.lic, LICENSE_OPTIONS, function (m) { return [m.commercial_use]; }, 'lic', 'All');
    rebuildMirroredFacet(MIRROR_FIELDS.src, SOURCE_OPTIONS, function (m) { return [m.source_group]; }, 'src', 'All');
    updateDeviceCounts();
  }

  function updateDeviceCounts() {
    ['iphone', 'ipad', 'mac'].forEach(function (d) {
      var n = MODELS.filter(function (m) {
        if (!matchesFilters(m, 'device')) return false;
        return (m.devices || []).indexOf(d) >= 0;
      }).length;
      document.querySelectorAll('.seg[data-filter="' + d + '"]').forEach(function (btn) {
        var countEl = btn.querySelector('.seg-count');
        if (!countEl) {
          countEl = document.createElement('span');
          countEl.className = 'seg-count';
          btn.appendChild(countEl);
        }
        countEl.textContent = n;
        btn.classList.toggle('seg-empty', n === 0);
      });
    });
  }

  // Every control that changes a shared filter: update state, mirror the twin control in the other tab, re-render everything.
  function syncAllControls() {
    Object.keys(MIRROR_FIELDS).forEach(function (key) {
      MIRROR_FIELDS[key].forEach(function (id) {
        var el = $(id);
        if (el && el.value !== FILTER_STATE[key]) el.value = FILTER_STATE[key];
      });
    });
  }

  function bindMirroredControl(key, debounce) {
    MIRROR_FIELDS[key].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener(debounce ? 'input' : 'change', function () {
        var raw = el.value;
        FILTER_STATE[key] = debounce ? raw.toLowerCase().trim() : raw;
        MIRROR_FIELDS[key].forEach(function (otherId) {
          if (otherId === id) return;
          var other = $(otherId);
          if (other && other.value !== raw) other.value = raw;
        });
        if (debounce) {
          clearTimeout(searchTimer);
          searchTimer = setTimeout(refreshAll, 150);
        } else {
          refreshAll();
        }
      });
    });
  }

  function clearField(key) {
    FILTER_STATE[key] = '';
  }

  function resetAllFilters() {
    Object.keys(FILTER_STATE).forEach(function (key) { FILTER_STATE[key] = ''; });
    ['iphone', 'ipad', 'mac'].forEach(function (d) { toggleDevice(d, true); });
    var sortBy = $('sort-by');
    if (sortBy) sortBy.value = 'score';
    syncAllControls();
    refreshAll();
  }

  function refreshAll() {
    applyFilters();
    renderLeaderboard();
    refreshAllFacets();
  }

  function initIoClearButtons() {
    document.querySelectorAll('.io-x').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sel = $(btn.dataset.ioClear);
        if (!sel) return;
        sel.value = '';
        sel.dispatchEvent(new Event('change'));
        sel.focus();
      });
    });
  }

  // ── Filter ──
  function applyFilters() {
    var sort = $('sort-by').value;

    FILTERED = MODELS.filter(function (m) { return matchesFilters(m, null); });

    if (sort === 'name') FILTERED.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (sort === 'params') FILTERED.sort(function (a, b) { return paramSortValue(a.parameters) - paramSortValue(b.parameters); });
    else FILTERED.sort(function (a, b) { return b.readiness_score - a.readiness_score; });

    renderPills();
    renderGrid();
  }

  // ── Filter pills ──
  function renderPills() {
    var search = FILTER_STATE.search, cap = FILTER_STATE.cap, inpFilter = FILTER_STATE.inp,
      outFilter = FILTER_STATE.out, lic = FILTER_STATE.lic, src = FILTER_STATE.src;
    var pills = [];
    if (search) pills.push({ label: '"' + search + '"', clear: function () { clearField('search'); } });
    if (cap) pills.push({ label: cap.replace(/-/g, ' '), chipClass: 'chip-cap-' + cap.replace(/_/g, '-'), clear: function () { clearField('cap'); } });
    if (inpFilter) pills.push({ label: 'in: ' + inpFilter.replace(/-/g, ' '), clear: function () { clearField('inp'); } });
    if (outFilter) pills.push({ label: 'out: ' + outFilter.replace(/-/g, ' '), clear: function () { clearField('out'); } });
    if (!deviceFilters.iphone) pills.push({ label: 'no iPhone', clear: function () { toggleDevice('iphone', true); } });
    if (!deviceFilters.ipad) pills.push({ label: 'no iPad', clear: function () { toggleDevice('ipad', true); } });
    if (!deviceFilters.mac) pills.push({ label: 'no Mac', clear: function () { toggleDevice('mac', true); } });
    if (lic) pills.push({ label: lic === 'likely' ? 'Commercial: likely' : 'Check license', clear: function () { clearField('lic'); } });
    if (src) pills.push({ label: sourceLabel(src), clear: function () { clearField('src'); } });

    var c = $('active-filters');
    if (!pills.length) { c.innerHTML = ''; return; }
    c.innerHTML = pills.map(function (p, i) {
      return '<button type="button" class="filter-pill' + (p.chipClass ? ' ' + p.chipClass : '') + '" data-idx="' + i + '" aria-label="Remove filter: ' + escapeHtml(p.label) + '">' + escapeHtml(p.label) + '</button>';
    }).join('');
    c.querySelectorAll('.filter-pill').forEach(function (el, i) {
      el.addEventListener('click', function () { pills[i].clear(); syncAllControls(); refreshAll(); });
    });
  }

  function toggleDevice(d, val) {
    deviceFilters[d] = val;
    document.querySelectorAll('.seg[data-filter="' + d + '"]').forEach(function (btn) {
      val ? btn.classList.add('active') : btn.classList.remove('active');
      btn.setAttribute('aria-pressed', val ? 'true' : 'false');
    });
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

      return '<div class="model-card" data-id="' + m.id + '" tabindex="0" role="button" aria-label="View details for ' + escapeHtml(m.name) + '" style="animation-delay:' + delay + 'ms">' +
        '<div class="card-top">' +
          '<span class="card-name">' + escapeHtml(m.name) + '</span>' +
          '<button type="button" class="card-score ' + scoreClass(s) + '" title="Click to see score breakdown" aria-label="Score ' + s + ', ' + gradeLetter(s) + '. Click to see breakdown.">' + s + ' ' + gradeLetter(s) + '</button>' +
        '</div>' +
        '<div class="card-caps">' + caps + '</div>' +
        '<div class="card-io">' + cardIoHTML(m.input_modalities, m.output_modalities) + '</div>' +
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
      card.addEventListener('click', function () { showDetail(card.dataset.id, card); });
      card.addEventListener('keydown', function (e) {
        if (e.target !== card) return; // let the score button handle its own keys
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showDetail(card.dataset.id, card); }
      });
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

    return '<div class="sb-factors">' + rows + '</div>';
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
  function closeModal() {
    $('modal-overlay').style.display = 'none';
    document.removeEventListener('keydown', trapModalFocus, true);
    if (lastFocusedEl && lastFocusedEl.focus) lastFocusedEl.focus();
    lastFocusedEl = null;
  }

  function trapModalFocus(e) {
    if (e.key !== 'Tab') return;
    var content = $('modal-content');
    var focusable = content.querySelectorAll('button, [href], input, select, [tabindex]:not([tabindex="-1"])');
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function showDetail(id, triggerEl) {
    var m = MODELS.find(function (x) { return x.id === id; });
    if (!m) return;
    lastFocusedEl = triggerEl || document.activeElement;
    var s = m.readiness_score;
    var art = m.artifact || {};
    var hfUrl = art.huggingface_url || '';
    var hfRepo = art.huggingface_repo || '';
    var devList = (m.devices || []).map(function (d) {
      return '<span class="chip">' + deviceLabel(d) + '</span>';
    }).join('');
    var capsList = (m.capabilities || []).map(function (c) {
      return '<span class="' + capChip(c) + '">' + c + '</span>';
    }).join('');
    var benchRows = (m.benchmarks || []).map(function (b) {
      return '<tr><td>' + (b.metric || '') + '</td><td><strong>' + b.value + '</strong> ' + (b.unit || '') + '</td><td>' + (b.device || '') + '</td><td>' + (b.compute_unit || '') + '</td></tr>';
    }).join('');

    $('modal-content').innerHTML =
      '<button class="modal-close" id="modal-close-btn" aria-label="Close">&times;</button>' +
      '<h2 id="modal-title">' + escapeHtml(m.name) + '</h2>' +
      '<p class="modal-id">' + m.id + ' &middot; ' + escapeHtml(sourceLabel(m.source_group)) + '</p>' +
      '<div class="modal-score-row">' +
        '<button type="button" class="card-score ' + scoreClass(s) + '" id="modal-score-btn" title="Click to see score breakdown">' + s + ' ' + gradeLetter(s) + '</button>' +
        '<span class="modal-score-desc">' + escapeHtml(gradeDescription(s)) + ' &middot; click to expand</span>' +
      '</div>' +
      '<div class="score-breakdown modal-score-details" style="display:none;">' +
        scoreBreakdownHTML(m) +
      '</div>' +
      (capsList ? '<div class="modal-section"><h4>Capabilities</h4><div class="card-caps">' + capsList + '</div></div>' : '') +
      '<div class="modal-section"><h4>Input &rarr; Output</h4><div class="card-io">' + cardIoHTML(m.input_modalities, m.output_modalities) + '</div></div>' +
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

      '<div class="modal-section"><h4>Install</h4><div class="code-block">' +
        '<div class="code-header"><span>bash</span><button class="btn-copy" data-copy-target="modal-install-code">Copy</button></div>' +
        '<pre><code id="modal-install-code">coreai-catalog install ' + m.id + '</code></pre>' +
      '</div></div>';

    $('modal-overlay').style.display = 'flex';
    document.addEventListener('keydown', trapModalFocus, true);
    $('modal-close-btn').focus();
    $('modal-close-btn').addEventListener('click', closeModal);
    $('modal-score-btn').addEventListener('click', function () {
      var details = document.querySelector('.modal-score-details');
      if (details.style.display === 'none') { details.style.display = 'block'; this.classList.add('active'); }
      else { details.style.display = 'none'; this.classList.remove('active'); }
    });
  }

  // ── Tasks ──
  async function loadTasks() {
    try {
      var data = await fetchJSON(TASKS_URL);
      var byCap = {};
      data.tasks.forEach(function (t) { t.capabilities.forEach(function (c) { (byCap[c] = byCap[c] || []).push(t); }); });
      $('task-list').innerHTML = Object.keys(byCap).sort().map(function (cap) {
        var syns = byCap[cap].map(function (t) { return t.task; }).sort();
        var modelCount = MODELS.filter(function (m) { return (m.capabilities || []).indexOf(cap) >= 0; }).length;
        return '<button type="button" class="task-section" data-cap="' + escapeHtml(cap) + '" aria-label="Show ' + modelCount + ' models with ' + escapeHtml(cap.replace(/-/g, ' ')) + ' in Explore">' +
          '<div class="task-section-head">' +
            '<span class="' + capChip(cap) + ' task-cap-chip">' + cap.replace(/-/g, ' ') + '</span>' +
            '<span class="task-count">' + modelCount + ' model' + (modelCount === 1 ? '' : 's') + '</span>' +
          '</div>' +
          '<div class="task-synonyms">' + syns.map(function (s) { return '<span class="chip">' + escapeHtml(s) + '</span>'; }).join('') + '</div>' +
        '</button>';
      }).join('');
      $('task-list').querySelectorAll('.task-section').forEach(function (btn) {
        btn.addEventListener('click', function () {
          FILTER_STATE.cap = btn.dataset.cap;
          syncAllControls();
          refreshAll();
          document.querySelector('[data-tab="explore"]').click();
        });
      });
    } catch (err) {
      $('task-list').innerHTML = '<div class="empty-state">Failed to load.<br><button type="button" class="btn-retry" id="retry-load-tasks">Try again</button></div>';
      var retryBtn = $('retry-load-tasks');
      if (retryBtn) retryBtn.addEventListener('click', loadTasks);
    }
  }

  // ── Leaderboard ──
  async function loadLeaderboard() {
    try {
      var data = await fetchJSON(LEADERBOARD_URL);
      LB_DATA = data.leaderboard || [];
      // Also load search-index for modality data (leaderboard doesn't have it)
      if (!MODELS.length) {
        try {
          var data2 = await fetchJSON(DATA_URL);
          MODELS = data2.models || [];
        } catch (e) {}
      }
      renderLeaderboard();
    } catch (err) {
      $('lb-body').innerHTML = '<tr><td colspan="4" class="lb-empty">Failed to load leaderboard.<br><button type="button" class="btn-retry" id="retry-load-lb">Try again</button></td></tr>';
      $('lb-count').textContent = 'Error';
      var retryBtn = $('retry-load-lb');
      if (retryBtn) retryBtn.addEventListener('click', loadLeaderboard);
    }
  }

  function renderLeaderboard() {
    var rows = LB_DATA.filter(function (m) {
      var full = MODELS.find(function (x) { return x.id === m.id; }) || m;
      return matchesFilters(full, null);
    });

    // Sort
    if (LB_SORT.col === 'name') {
      rows.sort(function (a, b) {
        var cmp = a.name.localeCompare(b.name);
        return LB_SORT.dir === 'asc' ? cmp : -cmp;
      });
    } else {
      rows.sort(function (a, b) {
        var cmp = b.readiness_score - a.readiness_score;
        if (cmp === 0) cmp = a.name.localeCompare(b.name);
        return LB_SORT.dir === 'asc' ? -cmp : cmp;
      });
    }

    $('lb-count').textContent = rows.length + ' of ' + LB_DATA.length + ' models';

    // Update sort indicators
    document.querySelectorAll('.lb-table th.sortable').forEach(function (th) {
      th.classList.remove('sort-asc', 'sort-desc');
      if (th.dataset.sort === LB_SORT.col) {
        th.classList.add(LB_SORT.dir === 'asc' ? 'sort-asc' : 'sort-desc');
        th.setAttribute('aria-sort', LB_SORT.dir === 'asc' ? 'ascending' : 'descending');
      } else {
        th.removeAttribute('aria-sort');
      }
    });

    if (!rows.length) {
      $('lb-body').innerHTML = '<tr><td colspan="4" class="lb-empty">No models match your filters.</td></tr>';
      return;
    }

    $('lb-body').innerHTML = rows.map(function (m, i) {
      var s = m.readiness_score;
      var caps = (m.capabilities || []).map(function (c) {
        return '<span class="' + capChip(c) + '">' + c.replace(/-/g, ' ') + '</span>';
      }).join('');

      return '<tr data-id="' + m.id + '" tabindex="0" role="button" aria-label="View details for ' + escapeHtml(m.name) + '">' +
        '<td class="lb-rank">' + (i + 1) + '</td>' +
        '<td class="lb-model">' + escapeHtml(m.name) + '</td>' +
        '<td class="lb-cap">' + caps + '</td>' +
        '<td class="lb-score"><span class="card-score ' + scoreClass(s) + '">' + s + ' ' + gradeLetter(s) + '</span></td>' +
      '</tr>';
    }).join('');

    // Row click / keyboard -> open detail modal
    $('lb-body').querySelectorAll('tr[data-id]').forEach(function (tr) {
      tr.addEventListener('click', function () { showDetail(tr.dataset.id, tr); });
      tr.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showDetail(tr.dataset.id, tr); }
      });
    });
  }

  function initLeaderboard() {
    // Sort header clicks (+ keyboard, since <th> isn't natively operable)
    document.querySelectorAll('.lb-table th.sortable').forEach(function (th) {
      function doSort() {
        var col = th.dataset.sort;
        if (LB_SORT.col === col) {
          LB_SORT.dir = LB_SORT.dir === 'asc' ? 'desc' : 'asc';
        } else {
          LB_SORT.col = col;
          LB_SORT.dir = col === 'params' ? 'asc' : 'desc';
        }
        renderLeaderboard();
      }
      th.addEventListener('click', doSort);
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); doSort(); }
      });
    });

    // Search/Capability/Input/Output/License/Source/Device are shared with Explore —
    // bound once for both tabs via bindMirroredControl() and toggleDevice(), see init below.

    // Reset button
    $('lb-reset').addEventListener('click', resetAllFilters);
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
        if (tab.dataset.tab === 'scores' && !LB_DATA.length) loadLeaderboard();
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
        refreshAll();
      });
    });
  }

  // ── Skill → tab jump links (Skills tab → specific Contribute card) ──
  function initSkillJumps() {
    document.querySelectorAll('.skill-jump').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tabBtn = document.querySelector('.tab[data-tab="' + btn.dataset.jumpTab + '"]');
        if (tabBtn) tabBtn.click();
        var target = $(btn.dataset.jumpTarget);
        if (!target) return;
        requestAnimationFrame(function () {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          target.classList.add('jump-highlight');
          setTimeout(function () { target.classList.remove('jump-highlight'); }, 1600);
        });
      });
    });
  }

  // ── Copy buttons (generic) ──
  // Delegated on document (not per-element) so buttons rendered later —
  // e.g. the model modal's Install card — work without a re-init call.
  function initCopyButtons() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.btn-copy');
      if (!btn) return;
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

      var orig = btn.textContent;
      function flash() {
        btn.textContent = 'Copied';
        btn.classList.remove('failed');
        btn.classList.add('copied');
        setTimeout(function () { btn.textContent = orig; btn.classList.remove('copied'); }, 1500);
      }
      function flashFail() {
        btn.textContent = 'Copy failed — select manually';
        btn.classList.remove('copied');
        btn.classList.add('failed');
        setTimeout(function () { btn.textContent = orig; btn.classList.remove('failed'); }, 2200);
      }

      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(flash, flashFail);
      } else {
        var ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
        document.body.removeChild(ta);
        ok ? flash() : flashFail();
      }
    });
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initTabs();
    initDeviceSegs();
    initLeaderboard();
    initIoClearButtons();
    loadData();

    // Search/Capability/Input/Output/License/Source are shared between Explore and
    // Scores — one control changing updates the other tab's twin and both renders.
    bindMirroredControl('search', true);
    bindMirroredControl('cap', false);
    bindMirroredControl('inp', false);
    bindMirroredControl('out', false);
    bindMirroredControl('lic', false);
    bindMirroredControl('src', false);

    $('sort-by').addEventListener('change', applyFilters);
    $('reset-filters').addEventListener('click', resetAllFilters);

    $('modal-overlay').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeModal();
    });

    initCopyButtons();
    initSkillJumps();
  });
})();
