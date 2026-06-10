// AegisGate Demo Dashboard — Data Renderer
// =====================================
//
// Fetches 5 seed JSON files (threats, MCP tools, EU AI Act scan,
// dashboard metrics, playground prompts) from /seed-data/ and
// renders them into the page. No frameworks — vanilla JS.
//
// Resilience: if any single fetch fails, the section shows a
// graceful error message but the rest of the page still works.

(function () {
  'use strict';

  // ============================================
  // Helpers
  // ============================================
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  async function fetchJSON(url) {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);
    return await res.json();
  }

  function esc(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatNumber(n) {
    if (typeof n !== 'number') return '—';
    return n.toLocaleString('en-US');
  }

  function showError(container, message) {
    container.innerHTML = `<div class="stat-skeleton" style="color:#f85149;">${esc(message)}</div>`;
  }

  // ============================================
  // 1. STATS GRID
  // ============================================
  async function renderStats() {
    const container = $('#stats-grid');
    try {
      const [threats, tools, scan, metrics] = await Promise.all([
        fetchJSON('/seed-data/threats.json'),
        fetchJSON('/seed-data/mcp-tools.json'),
        fetchJSON('/seed-data/compliance-eu-ai-act.json'),
        fetchJSON('/seed-data/dashboard-metrics.json'),
      ]);

      const stats = [
        {
          value: scan.scan_metadata?.total_controls ?? '82',
          label: 'EU AI Act controls',
          accent: 'gold',
        },
        {
          value: formatNumber(scan.scan_metadata?.passing ?? 0),
          label: 'controls passing',
          accent: 'accent',
        },
        {
          value: formatNumber(metrics.summary?.total_requests ?? 0),
          label: 'requests (24h)',
        },
        {
          value: formatNumber(metrics.summary?.total_threats_detected ?? 0),
          label: 'threats detected',
          accent: 'gold',
        },
        {
          value: formatNumber(metrics.summary?.total_threats_blocked ?? 0),
          label: 'threats blocked',
          accent: 'accent',
        },
        {
          value: threats.length,
          label: 'pre-loaded threats',
        },
        {
          value: tools.length,
          label: 'sample MCP tools',
        },
        {
          value: (metrics.summary?.uptime_percentage ?? 0).toFixed(2) + '%',
          label: 'uptime (24h)',
        },
      ];

      container.innerHTML = stats.map((s) => `
        <div class="stat-card">
          <div class="stat-value ${s.accent === 'accent' ? 'stat-value-accent' : s.accent === 'gold' ? 'stat-value-gold' : ''}">${esc(s.value)}</div>
          <div class="stat-label">${esc(s.label)}</div>
        </div>
      `).join('');
    } catch (e) {
      showError(container, 'Could not load stats: ' + e.message);
    }
  }

  // ============================================
  // 2. EU AI ACT COMPLIANCE SCAN
  // ============================================
  async function renderCompliance() {
    const container = $('#compliance-overview');
    const controlsList = $('#controls-list');
    try {
      const scan = await fetchJSON('/seed-data/compliance-eu-ai-act.json');
      const meta = scan.scan_metadata || {};
      const categories = scan.categories || {};
      const controls = scan.controls || [];

      // 2a. Overview (score card + category grid)
      const scorePct = Math.round((meta.overall_compliance_score ?? 0) * 100);
      const catList = Object.entries(categories);

      container.innerHTML = `
        <div class="compliance-score-card">
          <div class="compliance-score-value">${scorePct}%</div>
          <div class="compliance-score-label">overall compliance</div>
          <div class="compliance-score-bar">
            <div class="compliance-score-fill" style="width: ${scorePct}%;"></div>
          </div>
          <div style="margin-top:16px; font-size:12px; color:#8b949e;">
            ${formatNumber(meta.passing ?? 0)} pass · ${formatNumber(meta.warnings ?? 0)} warn · ${formatNumber(meta.failing ?? 0)} fail
          </div>
          <div style="margin-top:8px; font-size:11px; color:#6e7681; text-transform:uppercase; letter-spacing:0.5px;">
            ${esc(meta.framework || 'eu-ai-act')} · scanned ${esc((meta.scan_timestamp || '').slice(0, 10))}
          </div>
        </div>
        <div class="compliance-categories">
          ${catList.map(([key, cat]) => {
            const cls = (cat.status || '').replace(/_/g, '-');
            const name = key.replace(/_/g, ' ');
            return `
              <div class="category-card">
                <div class="category-name">${esc(name)}</div>
                <div class="category-counts">
                  <span class="category-count-pass">${cat.passing || 0} pass</span>
                  ${(cat.warnings || 0) > 0 ? `<span class="category-count-warn">${cat.warnings} warn</span>` : ''}
                  ${(cat.failing || 0) > 0 ? `<span class="category-count-fail">${cat.failing} fail</span>` : ''}
                </div>
                <div class="category-status category-status-${cls}">${esc(cat.status || 'unknown')}</div>
              </div>
            `;
          }).join('')}
        </div>
      `;

      // 2b. All controls list
      controlsList.innerHTML = controls.map((c) => {
        const status = c.status || 'unknown';
        const cls = status === 'pass' ? 'badge-pass' : status === 'warning' ? 'badge-warn' : 'badge-fail';
        return `
          <div class="control-row">
            <span class="control-id">${esc(c.id)}</span>
            <span class="control-name">
              ${esc(c.name)}
              ${c.note ? `<br><span style="color:#6e7681; font-size:11px;">${esc(c.note)}</span>` : ''}
            </span>
            <span class="control-status-badge ${cls}">${esc(status)}</span>
          </div>
        `;
      }).join('');
    } catch (e) {
      showError(container, 'Could not load compliance scan: ' + e.message);
    }
  }

  // ============================================
  // 3. THREATS GRID
  // ============================================
  async function renderThreats() {
    const container = $('#threats-grid');
    try {
      const threats = await fetchJSON('/seed-data/threats.json');
      container.innerHTML = threats.map((t) => {
        const sev = (t.severity || 'medium').toLowerCase();
        const outcome = t.actual_detection || 'detected';
        const outcomeClass = 'outcome-' + outcome;
        return `
          <div class="threat-card">
            <div class="threat-header">
              <div class="threat-name">${esc(t.name)}</div>
              <span class="threat-severity severity-${sev}">${esc(sev)}</span>
            </div>
            <div class="threat-meta">
              ${t.technique_id ? `<span class="threat-meta-item">${esc(t.technique_id)}</span>` : ''}
              ${t.detection_layer ? `<span class="threat-meta-item">${esc(t.detection_layer)}</span>` : ''}
              ${t.category ? `<span class="threat-meta-item">${esc(t.category)}</span>` : ''}
            </div>
            <div class="threat-description">${esc(t.description || '')}</div>
            <div class="threat-outcome ${outcomeClass}">
              <strong>→ ${esc(outcome.replace(/_/g, ' '))}:</strong>
              ${esc(t.blocked_reason || 'Action taken.')}
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      showError(container, 'Could not load threats: ' + e.message);
    }
  }

  // ============================================
  // 4. MCP TOOLS GRID
  // ============================================
  async function renderTools() {
    const container = $('#tools-grid');
    try {
      const tools = await fetchJSON('/seed-data/mcp-tools.json');
      container.innerHTML = tools.map((t) => {
        const risk = (t.risk_level || 'low').toLowerCase();
        const usage = t.usage_last_24h || {};
        const usageTotal = Object.values(usage).reduce((a, b) => a + b, 0);
        const initial = (t.name || '?').charAt(0).toUpperCase();
        return `
          <div class="tool-card">
            <div class="tool-header">
              <div class="tool-icon">${esc(initial)}</div>
              <div style="flex:1;">
                <div class="tool-name">${esc(t.name)}</div>
                <div class="tool-version">v${esc(t.version || '0.0.0')}</div>
              </div>
            </div>
            <div class="tool-description">${esc(t.description || '')}</div>
            ${(t.capabilities || []).length > 0 ? `
              <div class="tool-capabilities">
                <h4>Capabilities</h4>
                ${t.capabilities.map((c) => `<div class="tool-cap">${esc(c.name)} — ${esc(c.description || '')}</div>`).join('')}
              </div>
            ` : ''}
            <div class="tool-footer">
              <span>${formatNumber(usageTotal)} calls (24h)</span>
              <span class="tool-risk risk-${risk}">${esc(risk)} risk</span>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      showError(container, 'Could not load MCP tools: ' + e.message);
    }
  }

  // ============================================
  // 5. METRICS / BAR CHART
  // ============================================
  async function renderMetrics() {
    const summary = $('#metrics-summary');
    const chart = $('#bar-chart');
    const topTech = $('#top-techniques');
    const topCats = $('#threat-categories');
    try {
      const metrics = await fetchJSON('/seed-data/dashboard-metrics.json');
      const s = metrics.summary || {};
      const hourly = metrics.hourly_requests || [];
      const topTechs = metrics.top_threat_techniques || [];
      const cats = metrics.threat_categories || {};

      // 5a. Summary tiles
      const tiles = [
        { value: formatNumber(s.total_requests), label: 'requests' },
        { value: formatNumber(s.total_threats_detected), label: 'threats' },
        { value: formatNumber(s.total_users_active), label: 'users' },
        { value: formatNumber(s.total_mcp_tool_calls), label: 'tool calls' },
        { value: s.p50_latency_ms + 'ms', label: 'p50 latency' },
        { value: s.p95_latency_ms + 'ms', label: 'p95 latency' },
      ];
      summary.innerHTML = tiles.map((t) => `
        <div class="metric-tile">
          <div class="metric-tile-value">${esc(t.value)}</div>
          <div class="metric-tile-label">${esc(t.label)}</div>
        </div>
      `).join('');

      // 5b. Bar chart
      const maxReq = Math.max(...hourly.map((h) => h.requests || 0), 1);
      chart.innerHTML = hourly.map((h) => {
        const pct = ((h.requests || 0) / maxReq) * 100;
        const hasThreats = (h.threats || 0) > 0;
        return `
          <div class="bar-col">
            <div class="bar ${hasThreats ? 'has-threats' : ''}" style="height: ${Math.max(pct, 2)}%;">
              <div class="bar-tooltip">
                ${esc(h.hour)} UTC · ${h.requests} req · ${h.threats} threats
              </div>
            </div>
            <div class="bar-label">${esc(h.hour)}</div>
          </div>
        `;
      }).join('');

      // 5c. Top threat techniques
      topTech.innerHTML = topTechs.slice(0, 10).map((t) => {
        const blocked = t.blocked || 0;
        const warned = t.warned || 0;
        return `
          <li>
            ${esc(t.technique)}
            <span class="tech-count">${formatNumber(t.count)} <span style="color:#3fb950;">(${formatNumber(blocked)} blocked${warned ? `, ${formatNumber(warned)} warned` : ''})</span></span>
          </li>
        `;
      }).join('');

      // 5d. Threat categories
      const catEntries = Object.entries(cats).sort((a, b) => b[1] - a[1]);
      const maxCat = Math.max(...catEntries.map(([_, v]) => v), 1);
      topCats.innerHTML = catEntries.map(([k, v]) => {
        const pct = (v / maxCat) * 100;
        return `
          <li>
            <span class="cat-name">${esc(k.replace(/_/g, ' '))}</span>
            <div class="cat-bar-wrapper"><div class="cat-bar" style="width: ${pct}%;"></div></div>
            <span class="cat-count">${formatNumber(v)}</span>
          </li>
        `;
      }).join('');
    } catch (e) {
      showError(summary, 'Could not load metrics: ' + e.message);
      showError(chart, '');
    }
  }

  // ============================================
  // 6. PLAYGROUND (delegate to playground.js)
  // ============================================
  // playground.js handles its own init. dashboard.js just
  // makes sure the playground section's data is loaded
  // so the examples can be rendered.

  async function loadPlaygroundData() {
    try {
      const data = await fetchJSON('/seed-data/playground-prompts.json');
      window.__PLAYGROUND_PROMPTS__ = data.playground_prompts || [];
    } catch (e) {
      window.__PLAYGROUND_PROMPTS__ = [];
      console.error('Could not load playground prompts:', e);
    }
  }

  // ============================================
  // 7. INTERACTIVE UI WIRE-UP
  // ============================================
  function wireUI() {
    // Banner info toggle
    const bannerToggle = $('#demo-banner-toggle');
    const info = $('#demo-info');
    if (bannerToggle && info) {
      bannerToggle.addEventListener('click', () => {
        const isHidden = info.hasAttribute('hidden');
        if (isHidden) {
          info.removeAttribute('hidden');
          bannerToggle.textContent = 'Hide';
        } else {
          info.setAttribute('hidden', '');
          bannerToggle.textContent = "What's this?";
        }
      });
      // Close when clicking outside
      document.addEventListener('click', (e) => {
        if (info.hasAttribute('hidden')) return;
        if (info.contains(e.target) || bannerToggle.contains(e.target)) return;
        info.setAttribute('hidden', '');
        bannerToggle.textContent = "What's this?";
      });
    }

    // Controls list toggle
    const controlsToggle = $('#controls-toggle');
    const controlsList = $('#controls-list');
    if (controlsToggle && controlsList) {
      controlsToggle.addEventListener('click', () => {
        const expanded = controlsToggle.getAttribute('aria-expanded') === 'true';
        if (expanded) {
          controlsToggle.setAttribute('aria-expanded', 'false');
          controlsList.setAttribute('hidden', '');
          controlsToggle.querySelector('span:last-child').textContent = 'Show all 82 controls';
        } else {
          controlsToggle.setAttribute('aria-expanded', 'true');
          controlsList.removeAttribute('hidden');
          controlsToggle.querySelector('span:last-child').textContent = 'Hide controls list';
        }
      });
    }
  }

  // ============================================
  // INIT
  // ============================================
  async function init() {
    wireUI();
    // Render sections in parallel (each is independent)
    await Promise.all([
      renderStats(),
      renderCompliance(),
      renderThreats(),
      renderTools(),
      renderMetrics(),
      loadPlaygroundData(),
    ]);
    // Fire a custom event so playground.js can boot now
    document.dispatchEvent(new CustomEvent('dashboard:ready'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
