// Clerk is a boundary stub; all match operations use the isolated application store.
const originalFetch = window.fetch;
const correctionRequests = [];
let conflict = true;
let adminLoads = 0;
window.fetch = async (url, options = {}) => {
  if (String(url).startsWith('/api/admin/matches/') && options.method === 'POST') {
    correctionRequests.push({ body: JSON.parse(options.body), key: options.headers.get('Idempotency-Key') });
    if (conflict) {
      conflict = false;
      return new Response(JSON.stringify({ error: 'Match changed. Refresh and retry.' }), {
        status: 409, headers: { 'Content-Type': 'application/json' },
      });
    }
  }
  const response = await originalFetch(url, options);
  if (url === '/api/admin/matches?limit=30') adminLoads++;
  return response;
};
window.addEventListener('load', async () => {
  const role = new URLSearchParams(location.search).get('role');
  const byId = id => document.getElementById(id);
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const waitFor = async (predicate, message) => {
    for (let i = 0; i < 200; i++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(message);
  };
  try {
    await waitFor(() => byId('managedAuthStatus').textContent.includes('Signed in'), 'sign-in missing');
    if (role !== 'admin') {
      const response = await fetch('/api/admin/matches', { headers: { Authorization: `Bearer ${role}` } });
      assert(response.status === 403, 'non-admin correction API must be forbidden');
      assert(byId('adminNavBtn').getClientRects().length === 0, 'non-admin correction navigation visible');
    } else {
      await waitFor(() => byId('adminNavBtn').getClientRects().length > 0, 'admin navigation missing');
      byId('adminNavBtn').click();
      await waitFor(() => adminLoads >= 2 && byId('adminMatchesList').textContent.includes('Void match'), 'match missing');
      await new Promise(resolve => setTimeout(resolve, 50));
      window.prompt = () => 'no';
      window.confirm = () => true;
      byId('adminMatchesList').querySelector('button').click();
      assert(byId('adminMatchesStatus').textContent.includes('at least 3'), 'reason validation missing');
      window.prompt = () => 'Incorrect score';
      byId('adminMatchesList').querySelector('button').click();
      await waitFor(() => byId('adminMatchesStatus').textContent.includes('Match changed'), 'conflict feedback missing');
      byId('adminMatchesList').querySelector('button').click();
      await waitFor(() => byId('adminMatchesList').textContent.includes('Restore match'), 'void failed');
      assert(byId('adminMatchesStatus').textContent.includes('Match voided'), 'void success feedback missing');
      assert(byId('adminMatchesList').textContent.includes('Incorrect score'), 'audit reason missing');
      window.prompt = () => 'Restore result';
      byId('adminMatchesList').querySelector('button').click();
      await waitFor(() => byId('adminMatchesList').textContent.includes('Void match'), 'restore failed');
      assert(byId('adminMatchesStatus').textContent.includes('Match restored'), 'restore success feedback missing');
      assert(byId('adminMatchesList').textContent.includes('Restore result'), 'restore reason missing');
      assert(correctionRequests.every(request => request.key), 'correction idempotency key missing');
      assert(correctionRequests[1].body.expected_version === 1 && correctionRequests[2].body.expected_version === 2, 'correction versions missing');
      const audit = await fetch('/api/admin/matches', { headers: { Authorization: 'Bearer admin' } }).then(response => response.json());
      assert(audit.items[0].events.at(-1).actor_subject === 'user_admin', 'correction actor missing');
    }
    document.body.dataset.testResult = 'pass';
  } catch (error) {
    document.body.dataset.testResult = `fail: ${error.message}`;
  }
});
