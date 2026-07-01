/**
 * Core AI Catalog — static site explorer.
 * Loads dist/search-index.json and renders filterable model grid.
 * Pure vanilla JS — no build step, no framework, no dependencies.
 */
(function() {
  'use strict';

  const DATA_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/search-index.json';
  const TASKS_URL = 'https://raw.githubusercontent.com/kevinqz/coreai-catalog/main/dist/tasks/index.json';
  const HF_BASE = 'https://huggingface.co/';

  let MODELS = [];
  let FILTERED = [];
  let CAPABILITIES = new Set();

  // ── Helpers ──
  function scoreClass(score) {
    if (score >= 85) return 'score-a';
    if (score >= 70) return 'score-b';
    if (score >= 55) return 'score-c';
    if (score >= 40) return 'score-d';
    return 'score-f';
  }

  function gradeLetter(score) {
    if (score >= 85) return 'A';
    if (score >= 70) return 'B';
    if (score >= 55) return 'C';
    if (score >= 40) return 'D';
    return 'F';
  }

  function paramSortValue(p) {
    if (!p || p === 'unknown' || p === 'not_published') return 9999;
    const s = String(p).toUpperCase();
    const m = s.match(/([\d.]+)\s*(B|M|K)?/);
    if (!m) return 9999;
    let val = parseFloat(m[1]);
    const mult = { 'B': 1000, 'M': 1, 'K': 0.001 }[m[2]] || 1000;
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
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // ── Loading ──
  async function loadData() {
    try {
      const resp = await fetch(DATA_URL);
      const data = await resp.json();
      MODELS = data.models || [];

      // Collect capabilities
      CAPABILITIES = new Set();
      MODELS.forEach(m => (m.capabilities || []).forEach(c => CAPABILITIES.add(c)));

      // Populate capability filter
      const sel = document.getElementById('filter-capability');
      Array.from(CAPABILITIES).sort().forEach(cap => {
        const opt = document.createElement('option');
        opt.value = cap;
        opt.textContent = cap.replace(/-/g, ' ');
        sel.appendChild(opt);
      });

      // Update badge
      const badge = document.getElementById('model-count-badge');
      badge.src = `https://img.shields.io/badge/models-${MODELS.length}-blue`;
      badge.alt = `${MODELS.length} models`;

      renderGrid();
    } catch (err) {
      document.getElementById('model-grid').innerHTML =
        `<p style="color:var(--red);grid-column:1/-1;">Failed to load catalog data: ${err.message}</p>`;
    }
  }

  // ── Filtering ──
  function applyFilters() {
    const search = document.getElementById('search-box').value.toLowerCase().trim();
    const cap = document.getElementById('filter-capability').value;
    const showIphone = document.getElementById('filter-iphone').checked;
    const showIpad = document.getElementById('filter-ipad').checked;
    const showMac = document.getElementById('filter-mac').checked;
    const license = document.getElementById('filter-license').value;
    const source = document.getElementById('filter-source').value;
    const sortBy = document.getElementById('sort-by').value;

    FILTERED = MODELS.filter(m => {
      // Search
      if (search) {
        const hay = (m.name + ' ' + m.id + ' ' + (m.capabilities || []).join(' ') + ' ' + (m.family || '')).toLowerCase();
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
    const grid = document.getElementById('model-grid');
    const count = document.getElementById('result-count');
    count.textContent = `${FILTERED.length} of ${MODELS.length} models`;

    if (FILTERED.length === 0) {
      grid.innerHTML = '<p style="color:var(--text-dim);grid-column:1/-1;">No models match your filters.</p>';
      return;
    }

    grid.innerHTML = FILTERED.map(m => {
      const score = m.readiness_score;
      const sc = scoreClass(score);
      const gl = gradeLetter(score);
      const caps = (m.capabilities || []).slice(0, 4).map(c =>
        `<span class="chip">${c.replace(/-/g, ' ')}</span>`
      ).join('');
      const licClass = m.commercial_use === 'likely' ? 'lic-ok' : 'lic-warn';
      const licIcon = m.commercial_use === 'likely' ? '✅' : '⚠️';
      const benchIcon = m.benchmarks && m.benchmarks.length > 0 ? '📊' : '';

      return `
        <div class="model-card" data-id="${m.id}">
          <div class="card-header">
            <h3>${escapeHtml(m.name)}</h3>
            <span class="score-badge ${sc}">${score} (${gl})</span>
          </div>
          <div class="card-meta">${caps}</div>
          <div class="card-devices">${devIcons(m.devices || [])} ${sourceIcon(m.source_group)} ${m.source_group || ''} ${benchIcon}</div>
          <div class="card-license ${licClass}">${licIcon} ${m.license || '?'}</div>
        </div>
      `;
    }).join('');

    // Click handlers
    grid.querySelectorAll('.model-card').forEach(card => {
      card.addEventListener('click', () => showModelDetail(card.dataset.id));
    });
  }

  // ── Model Detail Modal ──
  function showModelDetail(id) {
    const m = MODELS.find(x => x.id === id);
    if (!m) return;

    const score = m.readiness_score;
    const art = m.artifact || {};
    const hfUrl = art.huggingface_url || '';
    const hfRepo = art.huggingface_repo || '';
    const devList = (m.devices || []).map(d =>
      `<span class="chip">${d}</span>`
    ).join('');
    const benchRows = (m.benchmarks || []).map(b =>
      `<tr><td>${b.metric || ''}</td><td>${b.value} ${b.unit || ''}</td><td>${b.device || ''}</td><td>${b.compute_unit || ''}</td></tr>`
    ).join('');

    const modal = document.getElementById('modal-content');
    modal.innerHTML = `
      <span class="modal-close" onclick="document.getElementById('modal-overlay').style.display='none'">&times;</span>
      <h2>${escapeHtml(m.name)}</h2>
      <p style="color:var(--text-dim);font-size:0.9rem;">${m.id} · ${m.source_group || ''} ${sourceIcon(m.source_group)}</p>

      <div style="margin:0.75rem 0;">
        <span class="score-badge ${scoreClass(score)}">${score} (${gradeLetter(score)})</span>
        <span style="margin-left:0.5rem;color:var(--text-dim);">Readiness score</span>
      </div>

      <div class="modal-section">
        <h4>Capabilities</h4>
        <div class="card-meta">${(m.capabilities || []).map(c => `<span class="chip">${c}</span>`).join('')}</div>
      </div>

      <div class="modal-section">
        <h4>Devices</h4>
        <div class="card-meta">${devList}</div>
      </div>

      <table class="modal-table">
        <tr><td>Parameters</td><td>${m.parameters || 'not published'}</td></tr>
        <tr><td>Precision</td><td>${m.precision || 'unknown'}</td></tr>
        <tr><td>Quantization</td><td>${m.quantization || 'unknown'}</td></tr>
        <tr><td>License</td><td>${m.license || '?'} ${m.commercial_use === 'likely' ? '✅' : '⚠️'}</td></tr>
        <tr><td>Runtime</td><td>${m.runtime || 'unknown'}</td></tr>
        <tr><td>Runner</td><td>${m.runner || 'unknown'}</td></tr>
      </table>

      ${benchRows ? `
      <div class="modal-section">
        <h4>Benchmarks</h4>
        <table class="modal-table">
          <tr><td>Metric</td><td>Value</td><td>Device</td><td>Unit</td></tr>
          ${benchRows}
        </table>
      </div>` : ''}

      ${m.notes ? `<div class="modal-section"><h4>Notes</h4><p style="font-size:0.9rem;">${escapeHtml(m.notes)}</p></div>` : ''}

      ${hfUrl ? `
      <div class="modal-section">
        <h4>Artifact</h4>
        <p><a href="${hfUrl}" target="_blank">${hfRepo || hfUrl}</a></p>
      </div>` : ''}

      <div class="modal-section">
        <h4>Install</h4>
        <pre><code>coreai-catalog install ${m.id}</code></pre>
      </div>
    `;

    document.getElementById('modal-overlay').style.display = 'flex';
  }

  // ── Tasks Tab ──
  async function loadTasks() {
    try {
      const resp = await fetch(TASKS_URL);
      const data = await resp.json();
      const list = document.getElementById('task-list');

      // Group by capability
      const byCap = {};
      data.tasks.forEach(t => {
        t.capabilities.forEach(c => {
          if (!byCap[c]) byCap[c] = [];
          byCap[c].push(t);
        });
      });

      list.innerHTML = Object.keys(byCap).sort().map(cap => {
        const tasks = byCap[cap];
        const synonyms = tasks.map(t => t.task).sort();
        return `
          <div class="task-capability">
            <h3>${cap.replace(/-/g, ' ')} <span class="task-model-count">${synonyms.length} task keywords</span></h3>
            <p>${synonyms.map(s => `<span class="chip">${s}</span>`).join(' ')}</p>
          </div>
        `;
      }).join('');
    } catch (err) {
      document.getElementById('task-list').innerHTML = `<p>Failed to load tasks: ${err.message}</p>`;
    }
  }

  // ── Tabs ──
  function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        const target = tab.dataset.tab;
        document.getElementById(target).classList.add('active');
        if (target === 'tasks' && !document.getElementById('task-list').innerHTML) {
          loadTasks();
        }
      });
    });
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', () => {
    loadData();
    initTabs();

    // Filter event listeners
    ['search-box', 'filter-capability', 'filter-license', 'filter-source', 'sort-by'].forEach(id => {
      const el = document.getElementById(id);
      el.addEventListener('input', applyFilters);
      el.addEventListener('change', applyFilters);
    });
    ['filter-iphone', 'filter-ipad', 'filter-mac'].forEach(id => {
      document.getElementById(id).addEventListener('change', applyFilters);
    });
    document.getElementById('reset-filters').addEventListener('click', () => {
      document.getElementById('search-box').value = '';
      document.getElementById('filter-capability').value = '';
      document.getElementById('filter-license').value = '';
      document.getElementById('filter-source').value = '';
      document.getElementById('filter-iphone').checked = true;
      document.getElementById('filter-ipad').checked = true;
      document.getElementById('filter-mac').checked = true;
      document.getElementById('sort-by').value = 'score';
      applyFilters();
    });

    // Close modal on overlay click
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) {
        e.currentTarget.style.display = 'none';
      }
    });
    // ESC to close modal
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.getElementById('modal-overlay').style.display = 'none';
      }
    });
  });
})();
