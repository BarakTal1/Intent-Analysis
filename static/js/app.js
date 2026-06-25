const API = '';
let activeProjectId = null;
let resultsSortBy = null, resultsSortDir = 'asc';
let explorerSortBy = null, explorerSortDir = 'asc';

function humanize(s) {
  if (!s) return s;
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function emptyState(icon, title, subtitle, ctaText, ctaPage) {
  return `<div class="flex flex-col items-center justify-center py-16 text-center">
    <span class="material-symbols-outlined text-[48px] text-on-surface-variant/40 mb-4">${icon}</span>
    <h3 class="text-[16px] font-semibold text-on-surface mb-1">${title}</h3>
    <p class="text-[13px] text-on-surface-variant mb-4 max-w-sm">${subtitle}</p>
    ${ctaText && ctaPage ? `<button class="bg-primary-container text-white px-5 py-2 rounded text-[13px] font-semibold hover:opacity-90 transition" onclick="navigate('${ctaPage}')">${ctaText}</button>` : ''}
  </div>`;
}

// ============ Projects ============
async function loadProjects() {
  const resp = await fetch(API + '/api/projects');
  const data = await resp.json();
  activeProjectId = data.active_project_id;

  const sel = document.getElementById('project-selector');
  sel.innerHTML = data.projects.length === 0
    ? '<option value="" disabled selected>No projects</option>'
    : data.projects.map(p =>
        `<option value="${p.id}" ${p.id === activeProjectId ? 'selected' : ''}>${p.name}</option>`
      ).join('');

  const grid = document.getElementById('projects-grid');
  if (grid) {
    grid.innerHTML = data.projects.map(p => `
      <div class="bg-card border ${p.id === activeProjectId ? 'border-primary' : 'border-card-border'} rounded-lg p-5 hover:border-interactive-border transition-colors relative group">
        ${p.id === activeProjectId ? '<span class="absolute top-3 right-3 text-[11px] bg-primary/20 text-primary px-2 py-0.5 rounded font-semibold">ACTIVE</span>' : ''}
        <div class="flex items-center gap-2 mb-3">
          <span class="material-symbols-outlined text-primary text-[24px]">folder</span>
          <h3 class="text-[16px] font-semibold truncate">${p.name}</h3>
        </div>
        <div class="grid grid-cols-2 gap-3 mb-4">
          <div class="bg-surface-container-high rounded p-2">
            <div class="text-[11px] text-on-surface-variant">Traces</div>
            <div class="text-[18px] font-semibold">${p.trace_count}</div>
          </div>
          <div class="bg-surface-container-high rounded p-2">
            <div class="text-[11px] text-on-surface-variant">Results</div>
            <div class="text-[18px] font-semibold">${p.result_count}</div>
          </div>
        </div>
        <div class="flex gap-2">
          ${p.id !== activeProjectId ? `<button class="flex-1 bg-primary-container text-white px-3 py-1.5 rounded text-[13px] font-semibold hover:opacity-90 transition" onclick="switchProject('${p.id}')">Activate</button>` : '<button class="flex-1 bg-primary/10 text-primary px-3 py-1.5 rounded text-[13px] font-semibold cursor-default">Active</button>'}
          <button class="px-3 py-1.5 border border-card-border rounded text-[13px] hover:bg-card-hover transition text-on-surface-variant" onclick="renameProject('${p.id}', '${p.name.replace(/'/g, "\\'")}')">Rename</button>
          <button class="px-3 py-1.5 border border-red-900/40 rounded text-[13px] hover:bg-red-900/20 transition text-error" onclick="deleteProject('${p.id}', '${p.name.replace(/'/g, "\\'")}')">
            <span class="material-symbols-outlined text-[16px]">delete</span>
          </button>
        </div>
      </div>
    `).join('') || '<div class="col-span-3 text-center py-12 text-on-surface-variant"><span class="material-symbols-outlined text-[48px] mb-2 block">folder_off</span>No projects yet. Create one to get started.</div>';
  }
}

function showCreateProject() {
  document.getElementById('create-project-modal').style.display = '';
  const input = document.getElementById('new-project-name');
  input.value = '';
  setTimeout(() => input.focus(), 100);
}

async function createProject() {
  const name = document.getElementById('new-project-name').value.trim();
  if (!name) return;
  await fetch(API + '/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  document.getElementById('create-project-modal').style.display = 'none';
  await loadProjects();
  navigate('upload');
}

async function switchProject(projectId) {
  await fetch(API + `/api/projects/${projectId}/activate`, { method: 'POST' });
  await loadProjects();
  const currentPage = document.querySelector('.page.active')?.id?.replace('page-', '') || 'upload';
  navigate(currentPage);
}

async function renameProject(projectId, currentName) {
  const newName = prompt('Rename project:', currentName);
  if (!newName || newName.trim() === currentName) return;
  await fetch(API + `/api/projects/${projectId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newName.trim() }),
  });
  await loadProjects();
}

async function deleteProject(projectId, name) {
  if (!confirm(`Delete project "${name}"? All traces and results in this project will be lost.`)) return;
  await fetch(API + `/api/projects/${projectId}`, { method: 'DELETE' });
  await loadProjects();
}

// ============ Navigation ============
function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  const pageEl = document.getElementById('page-' + page);
  if (pageEl) pageEl.classList.add('active');
  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');
  closeSidebarOnNavigate();

  const loaders = {
    dashboard: loadDashboard,
    projects: loadProjects,
    results: () => { loadResults(1); loadSummary(); },
    intents: loadIntents,
    satisfaction: loadSatisfaction,
    skills: loadSkills,
    'skills-gap': loadSkillsGap,
    explorer: () => loadExplorer(1),
    settings: loadSettings,
  };
  if (loaders[page]) loaders[page]();
}

// ============ Sidebar Toggle ============
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const isOpen = !sidebar.classList.contains('-translate-x-full');
  sidebar.classList.toggle('-translate-x-full', isOpen);
  overlay.classList.toggle('hidden', isOpen);
}

function closeSidebarOnNavigate() {
  if (window.innerWidth < 1024) {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
  }
}

// ============ Theme Toggle ============
function toggleTheme() {
  const isLight = document.documentElement.classList.toggle('light');
  document.documentElement.classList.toggle('dark', !isLight);
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
  document.getElementById('theme-icon').textContent = isLight ? 'dark_mode' : 'light_mode';
  Charts.updateTheme(isLight ? 'intentLight' : 'intentDark');
}

(function initTheme() {
  const saved = localStorage.getItem('theme');
  if (saved === 'light') {
    document.documentElement.classList.add('light');
    document.documentElement.classList.remove('dark');
    const icon = document.getElementById('theme-icon');
    if (icon) icon.textContent = 'dark_mode';
    Charts.updateTheme('intentLight');
  }
})();

// ============ Global Search ============
function navigateToSearch(query) {
  if (!query.trim()) return;
  navigate('explorer');
  const searchParam = encodeURIComponent(query.trim());
  loadExplorer(1, searchParam);
}

// ============ Upload Tabs ============
function switchUploadTab(tab) {
  document.querySelectorAll('.upload-tab').forEach(t => {
    t.classList.remove('active', 'border-primary', 'text-primary');
    t.classList.add('border-transparent', 'text-on-surface-variant');
  });
  const active = document.querySelector(`.upload-tab[data-tab="${tab}"]`);
  if (active) {
    active.classList.add('active', 'border-primary', 'text-primary');
    active.classList.remove('border-transparent', 'text-on-surface-variant');
  }
  document.querySelectorAll('.upload-panel').forEach(p => p.classList.add('hidden'));
  const panel = document.querySelector(`.upload-panel[data-panel="${tab}"]`);
  if (panel) panel.classList.remove('hidden');
}

// ============ Upload & Parse ============
async function handleFileUpload(files) {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  const resp = await fetch(API + '/api/upload', { method: 'POST', body: form });
  const data = await resp.json();
  refreshStagedFiles();
}

async function refreshStagedFiles() {
  const resp = await fetch(API + '/api/staged');
  const data = await resp.json();
  const tbody = document.getElementById('staged-table');
  document.getElementById('staged-count').textContent = data.files.length;
  tbody.innerHTML = data.files.map(f => `
    <tr class="border-b border-card-border hover:bg-card-hover transition-colors">
      <td class="px-4 py-2 text-on-surface flex items-center gap-2">
        <span class="material-symbols-outlined text-on-surface-variant text-[16px]">description</span>
        ${f.filename}
      </td>
      <td class="px-4 py-2 text-on-surface-variant">${formatSize(f.size)}</td>
      <td class="px-4 py-2 text-on-surface-variant">${f.rows ?? '--'}</td>
      <td class="px-4 py-2 text-right">
        ${f.status === 'parsed' ? '<span class="material-symbols-outlined text-[#4caf50] text-[18px]">check_circle</span>' :
          f.status === 'error' ? '<span class="material-symbols-outlined text-error text-[18px]">cancel</span>' :
          '<span class="material-symbols-outlined text-on-surface-variant text-[18px]">hourglass_empty</span>'}
      </td>
    </tr>
  `).join('');
}

async function parseAll() {
  const resp = await fetch(API + '/api/parse', { method: 'POST' });
  const data = await resp.json();
  refreshStagedFiles();

  if (data.traces && data.traces.length > 0) {
    document.getElementById('parsed-section').style.display = '';
    document.getElementById('parsed-title').textContent = `Parsed ${data.parsed} traces from ${document.getElementById('staged-count').textContent} files`;
    const cards = document.getElementById('parsed-cards');
    cards.innerHTML = data.traces.slice(0, 6).map(t => `
      <div class="bg-card border border-card-border rounded p-4 hover:border-interactive-border transition-colors">
        <div class="flex justify-between items-start mb-2">
          <span class="font-mono text-[13px] text-primary bg-primary/10 px-2 py-[2px] rounded">${t.trace_id.substring(0, 12)}...</span>
          <span class="text-[13px] text-on-surface-variant flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">chat</span> ${t.num_messages} messages
          </span>
        </div>
        <div class="text-[13px] text-on-surface-variant mb-3 flex items-center gap-1">
          <span class="material-symbols-outlined text-[14px]">build</span> ${t.num_tool_calls} tool calls
        </div>
        <div class="flex flex-wrap gap-1 mb-3">
          ${t.skills_activated.map(s => `<span class="bg-tertiary-container/10 text-tertiary-container font-mono text-[10px] px-2 py-[1px] border border-tertiary-container/20 rounded-full">${humanize(s)}</span>`).join('')}
        </div>
        <p class="text-[12px] text-on-surface-variant line-clamp-2">${t.preview}</p>
      </div>
    `).join('');
  }
}

async function clearAllData() {
  if (!confirm('Clear all traces and extraction results? This cannot be undone.')) return;
  try {
    const resp = await fetch(API + '/api/traces', { method: 'DELETE' });
    const data = await resp.json();
    alert(`Cleared ${data.cleared_traces} traces and ${data.cleared_results} results.`);
    loadResults();
    refreshStagedFiles();
    loadProjects();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ============ Extraction & Results ============
let resultsPage = 1;

async function runExtraction() {
  document.getElementById('kpi-status').textContent = 'Running...';
  try {
    const resp = await fetch(API + '/api/extract', { method: 'POST' });
    const data = await resp.json();
    document.getElementById('kpi-status').textContent = data.status === 'completed' ? 'Done' : data.status;
    loadResults(1);
    loadSummary();
  } catch (e) {
    document.getElementById('kpi-status').textContent = 'Error';
  }
}

async function loadDashboard() {
  const [summaryResp, intentsResp, satResp] = await Promise.all([
    fetch(API + '/api/analytics/summary'),
    fetch(API + '/api/analytics/intents'),
    fetch(API + '/api/analytics/satisfaction'),
  ]);
  const d = await summaryResp.json();
  const intents = await intentsResp.json();
  const sat = await satResp.json();

  document.getElementById('dash-total-traces').textContent = d.total_results || 0;
  document.getElementById('dash-total-traces-ctx').textContent = d.total_traces ? `${d.total_traces} uploaded` : '';

  const satEl = document.getElementById('dash-mean-sat');
  if (d.mean_satisfaction != null) {
    satEl.textContent = d.mean_satisfaction.toFixed(2);
    satEl.className = satEl.className.replace(/text-\[#[^\]]+\]/g, '');
    satEl.classList.add(d.mean_satisfaction >= 0.7 ? 'text-[#4caf50]' : d.mean_satisfaction >= 0.4 ? 'text-tertiary' : 'text-error');
    document.getElementById('dash-mean-sat-ctx').textContent = d.mean_satisfaction >= 0.85 ? 'Above target' : d.mean_satisfaction >= 0.55 ? 'Needs attention' : 'Below average';
  } else {
    satEl.textContent = '--';
  }

  document.getElementById('dash-goal-rate').textContent = d.goal_achievement_rate != null ? d.goal_achievement_rate + '%' : '--';
  document.getElementById('dash-goal-ctx').textContent = d.goal_achievement_rate != null
    ? (d.goal_achievement_rate >= 80 ? 'Strong performance' : d.goal_achievement_rate >= 50 ? 'Room for improvement' : 'Needs attention')
    : '';

  document.getElementById('dash-categories').textContent = d.categories_found ?? '--';
  document.getElementById('dash-categories-ctx').textContent = d.unknown_rate != null ? `${d.unknown_rate}% unknown` : '';

  if (intents.distribution && intents.distribution.length) {
    const top8 = intents.distribution.slice(0, 8);
    Charts.intentDistribution(document.getElementById('dash-intent-chart'), top8);
  }

  if (sat.distribution && sat.distribution.length) {
    Charts.satisfactionHistogram(document.getElementById('dash-sat-chart'), sat.distribution);
  }
}

async function loadSummary() {
  const resp = await fetch(API + '/api/analytics/summary');
  const d = await resp.json();
  document.getElementById('kpi-total').textContent = d.total_results || 0;
  document.getElementById('kpi-total-ctx').textContent = d.total_results ? `across ${d.total_results} traces` : '';
  document.getElementById('kpi-mean-sat').textContent = d.mean_satisfaction != null ? d.mean_satisfaction.toFixed(2) : '--';
  const satCtx = document.getElementById('kpi-mean-sat-ctx');
  if (d.mean_satisfaction != null) {
    satCtx.textContent = d.mean_satisfaction >= 0.85 ? 'Above target' : d.mean_satisfaction >= 0.55 ? 'Needs attention' : 'Below average';
  } else { satCtx.textContent = ''; }
  document.getElementById('kpi-goal').textContent = d.goal_achievement_rate != null ? d.goal_achievement_rate + '%' : '--';
  const goalCtx = document.getElementById('kpi-goal-ctx');
  if (d.goal_achievement_rate != null) {
    goalCtx.textContent = d.goal_achievement_rate >= 80 ? 'Strong performance' : d.goal_achievement_rate >= 50 ? 'Room for improvement' : 'Needs attention';
  } else { goalCtx.textContent = ''; }
}

function sortResults(col) {
  if (resultsSortBy === col) { resultsSortDir = resultsSortDir === 'asc' ? 'desc' : 'asc'; }
  else { resultsSortBy = col; resultsSortDir = 'asc'; }
  updateSortArrows('results-table', resultsSortBy, resultsSortDir);
  loadResults(1);
}

function sortExplorer(col) {
  if (explorerSortBy === col) { explorerSortDir = explorerSortDir === 'asc' ? 'desc' : 'asc'; }
  else { explorerSortBy = col; explorerSortDir = 'asc'; }
  updateSortArrows('explorer-table', explorerSortBy, explorerSortDir);
  loadExplorer(1);
}

function updateSortArrows(tableId, sortBy, sortDir) {
  const table = document.getElementById(tableId)?.closest('table');
  if (!table) return;
  table.querySelectorAll('.sort-arrow').forEach(el => {
    el.textContent = el.dataset.col === sortBy ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';
  });
}

async function loadResults(page) {
  if (page < 1) return;
  resultsPage = page;
  const perPage = parseInt(document.getElementById('results-per-page')?.value || 50);
  let url = API + `/api/results?page=${page}&per_page=${perPage}`;
  if (resultsSortBy) url += `&sort_by=${resultsSortBy}&sort_dir=${resultsSortDir}`;
  const resp = await fetch(url);
  const data = await resp.json();
  const totalPages = Math.ceil(data.total / perPage) || 1;
  if (page > 1 && data.items.length === 0) return;

  const tbody = document.getElementById('results-table');
  if (data.items.length === 0 && page === 1) {
    tbody.innerHTML = `<tr><td colspan="7">${emptyState('analytics', 'No extraction results yet', 'Upload traces and run extraction to see results here.', 'Upload Traces', 'upload')}</td></tr>`;
    document.getElementById('results-showing').textContent = '';
    const pi = document.getElementById('results-page-info'); if (pi) pi.textContent = '';
    return;
  }
  tbody.innerHTML = data.items.map(r => `
    <tr class="border-b border-card-border hover:bg-card-hover transition-colors cursor-pointer" onclick="showResultDetail('${r.trace_id}')">
      <td class="px-4 py-2 text-primary">${r.trace_id.substring(0, 12)}</td>
      <td class="px-4 py-2 text-on-surface max-w-[300px] truncate">${r.intent_summary}</td>
      <td class="px-4 py-2"><span class="bg-primary/10 text-primary px-2 py-[1px] rounded text-[11px]">${humanize(r.primary_intent)}</span></td>
      <td class="px-4 py-2">${satBadge(r.satisfaction_score)}</td>
      <td class="px-4 py-2">${r.goal_achieved ? '<span class="text-[#4caf50]">Yes</span>' : '<span class="text-error">No</span>'}</td>
      <td class="px-4 py-2"><span class="text-[11px] px-2 py-[1px] border border-card-border rounded">${r.complexity}</span></td>
      <td class="px-4 py-2 text-on-surface-variant">${r.skills_used.length}</td>
    </tr>
  `).join('');

  document.getElementById('results-showing').textContent = `Showing ${(page-1)*perPage+1}-${(page-1)*perPage+data.items.length} of ${data.total}`;
  const pi = document.getElementById('results-page-info'); if (pi) pi.textContent = `Page ${page} of ${totalPages}`;
  const prev = document.getElementById('results-prev'); if (prev) prev.disabled = page <= 1;
  const next = document.getElementById('results-next'); if (next) next.disabled = page >= totalPages;
}

async function showResultDetail(traceId) {
  const resp = await fetch(API + `/api/results/${traceId}`);
  const r = await resp.json();
  const el = document.getElementById('result-detail');
  el.style.display = '';

  el.innerHTML = `
    <div class="flex justify-between items-start mb-4">
      <h3 class="text-[16px] font-semibold">Trace: ${r.trace_id}</h3>
      <button onclick="document.getElementById('result-detail').style.display='none'" class="text-on-surface-variant hover:text-on-surface">
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>
    <div class="grid grid-cols-2 gap-6">
      <div>
        <h4 class="text-[14px] font-semibold mb-2">Full Intent Summary</h4>
        <p class="text-[13px] text-on-surface-variant mb-4">${r.intent_summary}</p>
        <h4 class="text-[14px] font-semibold mb-2">LLM Outputs</h4>
        <div class="space-y-1 text-[12px] font-mono">
          ${r.skills_relevance.map(s => `
            <div class="flex items-center gap-2">
              <span class="${s.was_relevant ? 'text-[#4caf50]' : 'text-error'}">&#9679;</span>
              ${humanize(s.skill_name)}
              <span class="text-on-surface-variant">SBERT: ${s.sbert_score != null ? s.sbert_score.toFixed(2) : 'N/A'}</span>
            </div>
          `).join('')}
        </div>
        <h4 class="text-[14px] font-semibold mt-4 mb-2">Satisfaction Signals</h4>
        <ul class="text-[12px] text-on-surface-variant space-y-1">
          ${r.satisfaction_signals.map(s => `<li>&#8226; ${s}</li>`).join('')}
        </ul>
      </div>
      <div>
        <h4 class="text-[14px] font-semibold mb-2">Conversation</h4>
        <div class="space-y-3 max-h-[400px] overflow-y-auto pr-2">
          ${(r.conversation || []).map(m => `
            <div class="${m.role === 'user' ? 'bg-primary/10 border-primary/20' : 'bg-surface-container-high border-card-border'} border rounded p-3">
              <div class="text-[11px] font-semibold uppercase mb-1 ${m.role === 'user' ? 'text-primary' : 'text-on-surface-variant'}">${m.role}</div>
              <div class="text-[13px] whitespace-pre-wrap">${m.content}</div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
  el.scrollIntoView({ behavior: 'smooth' });
}

// ============ Intent Overview ============
async function loadIntents() {
  const resp = await fetch(API + '/api/analytics/intents');
  const d = await resp.json();

  if (!d.distribution || d.distribution.length === 0) {
    document.getElementById('intent-dist-chart').innerHTML = emptyState('radar', 'No intent data available', 'Run extraction on uploaded traces to analyze intents.', 'Upload Traces', 'upload');
    document.getElementById('intent-top8-chart').innerHTML = '';
    document.getElementById('intent-hierarchy').innerHTML = '';
    document.getElementById('intent-sat-density').innerHTML = '';
    return;
  }

  document.getElementById('intent-top').textContent = humanize(d.top_intent) || '--';
  document.getElementById('intent-top-pct').textContent = d.top_intent_pct ? `${d.top_intent_pct}% of total traffic` : '';
  document.getElementById('intent-cats').textContent = d.categories_found || '--';
  document.getElementById('intent-unknown').textContent = d.unknown_rate != null ? d.unknown_rate + '%' : '--';

  // Distribution bars (ECharts)
  const dist = d.distribution || [];
  Charts.intentDistribution(document.getElementById('intent-dist-chart'), dist);

  // Top 8 donut (ECharts)
  const top8 = d.top_8 || [];
  Charts.intentDonut(document.getElementById('intent-top8-chart'), top8);

  // Hierarchy
  const hierarchy = d.hierarchy || {};
  document.getElementById('intent-hierarchy').innerHTML = Object.entries(hierarchy).slice(0, 8).map(([intent, subs]) => `
    <div class="mb-3">
      <div class="flex items-center gap-1 text-[13px] font-semibold">
        <span class="material-symbols-outlined text-[16px] text-on-surface-variant">subdirectory_arrow_right</span>
        ${humanize(intent)}
      </div>
      <div class="ml-6 space-y-1 mt-1">
        ${subs.map(s => `<div class="text-[12px] text-on-surface-variant font-mono flex items-center gap-2">
          <span class="material-symbols-outlined text-[14px]">arrow_right</span> ${humanize(s.sub_intent)} <span class="text-primary">${s.count}</span>
        </div>`).join('')}
      </div>
    </div>
  `).join('');

  // Satisfaction density
  const satDens = d.satisfaction_density || [];
  document.getElementById('intent-sat-density').innerHTML = `
    <table class="w-full text-[12px]">
      <thead><tr class="border-b border-card-border text-on-surface-variant">
        <th class="text-left py-1 px-2">Intent</th>
        <th class="text-right py-1 px-2">Score</th>
        <th class="text-right py-1 px-2">Volume</th>
        <th class="text-right py-1 px-2">Heat</th>
      </tr></thead>
      <tbody class="font-mono">
        ${satDens.map(x => `
          <tr class="border-b border-card-border hover:bg-card-hover">
            <td class="py-1 px-2">${humanize(x.intent)}</td>
            <td class="py-1 px-2 text-right">${x.mean_satisfaction}</td>
            <td class="py-1 px-2 text-right">${x.count}</td>
            <td class="py-1 px-2 text-right">${satBadge(x.mean_satisfaction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ============ Satisfaction ============
async function loadSatisfaction() {
  const resp = await fetch(API + '/api/analytics/satisfaction');
  const d = await resp.json();

  if (!d.distribution || d.distribution.length === 0) {
    document.getElementById('sat-histogram').innerHTML = emptyState('sentiment_satisfied', 'No satisfaction data available', 'Run extraction on uploaded traces to analyze satisfaction.', 'Upload Traces', 'upload');
    document.getElementById('sat-by-intent').innerHTML = '';
    document.getElementById('sat-by-complexity').innerHTML = '';
    document.getElementById('sat-by-expertise').innerHTML = '';
    document.getElementById('sat-signals').innerHTML = '';
    document.getElementById('sat-low-traces').innerHTML = '';
    return;
  }

  document.getElementById('sat-mean').textContent = d.mean_satisfaction?.toFixed(2) ?? '--';
  document.getElementById('sat-full').textContent = d.fully_satisfied_rate != null ? d.fully_satisfied_rate + '%' : '--';
  document.getElementById('sat-low').textContent = d.low_satisfaction_rate != null ? d.low_satisfaction_rate + '%' : '--';
  document.getElementById('sat-clarif').textContent = d.avg_clarifications?.toFixed(1) ?? '--';

  // Histogram (ECharts)
  const hist = d.distribution || [];
  Charts.satisfactionHistogram(document.getElementById('sat-histogram'), hist);

  // By intent (ECharts)
  const byInt = d.by_intent || [];
  Charts.satisfactionByCategory(document.getElementById('sat-by-intent'), byInt, 'primary');

  // By complexity (ECharts)
  const byComp = d.by_complexity || [];
  Charts.satisfactionByCategory(document.getElementById('sat-by-complexity'), byComp, 'tertiary');

  // By expertise (ECharts)
  const byExp = d.by_expertise || [];
  Charts.satisfactionByCategory(document.getElementById('sat-by-expertise'), byExp, 'green');

  // Signals
  const sigs = d.sentiment_signals || {};
  document.getElementById('sat-signals').innerHTML = `
    <div class="mb-3">
      <div class="text-[13px] font-semibold text-[#4caf50] mb-2 flex items-center gap-1">
        <span class="material-symbols-outlined text-[16px]">thumb_up</span> Positive
      </div>
      ${(sigs.positive || []).map(s => `
        <div class="flex items-center gap-2 text-[12px] mb-1 font-mono">
          <span class="text-[#4caf50]">${s.signal}</span>
          <span class="text-on-surface-variant bg-[#4caf50]/10 px-2 rounded">${s.count}</span>
        </div>
      `).join('') || '<div class="text-[12px] text-on-surface-variant">No data</div>'}
    </div>
    <div>
      <div class="text-[13px] font-semibold text-error mb-2 flex items-center gap-1">
        <span class="material-symbols-outlined text-[16px]">thumb_down</span> Negative
      </div>
      ${(sigs.negative || []).map(s => `
        <div class="flex items-center gap-2 text-[12px] mb-1 font-mono">
          <span class="text-error">${s.signal}</span>
          <span class="text-on-surface-variant bg-error/10 px-2 rounded">${s.count}</span>
        </div>
      `).join('') || '<div class="text-[12px] text-on-surface-variant">No data</div>'}
    </div>
  `;

  // Low sat traces
  const lowTraces = d.low_satisfaction_traces || [];
  document.getElementById('sat-low-traces').innerHTML = `
    <table class="w-full text-[12px]">
      <thead><tr class="border-b border-card-border text-on-surface-variant">
        <th class="text-left py-1 px-2">Trace ID</th>
        <th class="text-left py-1 px-2">Intent</th>
        <th class="text-right py-1 px-2">Score</th>
        <th class="text-left py-1 px-2">Primary Signal</th>
      </tr></thead>
      <tbody class="font-mono">
        ${lowTraces.slice(0, 10).map(t => `
          <tr class="border-b border-card-border hover:bg-card-hover cursor-pointer" onclick="navigate('results'); setTimeout(() => showResultDetail('${t.trace_id}'), 300)">
            <td class="py-1 px-2 text-primary">${t.trace_id.substring(0, 12)}</td>
            <td class="py-1 px-2">${humanize(t.intent)}</td>
            <td class="py-1 px-2 text-right">${t.score.toFixed(2)}</td>
            <td class="py-1 px-2 text-on-surface-variant truncate max-w-[200px]">${t.signals[0] || ''}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ============ Skills ============
async function loadSkills() {
  const resp = await fetch(API + '/api/analytics/skills');
  const d = await resp.json();

  if (!d.quadrant || d.quadrant.length === 0) {
    document.getElementById('skills-quadrant').innerHTML = emptyState('psychology', 'No skills data available', 'Run extraction on uploaded traces to analyze skills.', 'Upload Traces', 'upload');
    document.getElementById('skills-ranking').innerHTML = '';
    return;
  }

  document.getElementById('skills-total').textContent = d.total_skills_detected ?? '--';

  const mu = d.most_used_skill;
  document.getElementById('skills-most-used').textContent = mu ? humanize(mu.skill) : '--';
  document.getElementById('skills-most-used-count').textContent = mu ? `${mu.activations.toLocaleString()} activations` : '';

  const ns = d.noisiest_skill;
  document.getElementById('skills-noisiest').textContent = ns ? humanize(ns.skill) : '--';
  document.getElementById('skills-noisiest-info').textContent = ns ? `High activation, low relevance (${ns.relevance_rate}%)` : '';

  // Quadrant (ECharts)
  const quad = d.quadrant || [];
  Charts.skillsQuadrant(document.getElementById('skills-quadrant'), quad);

  // Ranking
  const top = d.top_skills || [];
  document.getElementById('skills-ranking').innerHTML = `
    <table class="w-full text-[12px]">
      <thead><tr class="border-b border-card-border text-on-surface-variant">
        <th class="text-left py-1 px-1">Skill</th>
        <th class="text-right py-1 px-1">Act</th>
        <th class="text-right py-1 px-1">Rel</th>
      </tr></thead>
      <tbody class="font-mono">
        ${top.map(s => `
          <tr class="border-b border-card-border hover:bg-card-hover">
            <td class="py-1 px-1 text-primary">${humanize(s.skill)}</td>
            <td class="py-1 px-1 text-right">${s.activations.toLocaleString()}</td>
            <td class="py-1 px-1 text-right">${s.relevance_rate}%</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ============ Skills Gap ============
async function loadSkillsGap() {
  const resp = await fetch(API + '/api/analytics/skills-gap');
  const d = await resp.json();

  document.getElementById('gap-total-intents').textContent = d.total_intents ?? '--';
  document.getElementById('gap-existing-skills').textContent = d.total_existing_skills ?? '--';
  document.getElementById('gap-uncovered').textContent = d.uncovered_intent_count ?? '--';
  document.getElementById('gap-low-relevance').textContent = d.low_relevance_intent_count ?? '--';

  // Gap candidates
  const candidates = d.gap_candidates || [];
  const container = document.getElementById('gap-candidates');
  if (candidates.length === 0) {
    container.innerHTML = '<div class="text-center py-8 text-on-surface-variant"><span class="material-symbols-outlined text-[36px] mb-2 block">check_circle</span>No significant skill gaps detected. All frequent intents have adequate skill coverage.</div>';
  } else {
    container.innerHTML = candidates.map((c, i) => {
      const scoreColor = c.gap_score >= 5 ? '#ffb4ab' : c.gap_score >= 3 ? '#ffb869' : '#a4c9ff';
      return `
      <div class="border border-card-border rounded-lg p-5 hover:border-interactive-border transition-colors">
        <div class="flex items-start justify-between mb-3">
          <div class="flex items-center gap-3">
            <span class="text-[20px] font-bold font-mono" style="color:${scoreColor}">#${i + 1}</span>
            <div>
              <div class="text-[16px] font-semibold">${humanize(c.suggested_skill_name)}</div>
              <div class="font-mono text-[13px] text-on-surface-variant">Intent: <span class="text-primary">${humanize(c.intent)}</span></div>
            </div>
          </div>
          <div class="flex items-center gap-4">
            <div class="text-right">
              <div class="text-[11px] text-on-surface-variant">Gap Score</div>
              <div class="text-[20px] font-bold font-mono" style="color:${scoreColor}">${c.gap_score}</div>
            </div>
            <div class="text-right">
              <div class="text-[11px] text-on-surface-variant">Frequency</div>
              <div class="text-[16px] font-semibold">${c.count} <span class="text-[12px] text-on-surface-variant">(${c.frequency_pct}%)</span></div>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-3 mb-3">
          <div class="bg-surface-container-high rounded p-2">
            <div class="text-[11px] text-on-surface-variant">Satisfaction</div>
            <div class="text-[14px] font-semibold">${satBadge(c.mean_satisfaction)}</div>
          </div>
          <div class="bg-surface-container-high rounded p-2">
            <div class="text-[11px] text-on-surface-variant">Goal Achievement</div>
            <div class="text-[14px] font-semibold">${c.goal_achievement_rate}%</div>
          </div>
          <div class="bg-surface-container-high rounded p-2">
            <div class="text-[11px] text-on-surface-variant">Avg Skills/Trace</div>
            <div class="text-[14px] font-semibold">${c.avg_skills_per_trace}</div>
          </div>
          <div class="bg-surface-container-high rounded p-2">
            <div class="text-[11px] text-on-surface-variant">Skill Relevance</div>
            <div class="text-[14px] font-semibold">${c.skill_relevance_rate != null ? c.skill_relevance_rate + '%' : 'N/A'}</div>
          </div>
        </div>

        <div class="mb-3">
          <div class="text-[12px] font-semibold text-on-surface-variant mb-1">Why this gap matters:</div>
          <div class="flex flex-wrap gap-1">
            ${c.reasons.map(r => `<span class="text-[11px] bg-error/10 text-error px-2 py-0.5 rounded">${r}</span>`).join('')}
          </div>
        </div>

        ${c.sub_intents.length > 0 ? `
        <div class="mb-3">
          <div class="text-[12px] font-semibold text-on-surface-variant mb-1">Sub-intents to cover:</div>
          <div class="flex flex-wrap gap-1">
            ${c.sub_intents.map(s => `<span class="text-[11px] bg-primary/10 text-primary px-2 py-0.5 rounded font-mono">${humanize(s.sub_intent)} (${s.count})</span>`).join('')}
          </div>
        </div>` : ''}

        <details class="text-[12px]">
          <summary class="text-on-surface-variant cursor-pointer hover:text-on-surface">Example conversations (${c.sample_summaries.length})</summary>
          <ul class="mt-2 space-y-1 text-on-surface-variant pl-4">
            ${c.sample_summaries.map(s => `<li class="list-disc">${s}</li>`).join('')}
          </ul>
        </details>
      </div>`;
    }).join('');
  }

  // Coverage table
  const coverage = d.skill_coverage || [];
  document.getElementById('gap-coverage-table').innerHTML = coverage.map(c => {
    const covBadge = !c.has_skill_coverage
      ? '<span class="text-[11px] bg-error/20 text-error px-2 py-0.5 rounded">None</span>'
      : c.skill_relevance_rate != null && c.skill_relevance_rate < 40
        ? '<span class="text-[11px] bg-tertiary/20 text-tertiary px-2 py-0.5 rounded">Weak</span>'
        : '<span class="text-[11px] bg-[#4caf50]/20 text-[#4caf50] px-2 py-0.5 rounded">Good</span>';
    return `
      <tr class="border-b border-card-border hover:bg-card-hover transition-colors">
        <td class="px-3 py-2"><span class="bg-primary/10 text-primary px-2 py-[1px] rounded text-[11px]">${humanize(c.intent)}</span></td>
        <td class="px-3 py-2 text-right">${c.count}</td>
        <td class="px-3 py-2 text-right">${satBadge(c.mean_satisfaction)}</td>
        <td class="px-3 py-2 text-right">${c.goal_achievement_rate}%</td>
        <td class="px-3 py-2 text-right">${c.avg_skills_per_trace}</td>
        <td class="px-3 py-2 text-right">${c.skill_relevance_rate != null ? c.skill_relevance_rate + '%' : '--'}</td>
        <td class="px-3 py-2">${covBadge}</td>
      </tr>`;
  }).join('');
}

// ============ Explorer ============
let explorerPage = 1;

async function loadExplorer(page, search) {
  if (page !== undefined && page < 1) return;
  explorerPage = page || 1;
  const perPage = parseInt(document.getElementById('explorer-per-page')?.value || 50);
  const intent = document.getElementById('explorer-intent-filter').value;
  const complexity = document.getElementById('explorer-complexity-filter').value;
  const goal = document.getElementById('explorer-goal-filter').value;

  let url = API + `/api/explorer?page=${explorerPage}&per_page=${perPage}`;
  if (search) url += `&search=${search}`;
  if (intent) url += `&intent=${intent}`;
  if (complexity) url += `&complexity=${complexity}`;
  if (goal) url += `&goal_achieved=${goal}`;
  if (explorerSortBy) url += `&sort_by=${explorerSortBy}&sort_dir=${explorerSortDir}`;

  const resp = await fetch(url);
  const data = await resp.json();

  const tbody = document.getElementById('explorer-table');
  if (data.items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5">${emptyState('database', 'No traces to explore', 'Upload and parse trace files to explore raw data.', 'Upload Traces', 'upload')}</td></tr>`;
    document.getElementById('explorer-showing').textContent = '';
    return;
  }
  tbody.innerHTML = data.items.map(r => `
    <tr class="border-b border-card-border hover:bg-card-hover transition-colors cursor-pointer" onclick="showExplorerDetail(${JSON.stringify(r).replace(/"/g, '&quot;')})">
      <td class="px-4 py-2 text-primary font-mono">${r.trace_id.substring(0, 16)}</td>
      <td class="px-4 py-2"><span class="bg-primary/10 text-primary px-2 py-[1px] rounded text-[11px]">${humanize(r.primary_intent) || '--'}</span></td>
      <td class="px-4 py-2"><span class="text-[11px] px-2 py-[1px] border border-card-border rounded">${r.complexity || '--'}</span></td>
      <td class="px-4 py-2">${r.goal_achieved != null ? (r.goal_achieved ? '<span class="text-[#4caf50]">Yes</span>' : '<span class="text-error">No</span>') : '--'}</td>
      <td class="px-4 py-2">${r.satisfaction_score != null ? satBadge(r.satisfaction_score) : '--'}</td>
    </tr>
  `).join('');

  const totalPages = Math.ceil(data.total / perPage) || 1;
  document.getElementById('explorer-showing').textContent = `Showing ${(explorerPage-1)*perPage+1}-${(explorerPage-1)*perPage+data.items.length} of ${data.total}`;
  const pi = document.getElementById('explorer-page-info'); if (pi) pi.textContent = `Page ${explorerPage} of ${totalPages}`;
  const prev = document.getElementById('explorer-prev'); if (prev) prev.disabled = explorerPage <= 1;
  const next = document.getElementById('explorer-next'); if (next) next.disabled = explorerPage >= totalPages;
}

function showExplorerDetail(item) {
  const el = document.getElementById('explorer-detail');
  el.style.display = '';
  el.innerHTML = `
    <div class="flex justify-between items-start mb-4">
      <h3 class="text-[16px] font-semibold font-mono">Trace: ${item.trace_id}</h3>
      <button onclick="document.getElementById('explorer-detail').style.display='none'" class="text-on-surface-variant hover:text-on-surface">
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>
    <div class="grid grid-cols-2 gap-6">
      <div>
        <h4 class="text-[14px] font-semibold mb-2">Conversation Trace</h4>
        <div class="space-y-3 max-h-[400px] overflow-y-auto pr-2">
          ${(item.messages || []).map(m => `
            <div class="${m.role === 'user' ? 'bg-primary/10 border-primary/20' : 'bg-surface-container-high border-card-border'} border rounded p-3">
              <div class="text-[11px] font-semibold uppercase mb-1">${m.role}</div>
              <div class="text-[13px] whitespace-pre-wrap">${m.content}</div>
            </div>
          `).join('')}
        </div>
      </div>
      <div>
        <h4 class="text-[14px] font-semibold mb-2">Raw JSON Payload</h4>
        <pre class="bg-background border border-card-border rounded p-3 text-[11px] font-mono max-h-[400px] overflow-auto text-on-surface-variant">${JSON.stringify(item.raw_json, null, 2)}</pre>
      </div>
    </div>
  `;
  el.scrollIntoView({ behavior: 'smooth' });
}

async function exportExplorer(format) {
  if (format === 'json') {
    const resp = await fetch(API + '/api/results/export/json');
    const data = await resp.json();
    downloadBlob(JSON.stringify(data, null, 2), 'intent_results.json', 'application/json');
  }
}

async function exportGapReport() {
  try {
    const resp = await fetch(API + '/api/analytics/skills-gap/export');
    if (!resp.ok) {
      alert('No data to export. Run extraction first.');
      return;
    }
    const data = await resp.json();
    const filename = `gap-report-${new Date().toISOString().slice(0, 10)}.json`;
    downloadBlob(JSON.stringify(data, null, 2), filename, 'application/json');
  } catch (e) {
    alert('Export failed: ' + e.message);
  }
}

// ============ Langfuse Import ============
async function checkLangfuseStatus() {
  try {
    const resp = await fetch(API + '/api/import/langfuse/status');
    const data = await resp.json();
    const badge = document.getElementById('langfuse-status-badge');
    if (badge) {
      if (data.configured) {
        badge.textContent = 'Connected';
        badge.className = 'ml-auto text-[12px] px-2 py-0.5 rounded font-semibold bg-green-900/30 text-[#4caf50]';
      } else {
        badge.textContent = 'Not Connected';
        badge.className = 'ml-auto text-[12px] px-2 py-0.5 rounded font-semibold bg-red-900/30 text-error';
      }
    }
  } catch(e) {}
}

async function fetchFromLangfuse() {
  const btn = document.getElementById('lf-fetch-btn');
  const resultDiv = document.getElementById('lf-result');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined text-[20px] animate-spin">progress_activity</span> Fetching...';

  const tagsRaw = document.getElementById('lf-tags').value.trim();
  const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : null;

  const body = {
    limit: parseInt(document.getElementById('lf-limit').value) || 50,
    user_id: document.getElementById('lf-user-id').value.trim() || null,
    session_id: document.getElementById('lf-session-id').value.trim() || null,
    name: document.getElementById('lf-name').value.trim() || null,
    tags: tags,
  };

  try {
    const resp = await fetch(API + '/api/import/langfuse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();

    resultDiv.classList.remove('hidden');
    if (!resp.ok) {
      resultDiv.className = 'mt-4 p-3 rounded text-[13px] bg-red-900/20 text-error border border-red-900/40';
      resultDiv.textContent = data.detail || 'Failed to fetch traces';
    } else {
      resultDiv.className = 'mt-4 p-3 rounded text-[13px] bg-green-900/20 text-[#4caf50] border border-green-900/40';
      resultDiv.innerHTML = `Fetched <strong>${data.fetched}</strong> traces from Langfuse — <strong>${data.imported}</strong> imported, <strong>${data.skipped_duplicates}</strong> duplicates skipped. Total traces in project: <strong>${data.total_traces}</strong>`;

      if (data.traces && data.traces.length > 0) {
        document.getElementById('parsed-section').style.display = '';
        document.getElementById('parsed-title').textContent = `Imported ${data.imported} traces from Langfuse`;
        const cards = document.getElementById('parsed-cards');
        cards.innerHTML = data.traces.slice(0, 6).map(t => `
          <div class="bg-card border border-card-border rounded p-4 hover:border-interactive-border transition-colors">
            <div class="flex justify-between items-start mb-2">
              <span class="font-mono text-[13px] text-primary bg-primary/10 px-2 py-[2px] rounded">${t.trace_id.substring(0, 12)}...</span>
              <span class="text-[13px] text-on-surface-variant flex items-center gap-1">
                <span class="material-symbols-outlined text-[14px]">chat</span> ${t.num_messages} messages
              </span>
            </div>
            <div class="text-[13px] text-on-surface-variant mb-3 flex items-center gap-1">
              <span class="material-symbols-outlined text-[14px]">build</span> ${t.num_tool_calls} tool calls
            </div>
            <div class="flex flex-wrap gap-1 mb-3">
              ${t.skills_activated.map(s => `<span class="bg-tertiary-container/10 text-tertiary-container font-mono text-[10px] px-2 py-[1px] border border-tertiary-container/20 rounded-full">${humanize(s)}</span>`).join('')}
            </div>
            <p class="text-[12px] text-on-surface-variant line-clamp-2">${t.preview}</p>
          </div>
        `).join('');
      }
    }
  } catch(e) {
    resultDiv.classList.remove('hidden');
    resultDiv.className = 'mt-4 p-3 rounded text-[13px] bg-red-900/20 text-error border border-red-900/40';
    resultDiv.textContent = 'Network error: ' + e.message;
  }

  btn.disabled = false;
  btn.innerHTML = '<span class="material-symbols-outlined text-[20px]">cloud_download</span> Fetch Traces';
}

// ============ LangSmith Import ============
async function checkLangSmithStatus() {
  try {
    const resp = await fetch(API + '/api/import/langsmith/status');
    const data = await resp.json();
    const badge = document.getElementById('langsmith-status-badge');
    if (badge) {
      if (data.configured) {
        badge.textContent = 'Connected';
        badge.className = 'ml-auto text-[12px] px-2 py-0.5 rounded font-semibold bg-green-900/30 text-[#4caf50]';
      } else {
        badge.textContent = 'Not Connected';
        badge.className = 'ml-auto text-[12px] px-2 py-0.5 rounded font-semibold bg-red-900/30 text-error';
      }
    }
  } catch(e) {}
}

async function loadLangSmithProjects() {
  const sel = document.getElementById('ls-project-select');
  try {
    const resp = await fetch(API + '/api/import/langsmith/projects');
    if (!resp.ok) { sel.classList.add('hidden'); return; }
    const data = await resp.json();
    sel.innerHTML = '<option value="">Select a project...</option>' +
      data.projects.map(p => `<option value="${p.name}">${p.name}</option>`).join('');
    sel.classList.remove('hidden');
  } catch(e) {
    sel.classList.add('hidden');
  }
}

async function fetchFromLangSmith() {
  const btn = document.getElementById('ls-fetch-btn');
  const resultDiv = document.getElementById('ls-result');
  btn.disabled = true;
  btn.innerHTML = '<span class="material-symbols-outlined text-[20px] animate-spin">progress_activity</span> Fetching...';

  const body = {
    project_name: document.getElementById('ls-project-name').value.trim() || null,
    limit: parseInt(document.getElementById('ls-limit').value) || 50,
    run_type: document.getElementById('ls-run-type').value || null,
    is_root: document.getElementById('ls-root-only').checked,
  };

  try {
    const resp = await fetch(API + '/api/import/langsmith', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    let data;
    try { data = await resp.json(); } catch { data = {}; }

    resultDiv.classList.remove('hidden');
    if (!resp.ok) {
      resultDiv.className = 'mt-4 p-3 rounded text-[13px] bg-red-900/20 text-error border border-red-900/40';
      resultDiv.textContent = data.detail || `Server error (${resp.status}). Check your LangSmith API key and project name.`;
    } else {
      resultDiv.className = 'mt-4 p-3 rounded text-[13px] bg-green-900/20 text-[#4caf50] border border-green-900/40';
      resultDiv.innerHTML = `Fetched <strong>${data.fetched}</strong> runs from LangSmith — <strong>${data.imported}</strong> imported, <strong>${data.skipped_duplicates}</strong> duplicates skipped. Total traces in project: <strong>${data.total_traces}</strong>`;

      if (data.traces && data.traces.length > 0) {
        document.getElementById('parsed-section').style.display = '';
        document.getElementById('parsed-title').textContent = `Imported ${data.imported} runs from LangSmith`;
        const cards = document.getElementById('parsed-cards');
        cards.innerHTML = data.traces.slice(0, 6).map(t => `
          <div class="bg-card border border-card-border rounded p-4 hover:border-interactive-border transition-colors">
            <div class="flex justify-between items-start mb-2">
              <span class="font-mono text-[13px] text-primary bg-primary/10 px-2 py-[2px] rounded">${t.trace_id.substring(0, 12)}...</span>
              <span class="text-[13px] text-on-surface-variant flex items-center gap-1">
                <span class="material-symbols-outlined text-[14px]">chat</span> ${t.num_messages} messages
              </span>
            </div>
            <div class="text-[13px] text-on-surface-variant mb-3 flex items-center gap-1">
              <span class="material-symbols-outlined text-[14px]">build</span> ${t.num_tool_calls} tool calls
            </div>
            <div class="flex flex-wrap gap-1 mb-3">
              ${t.skills_activated.map(s => `<span class="bg-tertiary-container/10 text-tertiary-container font-mono text-[10px] px-2 py-[1px] border border-tertiary-container/20 rounded-full">${humanize(s)}</span>`).join('')}
            </div>
            <p class="text-[12px] text-on-surface-variant line-clamp-2">${t.preview}</p>
          </div>
        `).join('');
      }
    }
  } catch(e) {
    resultDiv.classList.remove('hidden');
    resultDiv.className = 'mt-4 p-3 rounded text-[13px] bg-red-900/20 text-error border border-red-900/40';
    resultDiv.textContent = 'Network error: ' + e.message;
  }

  btn.disabled = false;
  btn.innerHTML = '<span class="material-symbols-outlined text-[20px]">hub</span> Fetch Runs';
}

// ============ Settings ============
async function loadSettings() {
  const resp = await fetch(API + '/api/settings');
  const d = await resp.json();
  document.getElementById('set-model').value = d.model_name || '';
  document.getElementById('set-concurrency').value = d.concurrency || 5;
  document.getElementById('set-concurrency-val').textContent = d.concurrency || 5;
  document.getElementById('set-temperature').value = (d.temperature || 0) * 10;
  document.getElementById('set-temperature-val').textContent = (d.temperature || 0).toFixed(1);
  document.getElementById('set-sat-thresh').value = (d.satisfaction_threshold || 0.85) * 100;
  document.getElementById('set-sat-thresh-val').textContent = (d.satisfaction_threshold || 0.85).toFixed(2);
  document.getElementById('set-skills-rel').value = (d.skills_relevance || 0.5) * 100;
  document.getElementById('set-skills-rel-val').textContent = (d.skills_relevance || 0.5).toFixed(2);
  document.getElementById('set-sbert-high').value = (d.sbert_high_cutoff || 0.6) * 100;
  document.getElementById('set-sbert-high-val').textContent = (d.sbert_high_cutoff || 0.6).toFixed(2);
  document.getElementById('set-sbert-low').value = (d.sbert_low_cutoff || 0.35) * 100;
  document.getElementById('set-sbert-low-val').textContent = (d.sbert_low_cutoff || 0.35).toFixed(2);
  document.getElementById('set-lf-host').value = d.langfuse_host || 'https://cloud.langfuse.com';
  if (d.has_langfuse_keys) {
    document.getElementById('set-lf-public').placeholder = '••••••• (configured)';
    document.getElementById('set-lf-secret').placeholder = '••••••• (configured)';
  }
  document.getElementById('set-ls-host').value = d.langsmith_host || 'https://api.smith.langchain.com';
  if (d.has_langsmith_key) {
    document.getElementById('set-ls-apikey').placeholder = '••••••• (configured)';
  }
}

async function saveSettings() {
  const body = {
    model_name: document.getElementById('set-model').value,
    api_key: document.getElementById('set-apikey').value || undefined,
    concurrency: parseInt(document.getElementById('set-concurrency').value),
    temperature: parseInt(document.getElementById('set-temperature').value) / 10,
    satisfaction_threshold: parseInt(document.getElementById('set-sat-thresh').value) / 100,
    skills_relevance: parseInt(document.getElementById('set-skills-rel').value) / 100,
    sbert_high_cutoff: parseInt(document.getElementById('set-sbert-high').value) / 100,
    sbert_low_cutoff: parseInt(document.getElementById('set-sbert-low').value) / 100,
    langfuse_public_key: document.getElementById('set-lf-public').value || undefined,
    langfuse_secret_key: document.getElementById('set-lf-secret').value || undefined,
    langfuse_host: document.getElementById('set-lf-host').value || undefined,
    langsmith_api_key: document.getElementById('set-ls-apikey').value || undefined,
    langsmith_host: document.getElementById('set-ls-host').value || undefined,
  };
  await fetch(API + '/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  alert('Settings saved!');
  checkLangfuseStatus();
  checkLangSmithStatus();
}

// Range slider live updates
document.querySelectorAll('input[type="range"]').forEach(el => {
  el.addEventListener('input', () => {
    const valEl = document.getElementById(el.id + '-val');
    if (!valEl) return;
    if (el.id === 'set-concurrency') valEl.textContent = el.value;
    else if (el.id === 'set-temperature') valEl.textContent = (el.value / 10).toFixed(1);
    else valEl.textContent = (el.value / 100).toFixed(2);
  });
});

// ============ Utilities ============
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function satBadge(score) {
  const color = score >= 0.85 ? '#4caf50' : score >= 0.55 ? '#ffb869' : '#ffb4ab';
  return `<span class="font-mono text-[12px] px-2 py-[1px] rounded" style="background:${color}20;color:${color}">${score.toFixed(2)}</span>`;
}

function downloadBlob(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// Drag & Drop
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('border-primary'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('border-primary'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('border-primary');
  if (e.dataTransfer.files.length) handleFileUpload(e.dataTransfer.files);
});

// ============ Startup ============
loadProjects();
loadDashboard();
checkLangfuseStatus();
checkLangSmithStatus();
