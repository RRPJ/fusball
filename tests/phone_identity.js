const phoneIdentityFetch = window.fetch;
window.fetch = (url, options) => {
  if (url.startsWith('/api/public/leaderboard?')) return Promise.resolve(new Response('{}', {status: 503}));
  return phoneIdentityFetch(url, options);
};

window.addEventListener('load', async () => {
  const waitFor = async (predicate, message) => {
    for (let i = 0; i < 200; i++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(message);
  };
  try {
    const body = document.getElementById('leaderboardBody');
    await waitFor(() => body.querySelectorAll('.profile-toggle').length === 2, 'standings');
    document.getElementById('sortStreakBtn').click();
    await waitFor(() => body.querySelector('tr td:last-child')?.textContent === '3', 'streak sort');
    const rows = [...body.querySelectorAll('tr')];
    if (rows.map(row => row.lastElementChild.textContent).join(',') !== '3,1') throw new Error('streak identities');
    for (const [row, expected] of [[rows[0], '3 straight wins'], [rows[1], '1 straight wins']]) {
      row.querySelector('button').click();
      await waitFor(() => row.nextElementSibling?.textContent.includes(expected), 'profile identity');
    }
    document.getElementById('sortFormBtn').click();
    if ([...body.querySelectorAll('tr')].map(row => row.lastElementChild.textContent.trim()).sort().join(',') !== 'L,W W') {
      throw new Error('form identities');
    }
    document.getElementById('filterThisMonthBtn').click();
    document.getElementById('sortImprovedBtn').click();
    await waitFor(() => body.querySelector('tr td:last-child')?.textContent === '+4', 'improved sort');
    if ([...body.querySelectorAll('tr')].map(row => row.lastElementChild.textContent).join(',') !== '+4,-1') {
      throw new Error('improved identities');
    }
    document.getElementById('sortStreakBtn').click();
    await waitFor(() => body.querySelector('tr td:last-child')?.textContent === '3', 'restore streak');
    const fetchOriginal = window.fetch;
    let publicRequested = false;
    window.fetch = (url, options) => {
      if (url.startsWith('/api/leaderboard?')) return Promise.resolve(new Response('{}', {status: 403}));
      if (url.startsWith('/api/public/leaderboard?')) publicRequested = true;
      return fetchOriginal(url, options);
    };
    try {
      await refreshLeaderboard();
      throw new Error('protected leaderboard denial ignored');
    } catch (error) {
      if (error.message !== 'Could not refresh leaderboard.') throw error;
    }
    if (publicRequested) throw new Error('public standings bypassed protected read');
    window.fetch = fetchOriginal;
    setOfflineMode('Test offline.');
    if ([...body.querySelectorAll('tr')].map(row => row.lastElementChild.textContent).join(',') !== '3,1') {
      throw new Error('cached standings lost player identities');
    }
    localStorage.setItem('fusball_leaderboard_snapshot', JSON.stringify({
      items: [{name: 'John Smith', position: 1, level: 20, offense_level: 10, defense_level: 10}],
      cachedAt: new Date().toISOString(), scope: 'all',
    }));
    await refreshLeaderboard();
    const cachedRow = body.querySelector('tr');
    if (!cachedRow.textContent.includes('John Smith') || cachedRow.lastElementChild.textContent !== '1' ||
        cachedRow.querySelector('button').disabled) throw new Error('legacy snapshot behavior');
    if (!document.getElementById('leaderboardFreshness').textContent.includes('identities unverified')) {
      throw new Error('legacy snapshot warning');
    }
    clearOfflineMode();
    cachedRow.querySelector('button').click();
    await waitFor(() => cachedRow.nextElementSibling?.textContent.includes('1 straight wins'), 'legacy profile after reconnect');
    document.body.dataset.testResult = 'pass';
  } catch (error) {
    document.body.dataset.testResult = `fail: ${error.message}`;
  }
});
