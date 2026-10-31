(() => {
  const cacheKey = 'fusball_public_leaderboard_snapshot_v2';
  const labels = {total: 'Total', offense: 'Offense', defense: 'Defense', form: 'Form', streak: 'Streak', improved: 'Improved'};
  const periods = {all: 'All time', this_quarter: 'This quarter', this_month: 'This month', this_week: 'This week'};
  const metricButtons = [...document.querySelectorAll('[data-metric]')];
  const periodButtons = [...document.querySelectorAll('[data-scope]')];
  const body = document.getElementById('leaderboardBody');
  const status = document.getElementById('status');
  let metric = 'total', scope = 'all', snapshot = null, stale = false, version = 0;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const statsRequired = value => ['form', 'streak', 'improved'].includes(value);
  const readCache = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(cacheKey));
      if (saved && labels[saved.metric] && periods[saved.scope] &&
          !(saved.metric === 'improved' && saved.scope === 'all') &&
          Array.isArray(saved.items) && saved.stats && typeof saved.stats === 'object') return saved;
    } catch (_) { /* Storage is optional. */ }
    return null;
  };
  const saveCache = data => {
    try { localStorage.setItem(cacheKey, JSON.stringify(data)); } catch (_) { /* Storage is optional. */ }
  };
  function controls() {
    metricButtons.forEach(button => {
      button.classList.toggle('active', button.dataset.metric === metric);
      button.setAttribute('aria-pressed', String(button.dataset.metric === metric));
      button.disabled = stale || (button.dataset.metric === 'improved' && scope === 'all');
    });
    periodButtons.forEach(button => {
      button.classList.toggle('active', button.dataset.scope === scope);
      button.setAttribute('aria-pressed', String(button.dataset.scope === scope));
      button.disabled = stale;
    });
    document.getElementById('metricHeader').textContent = labels[metric];
    document.getElementById('hint').textContent = metric === 'improved' ? 'Improved: delta on all-time leaderboard baseline.' : '';
  }
  function sortValue(row, stats) {
    const data = stats[row.player_id] || {};
    if (metric === 'offense') return Number(row.offense_level || 0);
    if (metric === 'defense') return Number(row.defense_level || 0);
    if (metric === 'form') return Number(data.win_rate || 0);
    if (metric === 'streak') return Number(data.streak || 0);
    if (metric === 'improved') return Number(data.improved || 0);
    return Number(row.level || 0);
  }
  function metricValue(row, stats) {
    const data = stats[row.player_id];
    if (statsRequired(metric) && !data) return '—';
    if (metric === 'form') return esc(data.recent_form_5);
    if (metric === 'streak') return esc(data.streak);
    if (metric === 'improved') return `${Number(data.improved) >= 0 ? '+' : ''}${esc(data.improved)}`;
    return esc(metric === 'offense' ? row.offense_level : metric === 'defense' ? row.defense_level : row.level);
  }
  function render() {
    controls();
    if (!snapshot) {
      body.innerHTML = '<tr><td colspan="3">Leaderboard unavailable.</td></tr>';
      return;
    }
    const rows = [...snapshot.items].sort((a, b) => sortValue(b, snapshot.stats) - sortValue(a, snapshot.stats) || Number(a.position || 999) - Number(b.position || 999));
    body.innerHTML = rows.length ? rows.map((row, i) =>
      `<tr><td>${i + 1}</td><td><button class="btn small profile-link" type="button" ${stale ? 'disabled' : ''} data-player="${esc(row.player_id)}">${esc(row.name)}</button><div class="sub">Off&nbsp;${esc(row.offense_level)} · Def&nbsp;${esc(row.defense_level)}</div></td><td>${metricValue(row, snapshot.stats)}</td></tr>`
    ).join('') : '<tr><td colspan="3">No players found.</td></tr>';
    body.querySelectorAll('.profile-link').forEach(button => button.addEventListener('click', () => openProfile(button)));
  }
  function fail(message) {
    stale = true;
    snapshot = readCache();
    if (snapshot) {
      metric = snapshot.metric;
      scope = snapshot.scope;
      status.textContent = `${message} Stale saved leaderboard: ${labels[metric]}, ${periods[scope]} (saved ${snapshot.savedAt}). Player profiles require a connection. Retry when the service is available.`;
    } else {
      status.textContent = `${message} Leaderboard unavailable; no saved snapshot. Player profiles require a connection. Retry when the service is available.`;
    }
    render();
  }
  async function getJson(url) {
    const response = await fetch(url, {cache: 'no-store'});
    if (!response.ok) throw new Error(`Service error (${response.status}).`);
    return response.json();
  }
  async function refresh() {
    const request = ++version;
    if (!navigator.onLine) { fail('Offline.'); return; }
    stale = false;
    controls();
    body.innerHTML = '<tr><td colspan="3">Loading standings...</td></tr>';
    status.textContent = 'Loading standings...';
    try {
      const query = `scope=${encodeURIComponent(scope)}`;
      const requests = [getJson(`/api/public/leaderboard?limit=50&${query}`)];
      if (statsRequired(metric)) requests.push(getJson(`/api/public/stats?${query}`));
      const [data, stats = {}] = await Promise.all(requests);
      if (request !== version) return;
      snapshot = {metric, scope, items: data.items, stats, savedAt: new Date().toLocaleString()};
      stale = false;
      saveCache(snapshot);
      status.textContent = `Live leaderboard: ${labels[metric]}, ${periods[scope]}.`;
      render();
    } catch (error) {
      if (request !== version) return;
      fail(navigator.onLine ? `Could not refresh leaderboard. ${error.message}` : 'Offline.');
    }
  }
  function card(label, item) {
    if (!item) return `<div class="profile-card"><div class="label">${label}</div><div class="value">No data yet</div></div>`;
    return `<div class="profile-card"><div class="label">${label}</div><div class="value">${esc(item.player)}</div><div class="subvalue">${esc(item.wins)}-${esc(item.losses)}${item.draws ? ` (${esc(item.draws)}D)` : ''} in ${esc(item.matches)} matches</div></div>`;
  }
  const delta = value => {
    const number = Number(value || 0);
    return `${number >= 0 ? '+' : ''}${number.toFixed(1)}`;
  };
  function profileHtml(data) {
    const s = data.summary || {}, trend = data.trend || {};
    const matches = (data.recent_matches || []).map(match =>
      `<div class="recent-match"><div class="kv">${match.won ? 'W' : 'L'} ${esc((match.timestamp || '?').slice(0, 10))} <strong>${esc(match.score_for)}-${esc(match.score_against)}</strong></div><div class="sub">${esc(match.team.join(' + '))} vs ${esc(match.opponents.join(' + '))}</div><div class="kv">Off ${delta(match.delta.offense)} Def ${delta(match.delta.defense)}</div></div>`
    ).join('') || '<div class="kv">No matches recorded yet.</div>';
    return `<div class="profile-panel"><div class="profile-header"><div><div class="profile-title">${esc(data.player)}</div><div class="profile-meta">${esc(s.wins || 0)}-${esc((s.games || 0) - (s.wins || 0))} in ${esc(s.games || 0)} matches · ${Math.round((s.win_rate || 0) * 100)}% win rate</div></div><div class="profile-meta">Form ${esc(s.recent_form_5 || 'No recent form')}</div></div><div class="profile-cards"><div class="profile-card"><div class="label">Current Streak</div><div class="value">${s.streak ? `${esc(s.streak)} straight wins` : 'No current streak'}</div><div class="subvalue">Last match ${esc(s.last_match ? s.last_match.slice(0, 10) : 'n/a')}</div></div>${card('Best Partner', data.best_partner)}${card('Toughest Opponent', data.toughest_opponent)}</div><div class="trend-row"><div class="trend-pill"><div class="label">Offense Trend</div><div class="value">${delta(trend.offense)}</div></div><div class="trend-pill"><div class="label">Defense Trend</div><div class="value">${delta(trend.defense)}</div></div></div><div><div class="profile-meta">Recent Matches</div>${matches}</div></div>`;
  }
  async function openProfile(button) {
    if (stale || !navigator.onLine) { fail('Offline.'); return; }
    const row = button.closest('tr');
    if (row.nextElementSibling?.classList.contains('expand-row')) { row.nextElementSibling.remove(); return; }
    body.querySelectorAll('.expand-row').forEach(el => el.remove());
    const expanded = document.createElement('tr');
    expanded.className = 'expand-row';
    expanded.innerHTML = '<td colspan="3" class="expand-panel">Loading player profile...</td>';
    row.after(expanded);
    const selectedScope = scope, request = version;
    try {
      const data = await getJson(`/api/public/player/${encodeURIComponent(button.dataset.player)}/profile?scope=${encodeURIComponent(selectedScope)}&recent_limit=5`);
      if (request === version && !stale && expanded.isConnected) expanded.firstElementChild.innerHTML = profileHtml(data);
    } catch (error) {
      if (request !== version) return;
      fail(navigator.onLine ? `Could not load player profile. ${error.message}` : 'Offline.');
    }
  }
  metricButtons.forEach(button => button.addEventListener('click', () => { metric = button.dataset.metric; refresh(); }));
  periodButtons.forEach(button => button.addEventListener('click', () => {
    scope = button.dataset.scope;
    if (scope === 'all' && metric === 'improved') metric = 'total';
    refresh();
  }));
  const retry = document.createElement('button');
  retry.className = 'btn small';
  retry.type = 'button';
  retry.textContent = 'Retry connection';
  retry.addEventListener('click', refresh);
  status.after(retry);
  window.addEventListener('offline', () => { ++version; fail('Offline.'); });
  window.addEventListener('online', refresh);
  refresh();
})();
