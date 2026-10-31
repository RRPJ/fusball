// This script runs against the rendered phone page and an isolated local store.
const browserTestMode = new URLSearchParams(location.search).get('test');
const originalFetch = window.fetch;
const submitted = [];
let failuresRemaining = browserTestMode === 'doubles' ? 2 : 0;
let offline = false;
window.fetch = async (url, options = {}) => {
  if (offline && url === '/api/health') {
    return new Response('{}', { status: 503 });
  }
  if (url === '/api/matches' && options.method === 'POST') {
    submitted.push({ body: JSON.parse(options.body), key: options.headers.get('Idempotency-Key') });
    if (failuresRemaining) {
      const conflict = failuresRemaining-- === 2;
      return new Response(JSON.stringify({ error: conflict ? 'Writer busy. Try again.' : 'Submit failed.' }), {
        status: conflict ? 409 : 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  }
  return originalFetch(url, options);
};

window.addEventListener('load', async () => {
  const byId = id => document.getElementById(id);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const waitFor = async (predicate, message) => {
    for (let i = 0; i < 200; i++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(message);
  };
  const selectPlayer = name => {
    const button = [...byId('presentPlayersPanel').querySelectorAll('button')]
      .find(node => node.textContent === name);
    assert(button, `missing present player ${name}`);
    button.click();
  };
  const score = (team, value) => [...byId(`score${team}`).querySelectorAll('button')]
    .find(button => button.textContent === String(value)).click();
  try {
    await waitFor(() => byId('presentPlayersPanel').textContent.includes('Alice'), 'players did not load');
    assert(document.documentElement.scrollWidth <= innerWidth, 'horizontal overflow');
    byId('modeSingles').focus();
    assert(document.activeElement === byId('modeSingles'), 'mode must be keyboard focusable');
    assert(getComputedStyle(byId('modeSingles')).outlineStyle !== 'none', 'focus must be visible');
    if (browserTestMode === 'doubles') byId('modeDoubles').click();
    byId('nextBtn').click();
    assert(byId('nextBtn').disabled, 'incomplete lineup should block progress');
    if (browserTestMode === 'doubles') {
      ['Alice', 'Bob', 'Carol', 'Dave'].forEach(selectPlayer);
      assert(byId('valRedDef').textContent === 'Alice' && byId('valRedOff').textContent === 'Bob', 'red positions');
      assert(byId('valBlueDef').textContent === 'Carol' && byId('valBlueOff').textContent === 'Dave', 'blue positions');
      byId('swapRedBtn').click();
      assert(byId('valRedDef').textContent === 'Bob', 'swap positions');
      byId('undoBtn').click();
      assert(byId('valRedDef').textContent === 'Alice', 'undo swap');
      byId('clearBtn').click();
      assert(byId('nextBtn').disabled, 'clear lineup should block progress');
      ['Alice', 'Bob', 'Carol', 'Dave'].forEach(selectPlayer);
    } else {
      ['Alice', 'Bob'].forEach(selectPlayer);
    }
    byId('nextBtn').click();
    score('Red', 3);
    score('Blue', 3);
    assert(byId('nextBtn').disabled, 'tied score should block progress');
    score('Red', 5);
    assert(!byId('nextBtn').disabled, 'finished score should allow review');
    byId('nextBtn').click();
    const review = byId('reviewText').textContent;
    assert(review.includes('Final Score: 5 - 3'), 'score missing from review');
    if (browserTestMode === 'doubles') {
      assert(review.includes('Alice + Bob') && review.includes('Carol + Dave'), 'review must show defense first');
    }
    byId('writePin').value = 'test-token';
    if (browserTestMode === 'doubles') {
      for (const message of ['Writer busy. Try again.', 'Submit failed.']) {
        byId('submitBtn').click();
        await waitFor(() => byId('statusText').textContent === message, `missing ${message}`);
        assert(byId('statusText').getClientRects().length > 0, 'submission error is not visible');
        assert(!byId('submitBtn').disabled, 'retry unavailable');
      }
    }
    byId('submitBtn').click();
    await waitFor(() => byId('statusText').textContent.includes('Result submitted.'), 'submission did not succeed');
    await waitFor(() => byId('step2').classList.contains('active'), 'did not return to players');
    const last = submitted[submitted.length - 1];
    assert(last.key, 'idempotency key missing');
    assert(JSON.stringify(last.body.team1) === JSON.stringify(browserTestMode === 'doubles' ? ['bob', 'alice'] : ['alice']), 'red payload order');
    assert(JSON.stringify(last.body.team2) === JSON.stringify(browserTestMode === 'doubles' ? ['dave', 'carol'] : ['bob']), 'blue payload order');
    byId('stepBtn1').click();
    const aliceRow = [...byId('leaderboardBody').querySelectorAll('tr')]
      .find(row => row.textContent.includes('Alice'));
    assert(aliceRow, 'refreshed standings missing player');
    aliceRow.click();
    const matches = browserTestMode === 'doubles' ? '2 matches' : '1 match';
    await waitFor(() => byId('leaderboardBody').textContent.includes(matches), 'updated player profile missing match');
    offline = true;
    await waitFor(() => document.body.classList.contains('offline'), 'offline state not shown');
    assert(byId('offlineBanner').getClientRects().length > 0, 'offline banner not visible');
    assert(byId('stickyBar').getClientRects().length === 0, 'match entry available offline');
    assert(byId('leaderboardBody').textContent.includes('Alice'), 'cached leaderboard missing');
    document.body.dataset.testResult = 'pass';
  } catch (error) {
    document.body.dataset.testResult = `fail: ${error.message}`;
  }
});
