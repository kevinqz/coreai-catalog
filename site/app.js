/**
 * Core AI Catalog — Explorer v2
 * Apple-grade UX: debounced search, staggered animations, theme toggle,
 * capability color coding, keyboard navigation, detail modal.
 * Pure vanilla JS — no build step, no dependencies.
 */
(function () {
  'use strict';

  // ── Config ──
  const DATA_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/search-index.json';
  const TASKS_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/tasks/index.json';

  // ── State ──
  let MODELS = [];
  let FILTERED = [];
  let CAPABILITIES = new Set();
  let searchTimer = null;

  // ── Helpers ──
  const $ = (id) => document.getElementById(id);

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
    const s = String(p).toUpperCase();
    const m = s.match(/([\d.]+)\s*(B|M|K)?/);
    if (!m) return 9999;
    let val = parseFloat(m[1]);
    const mult = { B: 1000, M: 1, K: 0.001 }[m[2]] || 1000;
    return val * mult;
  }

  function devIcons(devs) {
    let s = '';
    if (devs.includes('iphone')) s += '📱';
    if (devs.includes('ipad')) s += '📐';
    if (devs.includes('mac')) s += '💻';
    return s || '❓';
  }

  function sourceIcon(sg) {
    return { official: '🍎', zoo: '🐼', external: '🔗' }[sg] || '';
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function capChipClass(cap) {
    return 'chip chip-cap-' + (cap || '').replace(/_/g, '-');
  }

  // ── Data loading ──
  async function loadData() {
    try {
      const resp = await fetch(DATA_URL);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      MODELS = data.models || [];

      // Collect capabilities
      CAPABILITIES = new Set();
      MODELS.forEach((m) => (m.capabilities || []).forEach((c) => CAPABILITIES.add(c)));

      // Populate capability dropdown
      const sel = $('filter-capability');
      Array.from(CAPABILITIES)
        .sort()
        .forEach((cap) => {
          const opt = document.createElement('option');
          opt.value = cap;
          opt.textContent = cap.replace(/-/g, ' ');
          sel.appendChild(opt);
        });

      // Update search placeholder
      $('search-box').placeholder = `Search ${MODELS.length} models…`;

      applyFilters();
    } catch (err) {
      $('model-grid').innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>Failed to load catalog data.<br><small>${err.message}</small></p></div>`;
      $('result-count').textContent = 'Error';
    }
  }

  // ── Filtering ──
  function applyFilters() {
    const search = $('search-box').value.toLowerCase().trim();
    const cap = $('filter-capability').value;
    const showIphone = $('filter-iphone').checked;
    const showIpad = $('filter-ipad').checked;
    const showMac = $('filter-mac').checked;
    const license = $('filter-license').value;
    const source = $('filter-source').value;
    const sortBy = $('sort-by').value;

    FILTERED = MODELS.filter((m) => {
      // Search
      if (search) {
        const hay = (
          m.name + ' ' + m.id + ' ' + (m.capabilities || []).join(' ') + ' ' + (m.family || '')
        ).toLowerCase();
        if (!hay.includes(search)) return false;
      }
      // Capability
      if (cap && !(m.capabilities || []).includes(cap)) return false;
      // Device — model must support at least one selected device
      const devs = m.devices || [];
      if (showIphone || showIpad || showMac) {
        let match = false;
        if (showIphone && devs.includes('iphone')) match = true;
        if (showIpad && devs.includes('ipad')) match = true;
        if (showMac && devs.includes('mac')) match = true;
        if (!match) return false;
      }
      // License
      if (license && m.commercial_use !== license) return false;
      // Source
      if (source && m.source_group !== source) return false;
      return true;
    });

    // Sort
    if (sortBy === 'name') {
      FILTERED.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === 'params') {
      FILTERED.sort((a, b) => paramSortValue(a.parameters) - paramSortValue(b.parameters));
    } else {
      FILTERED.sort((a, b) => b.readiness_score - a.readiness_score);
    }

    renderGrid();
  }

  // ── Render ──
  function renderGrid() {
    const grid = $('model-grid');
    $('result-count').textContent = `${FILTERED.length} of ${MODELS.length} models`;

    if (FILTERED.length === 0) {
      grid.innerHTML =
        '<div class="empty-state"><div class="empty-state-icon">🔍</div><p>No models match your filters.<br><small>Try adjusting capability, device, or license filters.</small></p></div>';
      return;
    }

    grid.innerHTML = FILTERED.map((m, i) => {
      const score = m.readiness_score;
      const caps = (m.capabilities || [])
        .slice(0, 4)
        .map((c) => `<span class="${capChipClass(c)}">${c.replace(/-/g, ' ')}</span>`)
        .join('');
      const licClass = m.commercial_use === 'likely' ? 'lic-ok' : 'lic-warn';
      const licIcon = m.commercial_use === 'likely' ? '✅' : '⚠️';
      const benchIcon = m.benchmarks && m.benchmarks.length > 0 ? `<span class="card-bench">📊 ${m.benchmarks.length}</span>` : '';
      const delay = Math.min(i * 15, 200);

      return `
        <div class="model-card" data-id="${m.id}" style="animation-delay:${delay}ms">
          <div class="card-top">
            <span class="card-name">${escapeHtml(m.name)}</span>
            <span class="card-score ${scoreClass(score)}">${score} ${gradeLetter(score)}</span>
          </div>
          <div class="card-caps">${caps}</div>
          <div class="card-bottom">
            <div class="card-meta-left">
              <span class="card-devices" title="Device support">${devIcons(m.devices || [])}</span>
              <span class="card-source">${sourceIcon(m.source_group)} ${m.source_group || ''}</span>
            </div>
            <div class="card-meta-left">
              ${benchIcon}
              <span class="card-license ${licClass}">${licIcon} ${m.license || '?'}</span>
            </div>
          </div>
        </div>`;
    }).join('');

    // Click → modal
    grid.querySelectorAll('.model-card').forEach((card) => {
      card.addEventListener('click', () => showModelDetail(card.dataset.id));
    });
  }

  // ── Modal ──
  function showModelDetail(id) {
    const m = MODELS.find((x) => x.id === id);
    if (!m) return;

    const score = m.readiness_score;
    const art = m.artifact || {};
    const hfUrl = art.huggingface_url || '';
    const hfRepo = art.huggingface_repo || '';
    const devList = (m.devices || []).map((d) => `<span class="chip">${d}</span>`).join('');
    const capsList = (m.capabilities || []).map((c) => `<span class="${capChipClass(c)}">${c}</span>`).join('');
    const benchRows = (m.benchmarks || [])
      .map(
        (b) =>
          `<tr><td>${b.metric || ''}</td><td><strong>${b.value}</strong> ${b.unit || ''}</td><td>${b.device || ''}</td><td>${b.compute_unit || ''}</td></tr>`
      )
      .join('');

    $('modal-content').innerHTML = `
      <button class="modal-close" onclick="document.getElementById('modal-overlay').style.display='none'" aria-label="Close">&times;</button>
      <h2>${escapeHtml(m.name)}</h2>
      <p class="modal-id">${m.id} · ${sourceIcon(m.source_group)} ${m.source_group || ''}</p>

      <div class="modal-score-row">
        <span class="card-score ${scoreClass(score)}" style="font-size:0.85rem;padding:0.2rem 0.7rem">${score} ${gradeLetter(score)}</span>
        <span class="modal-score-desc">Readiness score · ${m.maturity || 'unknown'} maturity</span>
      </div>

      ${capsList ? `<div class="modal-section"><h4>Capabilities</h4><div class="card-caps">${capsList}</div></div>` : ''}
      ${devList ? `<div class="modal-section"><h4>Devices</h4><div class="card-caps">${devList}</div></div>` : ''}

      <table class="modal-table">
        <tr><td>Parameters</td><td>${m.parameters || 'not published'}</td></tr>
        <tr><td>Precision</td><td>${m.precision || 'unknown'}</td></tr>
        <tr><td>Quantization</td><td>${m.quantization || 'unknown'}</td></tr>
        <tr><td>License</td><td>${m.license || '?'} ${m.commercial_use === 'likely' ? '✅' : '⚠️'}</td></tr>
        <tr><td>Runtime</td><td>${m.runtime || 'unknown'}</td></tr>
        <tr><td>Runner</td><td>${m.runner || 'unknown'}</td></tr>
      </table>

      ${benchRows ? `<div class="modal-section"><h4>Benchmarks</h4><table class="modal-table"><tr><td>Metric</td><td>Value</td><td>Device</td><td>Compute</td></tr>${benchRows}</table></div>` : ''}

      ${m.notes ? `<div class="modal-section"><h4>Notes</h4><p style="font-size:0.86rem;color:var(--text-secondary)">${escapeHtml(m.notes)}</p></div>` : ''}

      ${hfUrl ? `<div class="modal-section"><h4>Artifact</h4><p><a href="${hfUrl}" target="_blank" rel="noopener">${hfRepo || hfUrl}</a></p></div>` : ''}

      <div class="modal-section">
        <h4>Install</h4>
        <pre><code>coreai-catalog install ${m.id}</code></pre>
      </div>`;

    $('modal-overlay').style.display = 'flex';
  }

  // ── Tasks tab ──
  async function loadTasks() {
    try {
      const resp = await fetch(TASKS_URL);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      const byCap = {};
      data.tasks.forEach((t) => {
        t.capabilities.forEach((c) => {
          if (!byCap[c]) byCap[c] = [];
          byCap[c].push(t);
        });
      });

      $('task-list').innerHTML = Object.keys(byCap)
        .sort()
        .map(
          (cap) => {
            const synonyms = byCap[cap].map((t) => t.task).sort();
            return `
            <div class="task-section">
              <h3>${cap.replace(/-/g, ' ')} <span class="task-count">${synonyms.length}</span></h3>
              <div class="task-synonyms">${synonyms.map((s) => `<span class="chip">${s}</span>`).join('')}</div>
            </div>`;
          }
        )
        .join('');
    } catch (err) {
      $('task-list').innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>Failed to load tasks.<br><small>${err.message}</small></p></div>`;
    }
  }

  // ── Tabs ──
  function initTabs() {
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));
        tab.classList.add('active');
        $(tab.dataset.tab).classList.add('active');
        if (tab.dataset.tab === 'tasks' && !$('task-list').innerHTML) loadTasks();
      });
    });
  }

  // ── Theme toggle ──
  function initTheme() {
    const toggle = $('theme-toggle');
    const updateIcon = () => {
      const t = document.documentElement.getAttribute('data-theme');
      toggle.textContent = t === 'light' ? '☀️' : '🌙';
    };
    updateIcon();
    toggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('coreai-theme', next);
      updateIcon();
    });
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    loadData();

    // Debounced filter listeners
    $('search-box').addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(applyFilters, 180);
    });

    ['filter-capability', 'filter-license', 'filter-source', 'sort-by'].forEach((id) => {
      $(id).addEventListener('change', applyFilters);
    });
    ['filter-iphone', 'filter-ipad', 'filter-mac'].forEach((id) => {
      $(id).addEventListener('change', applyFilters);
    });

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

    // Modal: close on overlay click + ESC
    $('modal-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') $('modal-overlay').style.display = 'none';
    });
  });
})();
