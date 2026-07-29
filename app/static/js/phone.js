    const slots = ['red_offense', 'red_defense', 'blue_offense', 'blue_defense'];
    const stepButtons = [null, document.getElementById('stepBtn1'), document.getElementById('stepBtn2'), document.getElementById('stepBtn3'), document.getElementById('stepBtn4')];
    const stepSections = [null, document.getElementById('step1'), document.getElementById('step2'), document.getElementById('step3'), document.getElementById('step4')];
    const leaderboardSection = document.getElementById('leaderboardSection');
    const adminMatchesSection = document.getElementById('adminMatchesSection');
    const adminNavBtn = document.getElementById('adminNavBtn');
    const appContent = document.getElementById('appContent');
    const stickyBar = document.getElementById('stickyBar');
    const slotToElement = {
      red_offense: document.getElementById('slotRedOff'),
      red_defense: document.getElementById('slotRedDef'),
      blue_offense: document.getElementById('slotBlueOff'),
      blue_defense: document.getElementById('slotBlueDef'),
    };
    const slotToValue = {
      red_offense: document.getElementById('valRedOff'),
      red_defense: document.getElementById('valRedDef'),
      blue_offense: document.getElementById('valBlueOff'),
      blue_defense: document.getElementById('valBlueDef'),
    };

    const state = {
      bootedAt: Date.now(),
      step: 1,
      mode: 'singles',
      activeSlot: 'red_offense',
      leaderboardSort: 'total',
      leaderboardFilter: 'all',
      leaderboardItems: [],
      playerStats: null,
      playerStatsScope: null,
      expandedPlayer: null,
      h2hOpen: false,
      isSubmitting: false,
      offline: false,
      readPinPromptPromise: null,
      healthTimerId: null,
      freshnessTimerId: null,
      inFlightGetControllers: new Set(),
      requestState: {},
      leaderboardSource: 'server',
      leaderboardCacheAt: null,
      leaderboardRequestVersion: 0,
      statsRequestVersion: 0,
      lastOnlineAt: null,
      lastOfflineAt: null,
      offlineReason: '',
      players: [],
      activePlayers: [],
      adminMatches: [],
      isAdmin: false,
      latestOdds: null,
      currentQuipKey: null,
      currentQuipText: null,
      currentQuipCategory: null,
      lastQuipIndexByCategory: {},
      selectionHistory: [],
      selected: {
        red_offense: null,
        red_defense: null,
        blue_offense: null,
        blue_defense: null,
      },
      score1: null,
      score2: null,
    };

    const READ_PIN_STORAGE_KEY = 'fusball_read_pin';
    const WRITE_PIN_STORAGE_KEY = 'fusball_write_pin';
    const LEGACY_TOKEN_STORAGE_KEY = 'fusball_token';
  const LEADERBOARD_CACHE_STORAGE_KEY = 'fusball_leaderboard_snapshot';

    const QUIPS_BY_CATEGORY = {
      expected_blowout: [
        'Called it. That one came with a warranty.',
        'Spreadsheet said easy and spreadsheet never lies.',
        'Pre-match forecast: pain. Outcome: accurate.',
        'That was not a match, that was a tutorial.',
        'Odds said cruise control and you set autopilot.',
        'Big favorite energy, fully delivered.',
        'You promised fireworks and brought a flamethrower.',
        'That scoreline was signed in advance.',
        'Expected business completed with zero drama.',
        'They queued confidence and shipped dominance.',
      ],
      expected_close_win: [
        'Favorite got the job done, just with extra paperwork.',
        'Predicted edge, sweaty execution.',
        'You won, but the stress meter also won.',
        'Expected W, unexpected cardio session.',
        'Victory arrived exactly on schedule, barely.',
        'That was a controlled burn, mostly controlled.',
        'Odds were right by a hairline margin.',
        'Close call, clean brag rights.',
        'You edged it. Style points pending review.',
        'Win confirmed, blood pressure not confirmed.',
      ],
      upset_win: [
        'Underdog just sent the rankings a breakup text.',
        'Prediction model is filing a formal complaint.',
        'That was theft in broad daylight and on camera.',
        'Upset served hot and with extra spice.',
        'You ignored the odds and wrote your own patch notes.',
        'Favorite status revoked effective immediately.',
        'That scoreboard just heckled the pre-game math.',
        'Underdog mode activated, chaos mode completed.',
        'The script was wrong and you made sure it knew.',
        'Odds got cooked and plated.',
      ],
      nail_biter: [
        'One ball either way and history changes.',
        'That finish was held together by nerves and denial.',
        'Clutch meter just exploded.',
        'Photo finish energy. No survivors.',
        'That was not clean, but it was legendary.',
        'Five-four: the universal language of panic.',
        'Everyone lost years off their lifespan there.',
        'You did not win calmly and that is okay.',
        'Last-ball drama sponsored by pure stubbornness.',
        'Nail-biter certified. Hands still shaking.',
      ],
      total_stomp: [
        'Mercy rule vibes without the mercy.',
        'That scoreline should come with parental guidance.',
        'Clean sweep, zero crumbs left.',
        'You speedran that lobby.',
        'They queued for a game and got a lecture instead.',
        'That was domination with subtitles.',
        'No comeback arc, only credits.',
        'Brutal efficiency and a tiny bit of disrespect.',
        'One side played foosball, the other took notes.',
        'That was an uninstall-level result.',
      ],
      even_match_outcome: [
        'Even odds, uneven confidence by the end.',
        'Coin flip matchup, loaded dice finish.',
        'Fifty-fifty on paper, spicy in practice.',
        'Balanced start, unbalanced bragging rights.',
        'That matchup was level until somebody snapped.',
        'Perfectly even pre-game, perfectly loud post-game.',
        'Model said toss-up, table said throwdown.',
        'Equal ratings, unequal celebrations.',
        'That was parity with extra attitude.',
        'Even matchup resolved by pure audacity.',
      ],
    };

    function formatElapsed(startedAt) {
      if (!startedAt) {
        return '';
      }
      const elapsedMs = Math.max(1000, Date.now() - startedAt);
      if (elapsedMs < 60000) {
        return `${Math.ceil(elapsedMs / 1000)}s`;
      }
      if (elapsedMs < 3600000) {
        return `${Math.ceil(elapsedMs / 60000)}m`;
      }
      return `${Math.ceil(elapsedMs / 3600000)}h`;
    }

    function formatAge(timestampMs) {
      if (!timestampMs) {
        return 'unknown';
      }
      const ageMs = Math.max(0, Date.now() - timestampMs);
      if (ageMs < 60000) {
        return 'just now';
      }
      if (ageMs < 3600000) {
        return `${Math.floor(ageMs / 60000)}m ago`;
      }
      if (ageMs < 86400000) {
        return `${Math.floor(ageMs / 3600000)}h ago`;
      }
      return `${Math.floor(ageMs / 86400000)}d ago`;
    }

    function ensureRequestMeta(key) {
      if (!state.requestState[key]) {
        state.requestState[key] = {
          label: key,
          inFlightAt: null,
          lastSuccessAt: null,
          lastFailureAt: null,
          lastError: '',
        };
      }
      return state.requestState[key];
    }

    function renderOfflineBanner() {
      const banner = document.getElementById('offlineBanner');
      if (!banner) {
        return;
      }
      if (!state.offline) {
        banner.style.display = 'none';
        return;
      }
      banner.style.display = 'block';
      const cacheText = state.leaderboardCacheAt
        ? ` Cached leaderboard age: ${formatAge(state.leaderboardCacheAt)}.`
        : ' Cached leaderboard age is unknown.';
      banner.textContent = `${state.offlineReason || 'API offline.'} Showing leaderboard snapshot only.${cacheText}`;
    }

    function renderLeaderboardFreshness() {
      const node = document.getElementById('leaderboardFreshness');
      if (!node) {
        return;
      }
      const meta = ensureRequestMeta('leaderboard');
      const scopeLabel = state.leaderboardFilter === 'this_month'
        ? 'this month'
        : state.leaderboardFilter === 'this_quarter'
          ? 'this quarter'
        : state.leaderboardFilter === 'this_week'
          ? 'this week'
          : 'all-time';
      if (meta.inFlightAt) {
        node.textContent = `Fetching ${scopeLabel} standings... ${formatElapsed(meta.inFlightAt)} elapsed.`;
        return;
      }
      if (state.offline) {
        if (state.leaderboardCacheAt) {
          node.textContent = `Snapshot mode. Showing cached leaderboard from ${formatAge(state.leaderboardCacheAt)} until the API is reachable again.`;
        } else {
          node.textContent = 'Snapshot mode. No cache age is available yet.';
        }
        return;
      }
      if (meta.lastSuccessAt) {
        const sourceText = state.leaderboardSource === 'server' ? 'from page load' : 'from the live API';
        node.textContent = `Live standings. Updated ${formatAge(meta.lastSuccessAt)} ${sourceText}.`;
        return;
      }
      node.textContent = 'Waiting for the first live leaderboard refresh.';
    }

    function renderLiveStatus() {
      const chip = document.getElementById('liveStatusChip');
      const age = document.getElementById('liveStatusAge');
      const detail = document.getElementById('liveStatusDetail');
      if (!chip || !age || !detail) {
        return;
      }

      const activeRequests = Object.values(state.requestState).filter((meta) => meta.inFlightAt && meta.showInLiveStatus !== false);
      if (activeRequests.length) {
        const current = activeRequests.sort((left, right) => left.inFlightAt - right.inFlightAt)[0];
        const extraCount = activeRequests.length - 1;
        chip.textContent = `Fetching ${current.label}${extraCount > 0 ? ` +${extraCount}` : ''}`;
        chip.className = 'status-chip fetching';
        age.textContent = `In progress for ${formatElapsed(current.inFlightAt)}.`;
        detail.textContent = 'Requests are active. The page will stamp each panel when fresh data lands.';
        return;
      }

      if (state.offline) {
        chip.textContent = 'Snapshot mode';
        chip.className = 'status-chip bad';
        age.textContent = state.lastOfflineAt
          ? `Lost connection ${formatAge(state.lastOfflineAt)}.`
          : 'Connection unavailable.';
        detail.textContent = state.leaderboardCacheAt
          ? `Showing cached leaderboard from ${formatAge(state.leaderboardCacheAt)}. Match entry stays disabled while offline.`
          : 'Match entry stays disabled while offline. No cached leaderboard timestamp is available.';
        return;
      }

      const leaderboardMeta = ensureRequestMeta('leaderboard');
      const presenceMeta = ensureRequestMeta('presence');
      chip.textContent = 'Live';
      chip.className = 'status-chip ok';
      age.textContent = leaderboardMeta.lastSuccessAt
        ? `Leaderboard updated ${formatAge(leaderboardMeta.lastSuccessAt)}.`
        : 'Waiting for the first leaderboard refresh.';
      if (presenceMeta.lastSuccessAt) {
        detail.textContent = `Presence updated ${formatAge(presenceMeta.lastSuccessAt)}. Writes are available.`;
      } else if (state.lastOnlineAt) {
        detail.textContent = `Connection healthy since ${formatAge(state.lastOnlineAt)}. Waiting for active-player data.`;
      } else {
        detail.textContent = 'Connection healthy. Waiting for live data.';
      }
    }

    function beginTrackedRequest(key, label) {
      const meta = ensureRequestMeta(key);
      meta.label = label || meta.label;
      meta.inFlightAt = Date.now();
      meta.lastError = '';
      meta.showInLiveStatus = key !== 'players';
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function completeTrackedRequest(key) {
      const meta = ensureRequestMeta(key);
      meta.inFlightAt = null;
      meta.lastSuccessAt = Date.now();
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function failTrackedRequest(key, errorMessage) {
      const meta = ensureRequestMeta(key);
      meta.inFlightAt = null;
      meta.lastFailureAt = Date.now();
      meta.lastError = errorMessage || 'Request failed.';
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function startFreshnessTicker() {
      if (state.freshnessTimerId) {
        window.clearInterval(state.freshnessTimerId);
      }
      renderOfflineBanner();
      renderLeaderboardFreshness();
      renderLiveStatus();
      state.freshnessTimerId = window.setInterval(() => {
        renderOfflineBanner();
        renderLeaderboardFreshness();
        renderLiveStatus();
        renderPresenceStatus();
        renderOddsStatus();
      }, 1000);
    }

    function seedInitialFreshness() {
      const leaderboardMeta = ensureRequestMeta('leaderboard');
      leaderboardMeta.label = 'leaderboard';
      leaderboardMeta.lastSuccessAt = state.bootedAt;
      state.lastOnlineAt = state.bootedAt;
      renderOfflineBanner();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function setStatus(text, type = '') {
      const node = document.getElementById('statusText');
      if (!node) return;
      node.textContent = text;
      node.className = 'status' + (type ? ' ' + type : '');
    }

    function setAddPlayerStatus(text, type = '') {
      const node = document.getElementById('addPlayerStatus');
      node.textContent = text;
      node.className = 'status' + (type ? ' ' + type : '');
    }

    function cacheLeaderboard(items) {
      try {
        const payload = {
          items: items || [],
          cachedAt: new Date().toISOString(),
          scope: state.leaderboardFilter,
        };
        localStorage.setItem(LEADERBOARD_CACHE_STORAGE_KEY, JSON.stringify(payload));
        state.leaderboardCacheAt = Date.parse(payload.cachedAt);
      } catch {
        // Ignore storage failures on private mode/storage-restricted browsers.
      }
      renderOfflineBanner();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function readCachedLeaderboard() {
      try {
        const raw = localStorage.getItem(LEADERBOARD_CACHE_STORAGE_KEY);
        if (!raw) return { items: [], cachedAt: null, scope: null };
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return { items: parsed, cachedAt: null, scope: null };
        }
        if (parsed && Array.isArray(parsed.items)) {
          return {
            items: parsed.items,
            cachedAt: parsed.cachedAt || null,
            scope: parsed.scope || null,
          };
        }
        return { items: [], cachedAt: null, scope: null };
      } catch {
        return { items: [], cachedAt: null, scope: null };
      }
    }

    function setOfflineMode(reason = 'API offline.') {
      if (state.offline) return;
      state.offline = true;
      state.offlineReason = reason;
      state.lastOfflineAt = Date.now();
      abortInFlightGets();
      document.body.classList.add('offline');
      leaderboardSection.classList.add('active');
      const cached = readCachedLeaderboard();
      if (cached.cachedAt) {
        state.leaderboardCacheAt = Date.parse(cached.cachedAt);
      }
      if (cached.items.length) {
        state.leaderboardSource = 'cache';
        renderLeaderboard(cached.items);
      }
      renderOfflineBanner();
      setStatus('API offline. Match entry is disabled.', 'bad');
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function clearOfflineMode() {
      state.lastOnlineAt = Date.now();
      if (!state.offline) {
        renderLiveStatus();
        return;
      }
      state.offline = false;
      state.offlineReason = '';
      document.body.classList.remove('offline');
      leaderboardSection.classList.toggle('active', state.step === 1);
      renderOfflineBanner();
      setStatus('API online again.', 'ok');
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function abortInFlightGets() {
      for (const controller of state.inFlightGetControllers) {
        controller.abort();
      }
      state.inFlightGetControllers.clear();
    }

    function startHealthMonitor() {
      if (state.healthTimerId) {
        window.clearInterval(state.healthTimerId);
      }

      const check = async () => {
        try {
          const response = await apiFetch('/api/health', {
            allowOffline: true,
            timeoutMs: 1200,
          });
          if (response.ok) {
            clearOfflineMode();
            return;
          }
          setOfflineMode('API offline.');
        } catch {
          setOfflineMode('API offline.');
        }
      };

      check();
      state.healthTimerId = window.setInterval(check, 5000);
    }

    function getStoredReadPin() {
      return (sessionStorage.getItem(READ_PIN_STORAGE_KEY) || '').trim();
    }

    function getStoredWritePin() {
      return (sessionStorage.getItem(WRITE_PIN_STORAGE_KEY) || sessionStorage.getItem(LEGACY_TOKEN_STORAGE_KEY) || '').trim();
    }

    function persistReadPin(pin) {
      const value = (pin || '').trim();
      if (value) {
        sessionStorage.setItem(READ_PIN_STORAGE_KEY, value);
      } else {
        sessionStorage.removeItem(READ_PIN_STORAGE_KEY);
      }
    }

    function persistWritePin(pin) {
      const value = (pin || '').trim();
      if (value) {
        sessionStorage.setItem(WRITE_PIN_STORAGE_KEY, value);
        // Keep legacy key in sync for backward-compatible local runs.
        sessionStorage.setItem(LEGACY_TOKEN_STORAGE_KEY, value);
      } else {
        sessionStorage.removeItem(WRITE_PIN_STORAGE_KEY);
        sessionStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
      }
    }

    function setReadPinInputValue(pin) {
      const input = document.getElementById('readPin');
      if (input) {
        input.value = pin;
      }
    }

    function setWritePinInputValue(pin) {
      const input = document.getElementById('writePin');
      if (input) {
        input.value = pin;
      }
    }

    function clearStoredReadPin() {
      persistReadPin('');
      setReadPinInputValue('');
    }

    function clearStoredWritePin() {
      persistWritePin('');
      setWritePinInputValue('');
    }

    function promptForReadPin(promptMessage = 'Enter read PIN', forcePrompt = false) {
      if (state.readPinPromptPromise) {
        return state.readPinPromptPromise;
      }

      state.readPinPromptPromise = Promise.resolve().then(() => {
        const existing = getStoredReadPin();
        if (existing && !forcePrompt) {
          return existing;
        }

        const entered = (window.prompt(promptMessage) || '').trim();
        if (!entered) {
          return '';
        }
        persistReadPin(entered);
        setReadPinInputValue(entered);
        return entered;
      }).finally(() => {
        state.readPinPromptPromise = null;
      });

      return state.readPinPromptPromise;
    }

    function promptForWritePin(promptMessage = 'Enter writer PIN', forcePrompt = false) {
      let writePin = '';
      const input = document.getElementById('writePin');
      if (!forcePrompt && input) {
        writePin = (input.value || '').trim();
      }
      if (writePin) {
        persistWritePin(writePin);
        return writePin;
      }

      writePin = forcePrompt ? '' : getStoredWritePin();
      if (writePin) {
        setWritePinInputValue(writePin);
        return writePin;
      }

      const entered = (window.prompt(promptMessage) || '').trim();
      if (!entered) {
        return '';
      }
      persistWritePin(entered);
      setWritePinInputValue(entered);
      return entered;
    }

    function ensureWritePin() {
      return promptForWritePin('Enter writer PIN');
    }

    async function retryReadAuth(url, options, suppliedReadPin, suppliedWritePin) {
      if (suppliedReadPin) {
        clearStoredReadPin();
        const enteredReadPin = await promptForReadPin('Incorrect read PIN. Enter read PIN.', true);
        if (enteredReadPin) {
          return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
        }
        return null;
      }

      if (suppliedWritePin) {
        clearStoredWritePin();
        const enteredWritePin = promptForWritePin('Incorrect writer PIN. Enter writer PIN.', true);
        if (enteredWritePin) {
          return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
        }
        return null;
      }

      const enteredReadPin = await promptForReadPin('Enter read PIN', true);
      if (enteredReadPin) {
        return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
      }
      return null;
    }

    function retryWriteAuth(url, options, suppliedWritePin) {
      const promptMessage = suppliedWritePin
        ? 'Incorrect writer PIN. Enter writer PIN.'
        : 'Enter writer PIN';
      if (suppliedWritePin) {
        clearStoredWritePin();
      }
      const enteredWritePin = promptForWritePin(promptMessage, true);
      if (enteredWritePin) {
        return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
      }
      return null;
    }

    async function apiFetch(url, options = {}) {
      const method = (options.method || 'GET').toUpperCase();
      if (state.offline && !options.allowOffline) {
        throw new Error('API offline.');
      }

      const trackKey = options.trackKey || '';
      const startedTracking = !!trackKey && !options.__trackingActive;
      if (startedTracking) {
        beginTrackedRequest(trackKey, options.trackLabel || trackKey);
      }

      const headers = new Headers(options.headers || {});
      const managedToken = window.Clerk && Clerk.session
        ? await Clerk.session.getToken()
        : '';
      if (managedToken) {
        headers.set('Authorization', `Bearer ${managedToken}`);
      }
      const readPin = getStoredReadPin();
      const writePin = getStoredWritePin();
      const suppliedReadPin = !!readPin;
      const suppliedWritePin = !!writePin;
      if (readPin) {
        headers.set('X-Read-Pin', readPin);
      }
      if (writePin) {
        headers.set('X-Write-Pin', writePin);
        headers.set('X-Operator-Token', writePin);
      }

      const timeoutMs = typeof options.timeoutMs === 'number'
        ? options.timeoutMs
        : (method === 'GET' ? 2200 : 5000);
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
      if (method === 'GET') {
        state.inFlightGetControllers.add(controller);
      }

      let trackOutcome = 'pending';

      try {
        const response = await fetch(url, {
          ...options,
          headers,
          signal: controller.signal,
          cache: method === 'GET' ? 'no-store' : options.cache,
        });
        const authRetry = !!options.__authRetry;
        if (AUTH_MODE !== 'clerk' && !managedToken && !authRetry && response.status === 401 && method === 'GET' && !options.allowOffline) {
          const retried = await retryReadAuth(url, options, suppliedReadPin, suppliedWritePin);
          if (retried) {
            trackOutcome = 'success';
            return retried;
          }
        }
        if (AUTH_MODE !== 'clerk' && !managedToken && !authRetry && (response.status === 401 || response.status === 403) && method !== 'GET') {
          const retried = retryWriteAuth(url, options, suppliedWritePin);
          if (retried) {
            trackOutcome = 'success';
            return await retried;
          }
        }
        if (response.status === 503) {
          setOfflineMode('API offline.');
        }
        trackOutcome = 'success';
        return response;
      } catch (error) {
        trackOutcome = 'error';
        if (startedTracking) {
          failTrackedRequest(trackKey, error && error.message ? error.message : 'Request failed.');
        }
        if (error && error.name === 'AbortError') {
          if (state.offline && !options.allowOffline) {
            throw new Error('API offline.');
          }
          throw new Error('Request timed out.');
        }
        setOfflineMode('API offline.');
        throw new Error('API offline.');
      } finally {
        window.clearTimeout(timeoutId);
        if (method === 'GET') {
          state.inFlightGetControllers.delete(controller);
        }
        if (startedTracking && trackOutcome === 'success') {
          completeTrackedRequest(trackKey);
        }
      }
    }

    function setMode(mode) {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      state.mode = mode;
      document.getElementById('modeSingles').classList.toggle('active', mode === 'singles');
      document.getElementById('modeDoubles').classList.toggle('active', mode === 'doubles');
      slotToElement.red_defense.style.opacity = mode === 'doubles' ? '1' : '0.6';
      slotToElement.blue_defense.style.opacity = mode === 'doubles' ? '1' : '0.6';
      if (mode === 'singles') {
        state.selected.red_defense = null;
        state.selected.blue_defense = null;
        if (state.activeSlot === 'red_defense' || state.activeSlot === 'blue_defense') {
          setActiveSlot('red_offense');
        }
      } else {
        setActiveSlot('red_defense');
      }
      document.getElementById('swapRedBtn').disabled = mode === 'singles';
      document.getElementById('swapBlueBtn').disabled = mode === 'singles';
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
      renderPresenceStatus();
    }

    function setActiveSlot(slot) {
      if (state.mode === 'singles' && (slot === 'red_defense' || slot === 'blue_defense')) {
        return;
      }
      state.activeSlot = slot;
      for (const name of slots) {
        slotToElement[name].classList.toggle('active', name === slot);
      }
    }

    function nextEmptySlot() {
      const order = state.mode === 'doubles'
        ? ['red_defense', 'red_offense', 'blue_defense', 'blue_offense']
        : ['red_offense', 'blue_offense'];
      const cur = order.indexOf(state.activeSlot);
      for (let i = cur + 1; i < order.length; i++) {
        if (!state.selected[order[i]]) return order[i];
      }
      for (let i = 0; i < cur; i++) {
        if (!state.selected[order[i]]) return order[i];
      }
      return null;
    }

    function assignPlayer(playerName) {
      if (!state.activePlayers.includes(playerName.toLowerCase())) {
        setStatus(playerName + ' is not marked active.', 'bad');
        return;
      }
      state.selectionHistory.push(JSON.stringify(state.selected));
      for (const slot of slots) {
        if (state.selected[slot] === playerName) {
          state.selected[slot] = null;
        }
      }
      state.selected[state.activeSlot] = playerName;
      renderSlots();
      updateSummary();
      updateReview();
      const next = nextEmptySlot();
      if (next) setActiveSlot(next);
      refreshOdds();
    }

    function undoLastPick() {
      const previous = state.selectionHistory.pop();
      if (!previous) {
        return;
      }
      state.selected = JSON.parse(previous);
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    function swapSides() {
      const next = {
        red_offense: state.selected.blue_offense,
        red_defense: state.selected.blue_defense,
        blue_offense: state.selected.red_offense,
        blue_defense: state.selected.red_defense,
      };
      state.selectionHistory.push(JSON.stringify(state.selected));
      state.selected = next;
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    function swapTeam(team) {
      state.selectionHistory.push(JSON.stringify(state.selected));
      const tmp = state.selected[`${team}_offense`];
      state.selected[`${team}_offense`] = state.selected[`${team}_defense`];
      state.selected[`${team}_defense`] = tmp;
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    function renderSlots() {
      slotToValue.red_offense.textContent = state.selected.red_offense || 'Tap a player';
      slotToValue.red_defense.textContent = state.selected.red_defense || (state.mode === 'doubles' ? 'Tap a player' : 'Optional in singles');
      slotToValue.blue_offense.textContent = state.selected.blue_offense || 'Tap a player';
      slotToValue.blue_defense.textContent = state.selected.blue_defense || (state.mode === 'doubles' ? 'Tap a player' : 'Optional in singles');
    }

    function renderPlayerButtons() {
      const presentPanel = document.getElementById('presentPlayersPanel');
      const awayPanel = document.getElementById('awayPlayersPanel');
      const presentHeading = document.getElementById('presentPlayersHeading');
      const awayHeading = document.getElementById('awayPlayersHeading');
      presentPanel.innerHTML = '';
      awayPanel.innerHTML = '';

      const presentNames = [];
      const awayNames = [];
      for (const name of state.players) {
        const key = name.toLowerCase();
        if (state.activePlayers.includes(key)) {
          presentNames.push(name);
        } else {
          awayNames.push(name);
        }
      }

      for (const name of presentNames) {
        const row = document.createElement('div');
        row.className = 'player-item present-row';
        const assignBtn = document.createElement('button');
        assignBtn.type = 'button';
        assignBtn.className = 'btn small present-player';
        assignBtn.textContent = name;
        assignBtn.addEventListener('click', () => assignPlayer(name));

        const demoteBtn = document.createElement('button');
        demoteBtn.type = 'button';
        demoteBtn.className = 'btn small demote';
        demoteBtn.textContent = '−';
        demoteBtn.title = `Mark ${name} away`;
        demoteBtn.addEventListener('click', () => togglePresence(name, false));

        row.appendChild(assignBtn);
        row.appendChild(demoteBtn);
        presentPanel.appendChild(row);
      }

      for (const name of awayNames) {
        const row = document.createElement('div');
        row.className = 'player-item';
        const activateBtn = document.createElement('button');
        activateBtn.type = 'button';
        activateBtn.className = 'btn small away-player';
        activateBtn.textContent = name;
        activateBtn.addEventListener('click', () => togglePresence(name, true));
        row.appendChild(activateBtn);
        awayPanel.appendChild(row);
      }

      presentHeading.textContent = `Present Players (${presentNames.length}) - tap to assign`;
      awayHeading.textContent = `Away Players (${awayNames.length}) - tap to mark present`;

      if (presentNames.length === 0) {
        presentPanel.innerHTML = "<div class='muted'>No present players yet.</div>";
      }
      if (awayNames.length === 0) {
        awayPanel.innerHTML = "<div class='muted'>No away players.</div>";
      }

      renderPresenceStatus();
    }

    function renderPresenceStatus() {
      const node = document.getElementById('presenceStatus');
      const required = state.mode === 'doubles' ? 4 : 2;
      const meta = ensureRequestMeta('presence');
      let text = `${state.activePlayers.length} active player(s). Need ${required} for ${state.mode}.`;
      if (meta.inFlightAt) {
        text += ` Refreshing active players (${formatElapsed(meta.inFlightAt)}).`;
      } else if (state.offline) {
        text += ' Presence updates are unavailable while offline.';
      } else if (meta.lastSuccessAt) {
        text += ` Updated ${formatAge(meta.lastSuccessAt)}.`;
      }
      node.textContent = text;
      node.className = 'status' + (state.activePlayers.length >= required ? ' ok' : '');
      document.getElementById('randomBtn').disabled = state.activePlayers.length < required;
      document.getElementById('autoBtn').disabled = state.mode !== 'doubles';
    }

    function renderOddsStatus() {
      const node = document.getElementById('oddsText');
      if (!node) {
        return;
      }
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      const meta = ensureRequestMeta('odds');
      if (!redOff || !blueOff) {
        node.textContent = '';
        node.className = 'status';
        return;
      }
      if (meta.inFlightAt) {
        node.textContent = `Calculating odds... ${formatElapsed(meta.inFlightAt)} elapsed.`;
        node.className = 'status';
        return;
      }
      if (!state.latestOdds) {
        if (meta.lastFailureAt) {
          node.textContent = 'Could not load odds for this matchup.';
          node.className = 'status bad';
        } else {
          node.textContent = 'Pick both sides to fetch matchup odds.';
          node.className = 'status';
        }
        return;
      }

      const redPct = Math.round(state.latestOdds.probability * 100);
      const bluePct = 100 - redPct;
      const [favored, favoredPct] = redPct >= 50 ? [redOff + ' side', redPct] : [blueOff + ' side', bluePct];
      const label = oddsLabel(state.latestOdds.probability);
      const upset = hasUpsetRisk(state.latestOdds.probability);
      const badgeHtml = `<span class='badge ${label.cls}'>${label.text}</span>` +
        (upset ? `<span class='badge badge-bad'>Upset Risk</span>` : '') +
        (meta.lastSuccessAt ? `<span class='badge badge-muted'>Updated ${formatAge(meta.lastSuccessAt)}</span>` : '');
      node.innerHTML = `Odds: ${state.latestOdds.ratio} \u2014 ${favored} favored (${favoredPct}%) \u2014 Predicted: ${state.latestOdds.predicted} ${badgeHtml}`;
      node.className = 'status ok';
    }

    function setScore(side, score) {
      if (side === 'red') {
        state.score1 = score;
      } else {
        state.score2 = score;
      }
      renderScoreButtons();
      updateSummary();
      updateReview();
      updateScoreHint();
    }

    function renderScoreButtons() {
      const redPanel = document.getElementById('scoreRed');
      const bluePanel = document.getElementById('scoreBlue');
      redPanel.innerHTML = '';
      bluePanel.innerHTML = '';
      for (let i = 0; i <= 5; i += 1) {
        const redBtn = document.createElement('button');
        redBtn.type = 'button';
        redBtn.className = 'btn score red-team' + (state.score1 === i ? ' active' : '');
        redBtn.textContent = String(i);
        redBtn.addEventListener('click', () => setScore('red', i));
        redPanel.appendChild(redBtn);

        const blueBtn = document.createElement('button');
        blueBtn.type = 'button';
        blueBtn.className = 'btn score blue-team' + (state.score2 === i ? ' active' : '');
        blueBtn.textContent = String(i);
        blueBtn.addEventListener('click', () => setScore('blue', i));
        bluePanel.appendChild(blueBtn);
      }
    }

    function buildPayload() {
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      if (!redOff || !blueOff) {
        throw new Error('Select both offense players first.');
      }

      let team1 = [redOff.toLowerCase()];
      let team2 = [blueOff.toLowerCase()];

      if (state.mode === 'doubles') {
        const redDef = state.selected.red_defense;
        const blueDef = state.selected.blue_defense;
        if (!redDef || !blueDef) {
          throw new Error('Select both defense players for doubles.');
        }
        team1 = [redOff.toLowerCase(), redDef.toLowerCase()];
        team2 = [blueOff.toLowerCase(), blueDef.toLowerCase()];
      }

      if (state.score1 === null || state.score2 === null) {
        throw new Error('Select both scores before submit.');
      }

      return { team1, team2, score1: state.score1, score2: state.score2 };
    }

    function clearSelection() {
      state.selected = {
        red_offense: null,
        red_defense: null,
        blue_offense: null,
        blue_defense: null,
      };
      state.selectionHistory = [];
      state.score1 = null;
      state.score2 = null;
      setActiveSlot(state.mode === 'doubles' ? 'red_defense' : 'red_offense');
      renderSlots();
      renderScoreButtons();
      setStatus('Cleared form.');
      updateSummary();
      updateReview();
      refreshOdds();
      updateScoreHint();
    }

    function displayNameForKey(playerName) {
      const found = state.players.find((candidate) => candidate.toLowerCase() === playerName.toLowerCase());
      return found || playerName;
    }

    async function refreshPresence() {
      if (state.offline) {
        return;
      }
      const response = await apiFetch('/api/presence', {
        trackKey: 'presence',
        trackLabel: 'active players',
      });
      if (!response.ok) {
        throw new Error('Could not load active players.');
      }
      const payload = await response.json();
      state.activePlayers = (payload.items || []).map((name) => name.toLowerCase());
      renderPlayerButtons();
    }

    async function togglePresence(playerName, forceActive = null) {
      const key = playerName.toLowerCase();
      const nextActive = forceActive === null ? !state.activePlayers.includes(key) : !!forceActive;
      const response = await apiFetch('/api/presence', {
        method: 'POST',
        trackKey: 'presence',
        trackLabel: 'active players',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: key, active: nextActive }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.error || 'Could not update active players.', 'bad');
        return;
      }
      await refreshPresence();
      setStatus(`${payload.name} marked ${payload.active ? 'active' : 'away'}.`, 'ok');
    }

    function selectedKeysPayload() {
      return {
        red_offense: state.selected.red_offense ? state.selected.red_offense.toLowerCase() : null,
        red_defense: state.selected.red_defense ? state.selected.red_defense.toLowerCase() : null,
        blue_offense: state.selected.blue_offense ? state.selected.blue_offense.toLowerCase() : null,
        blue_defense: state.selected.blue_defense ? state.selected.blue_defense.toLowerCase() : null,
      };
    }

    function applySelectedFromApi(selected) {
      state.selectionHistory.push(JSON.stringify(state.selected));
      state.selected = {
        red_offense: selected.red_offense ? displayNameForKey(selected.red_offense) : null,
        red_defense: selected.red_defense ? displayNameForKey(selected.red_defense) : null,
        blue_offense: selected.blue_offense ? displayNameForKey(selected.blue_offense) : null,
        blue_defense: selected.blue_defense ? displayNameForKey(selected.blue_defense) : null,
      };
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    async function randomizeLineup() {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      const response = await apiFetch('/api/lineup/random', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: state.mode }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.error || 'Could not build random lineup.', 'bad');
        return;
      }
      applySelectedFromApi(payload.selected || {});
      setStatus('Random lineup assigned from active players.', 'ok');
    }

    async function autoBalanceLineup() {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      if (state.mode !== 'doubles') {
        setStatus('Auto balance is available in doubles mode.', 'bad');
        return;
      }
      const response = await apiFetch('/api/lineup/auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: state.mode, selected: selectedKeysPayload() }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.error || 'Could not auto-balance lineup.', 'bad');
        return;
      }
      applySelectedFromApi(payload.selected || {});
      setStatus('Lineup auto-balanced for best match quality.', 'ok');
    }

    function leaderboardSortValue(row) {
      const s = state.playerStats;
      const k = row.name.toLowerCase();
      if (state.leaderboardSort === 'offense') return Number(row.offense_level || 0);
      if (state.leaderboardSort === 'defense') return Number(row.defense_level || 0);
      if (state.leaderboardSort === 'form') return s && s[k] ? Number(s[k].win_rate || 0) : 0;
      if (state.leaderboardSort === 'streak') return s && s[k] ? Number(s[k].streak || 0) : 0;
      if (state.leaderboardSort === 'improved') return s && s[k] ? Number(s[k].improved || 0) : 0;
      return Number(row.level || 0);
    }

    function leaderboardMetric(row) {
      const s = state.playerStats;
      const k = row.name.toLowerCase();
      if (state.leaderboardSort === 'offense') return String(row.offense_level);
      if (state.leaderboardSort === 'defense') return String(row.defense_level);
      if (state.leaderboardSort === 'form') {
        if (!s || !s[k]) return '\u2014';
        const f = s[k].recent_form_5;
        return f.split('').map(c => `<span class='form-${c.toLowerCase()}'>${c}</span>`).join(' ');
      }
      if (state.leaderboardSort === 'streak') return s && s[k] ? String(s[k].streak) : '\u2014';
      if (state.leaderboardSort === 'improved') {
        if (!s || !s[k]) return '\u2014';
        const v = s[k].improved;
        return `<span class='${v >= 0 ? "delta-pos" : "delta-neg"}'>${v >= 0 ? '+' : ''}${v}</span>`;
      }
      return String(row.level);
    }

    function applyLeaderboardFilter(items) {
      return items;
    }

    function setLeaderboardSort(mode) {
      if (mode === 'improved' && state.leaderboardFilter === 'all') {
        return;
      }
      state.leaderboardSort = mode;
      const ids = ['sortTotalBtn','sortAtkBtn','sortDefBtn','sortFormBtn','sortStreakBtn','sortImprovedBtn'];
      const modes = ['total','offense','defense','form','streak','improved'];
      const headers = ['Total','Offense','Defense','Form','Streak','Improved'];
      ids.forEach((id, i) => document.getElementById(id).classList.toggle('active', modes[i] === mode));
      const hdr = document.getElementById('lbMetricHeader');
      if (hdr) hdr.textContent = headers[modes.indexOf(mode)] || 'Total';
      const hint = document.getElementById('metricHint');
      if (hint) {
        hint.textContent = mode === 'improved'
          ? 'Improved: delta on all-time leaderboard baseline.'
          : '';
      }
      const statsNeeded = ['form','streak','improved'].includes(mode);
      if (statsNeeded && (!state.playerStats || state.playerStatsScope !== state.leaderboardFilter)) {
        fetchLeaderboardStats().catch(() => undefined);
      } else {
        renderLeaderboard(state.leaderboardItems);
      }
    }

    function fetchLeaderboardStats() {
      const requestVersion = state.statsRequestVersion + 1;
      const requestScope = state.leaderboardFilter;
      state.statsRequestVersion = requestVersion;
      return apiFetch('/api/stats?scope=' + encodeURIComponent(state.leaderboardFilter), {
        trackKey: 'stats',
        trackLabel: 'leaderboard stats',
      })
        .then(r => {
          if (!r.ok) {
            throw new Error('Could not load leaderboard stats.');
          }
          return r.json();
        })
        .then(data => {
          if (requestVersion !== state.statsRequestVersion || requestScope !== state.leaderboardFilter) {
            return data;
          }
          state.playerStats = data;
          state.playerStatsScope = requestScope;
          renderLeaderboard(state.leaderboardItems);
          return data;
        });
    }

    function setLeaderboardFilter(f) {
      state.leaderboardFilter = f;
      state.playerStats = null;
      state.playerStatsScope = null;
      document.getElementById('filterAllBtn').classList.toggle('active', f === 'all');
      document.getElementById('filterThisQuarterBtn').classList.toggle('active', f === 'this_quarter');
      document.getElementById('filterThisMonthBtn').classList.toggle('active', f === 'this_month');
      document.getElementById('filterThisWeekBtn').classList.toggle('active', f === 'this_week');

      const improvedBtn = document.getElementById('sortImprovedBtn');
      improvedBtn.disabled = f === 'all';
      if (f === 'all' && state.leaderboardSort === 'improved') {
        setLeaderboardSort('total');
      }

      if (!state.offline) {
        refreshLeaderboard().catch(() => undefined);
      }

      const needsStats = ['form', 'streak', 'improved'].includes(state.leaderboardSort);
      if (needsStats && !state.offline) {
        fetchLeaderboardStats().catch(() => undefined);
      }
    }

    function renderLeaderboard(items) {
      state.leaderboardItems = items || [];
      const body = document.getElementById('leaderboardBody');
      const filtered = applyLeaderboardFilter(state.leaderboardItems);
      if (!filtered || filtered.length === 0) {
        body.innerHTML = "<tr><td colspan='3'>No players found.</td></tr>";
        return;
      }
      const ordered = [...filtered].sort((a, b) => {
        const diff = leaderboardSortValue(b) - leaderboardSortValue(a);
        if (diff !== 0) return diff;
        return Number(a.position || 999) - Number(b.position || 999);
      });
      body.innerHTML = ordered.map((row, idx) => {
        const playerKey = row.name.toLowerCase();
        const metric = leaderboardMetric(row);
        const rank = idx + 1;
        return `<tr class='lrow' onclick='togglePlayerHistory(this, "${playerKey}")'><td>${rank}</td><td><div>${row.name}</div><div class="sub">Off\u00a0${row.offense_level} \u00b7 Def\u00a0${row.defense_level}</div></td><td>${metric}</td></tr>`;
      }).join('');
    }

    function formatSignedDelta(value) {
      const numeric = Number(value || 0);
      const fixed = numeric.toFixed(1);
      return `<span class='${numeric >= 0 ? 'delta-pos' : 'delta-neg'}'>${numeric >= 0 ? '+' : ''}${fixed}</span>`;
    }

    function recentFormText(form) {
      if (!form) return 'No recent form';
      return form.split('').map(ch => ch === 'W' ? `<span class='form-w'>W</span>` : `<span class='form-l'>L</span>`).join(' ');
    }

    function renderProfileOpponentCard(label, item, actionLabel, playerKey) {
      if (!item) {
        return `<div class='profile-card'><div class='label'>${label}</div><div class='value'>No data yet</div></div>`;
      }
      return `<div class='profile-card'>` +
        `<div class='label'>${label}</div>` +
        `<div class='value'>${item.player}</div>` +
        `<div class='subvalue'>${item.wins}-${item.losses}` + (item.draws ? ` (${item.draws}D)` : '') + ` in ${item.matches} match${item.matches === 1 ? '' : 'es'}</div>` +
        (actionLabel
          ? `<div class='subvalue' style='margin-top:8px;'><button class='btn small' type='button' onclick='openPlayerH2H("${playerKey}", "${item.player.toLowerCase()}")'>${actionLabel}</button></div>`
          : '') +
        `</div>`;
    }

    function renderRecentMatches(matches) {
      if (!matches || matches.length === 0) {
        return `<div class='kv'>No matches recorded yet.</div>`;
      }
      return matches.map(match => {
        const result = match.won ? `<span class='form-w'>W</span>` : `<span class='form-l'>L</span>`;
        const date = match.timestamp ? match.timestamp.slice(0, 10) : '?';
        const lineup = `${match.team.join(' + ')} vs ${match.opponents.join(' + ')}`;
        return `<div class='recent-match'>` +
          `<div class='kv'>${result} ${date} <strong>${match.score_for}-${match.score_against}</strong></div>` +
          `<div class='sub'>${lineup}</div>` +
          `<div class='kv'>Off ${formatSignedDelta(match.delta.offense)} Def ${formatSignedDelta(match.delta.defense)}</div>` +
          `</div>`;
      }).join('');
    }

    function renderPlayerProfile(data) {
      const summary = data.summary || {};
      const bestPartner = renderProfileOpponentCard('Best Partner', data.best_partner, '', data.player);
      const toughestOpponent = renderProfileOpponentCard('Toughest Opponent', data.toughest_opponent, 'Open H2H', data.player);
      const streakValue = summary.streak ? `${summary.streak} straight wins` : 'No current streak';
      return `<div class='profile-panel'>` +
        `<div class='profile-header'>` +
          `<div>` +
            `<div class='profile-title'>${displayNameForKey(data.player)}</div>` +
            `<div class='profile-meta'>${summary.wins || 0}-${(summary.games || 0) - (summary.wins || 0)} in ${summary.games || 0} match${summary.games === 1 ? '' : 'es'} · ${Math.round((summary.win_rate || 0) * 100)}% win rate</div>` +
          `</div>` +
          `<div class='profile-meta'>Form ${recentFormText(summary.recent_form_5 || '')}</div>` +
        `</div>` +
        `<div class='profile-cards'>` +
          `<div class='profile-card'><div class='label'>Current Streak</div><div class='value'>${streakValue}</div><div class='subvalue'>Last match ${summary.last_match ? summary.last_match.slice(0, 10) : 'n/a'}</div></div>` +
          bestPartner +
          toughestOpponent +
        `</div>` +
        `<div class='trend-row'>` +
          `<div class='trend-pill'><div class='label'>Offense Trend</div><div class='value'>${formatSignedDelta((data.trend || {}).offense)}</div><div class='subvalue'>Recent matches</div></div>` +
          `<div class='trend-pill'><div class='label'>Defense Trend</div><div class='value'>${formatSignedDelta((data.trend || {}).defense)}</div><div class='subvalue'>Recent matches</div></div>` +
        `</div>` +
        `<div>` +
          `<div style='font-size:0.75rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.04em;'>Recent Matches</div>` +
          renderRecentMatches(data.recent_matches || []) +
        `</div>` +
        `<div class='profile-actions'>` +
          `<button class='btn small' type='button' onclick='setLeaderboardFilter(state.leaderboardFilter)'>Refresh Scope</button>` +
        `</div>` +
      `</div>`;
    }

    function openPlayerH2H(playerKey, otherPlayerKey) {
      setStep(2);
      setMode('singles');
      state.selected.red_offense = displayNameForKey(playerKey);
      state.selected.blue_offense = displayNameForKey(otherPlayerKey);
      state.selected.red_defense = null;
      state.selected.blue_defense = null;
      state.h2hOpen = true;
      renderSlots();
      updateSummary();
      updateReview();
      refreshH2H();
    }

    async function togglePlayerHistory(rowEl, playerKey) {
      if (state.offline) {
        return;
      }
      const nextEl = rowEl.nextElementSibling;
      if (nextEl && nextEl.classList.contains('expand-row')) {
        nextEl.remove();
        if (state.expandedPlayer === playerKey) { state.expandedPlayer = null; return; }
      }
      state.expandedPlayer = playerKey;
      const tr = document.createElement('tr');
      tr.className = 'expand-row';
      const td = document.createElement('td');
      td.colSpan = 3;
      td.className = 'expand-panel';
      td.innerHTML = '<div class="kv">Loading player profile...</div>';
      tr.appendChild(td);
      rowEl.after(tr);
      try {
        const resp = await apiFetch(`/api/player/${encodeURIComponent(playerKey)}/profile?scope=${encodeURIComponent(state.leaderboardFilter)}&recent_limit=5`, {
          trackKey: 'profile',
          trackLabel: 'player profile',
        });
        if (!resp.ok) { td.innerHTML = '<div class="kv">No profile available.</div>'; return; }
        const data = await resp.json();
        td.innerHTML = renderPlayerProfile(data);
      } catch { td.innerHTML = '<div class="kv">Could not load profile.</div>'; }
    }

    function updateSummary() {
      const red = formatTeamDisplay('red');
      const blue = formatTeamDisplay('blue');
      const score = (state.score1 === null || state.score2 === null) ? '?-?' : `${state.score1}-${state.score2}`;
      document.getElementById('summaryText').textContent = `${state.mode.toUpperCase()} | Red: ${red} vs Blue: ${blue} | Score: ${score}`;
      document.getElementById('redScoreLabel').textContent = red;
      document.getElementById('blueScoreLabel').textContent = blue;
      document.getElementById('nextBtn').disabled = !isStepComplete(state.step);
      for (let i = 1; i <= 4; i++) {
        stepButtons[i].disabled = !isStepReachable(i);
      }
    }

    function isStepComplete(step) {
      if (step === 1) return true;
      if (step === 2) {
        if (!state.selected.red_offense || !state.selected.blue_offense) return false;
        if (state.mode === 'doubles' && (!state.selected.red_defense || !state.selected.blue_defense)) return false;
        return true;
      }
      if (step === 3) {
        if (state.score1 === null || state.score2 === null) return false;
        return Math.max(state.score1, state.score2) === 5 && Math.min(state.score1, state.score2) !== 5;
      }
      return true;
    }

    function isStepReachable(step) {
      for (let i = 1; i < step; i++) {
        if (!isStepComplete(i)) return false;
      }
      return true;
    }

    function isFinishedScore(score1, score2) {
      if (score1 === null || score2 === null) {
        return false;
      }
      return Math.max(score1, score2) === 5 && Math.min(score1, score2) !== 5;
    }

    function parsePredictedLosingGoals(predicted) {
      if (!predicted || typeof predicted !== 'string') {
        return null;
      }
      const parts = predicted.split('-').map((value) => Number.parseInt(value, 10));
      if (parts.length !== 2 || Number.isNaN(parts[0]) || Number.isNaN(parts[1])) {
        return null;
      }
      return Math.min(parts[0], parts[1]);
    }

    function classifyQuipCategory(probability, predicted, score1, score2) {
      if (!isFinishedScore(score1, score2)) {
        return null;
      }

      const winnerGoals = Math.max(score1, score2);
      const loserGoals = Math.min(score1, score2);
      const margin = winnerGoals - loserGoals;
      const redFavored = probability >= 0.5;
      const redWon = score1 > score2;
      const upset = redWon !== redFavored;
      const confidence = Math.max(probability, 1 - probability);
      const predictedLosingGoals = parsePredictedLosingGoals(predicted);

      if (winnerGoals === 5 && loserGoals <= 1) {
        return 'total_stomp';
      }
      if (margin === 1) {
        return 'nail_biter';
      }
      if (upset) {
        return 'upset_win';
      }
      if (Math.abs(probability - 0.5) <= 0.06) {
        return 'even_match_outcome';
      }
      if (confidence >= 0.7 && (margin >= 3 || (predictedLosingGoals !== null && loserGoals <= predictedLosingGoals))) {
        return 'expected_blowout';
      }
      return 'expected_close_win';
    }

    function selectQuipForCategory(category) {
      const options = QUIPS_BY_CATEGORY[category] || [];
      if (!options.length) {
        return 'Table speaks louder than predictions.';
      }

      let index = Math.floor(Math.random() * options.length);
      const previous = state.lastQuipIndexByCategory[category];
      if (options.length > 1 && previous === index) {
        index = (index + 1 + Math.floor(Math.random() * (options.length - 1))) % options.length;
      }

      state.lastQuipIndexByCategory[category] = index;
      return options[index];
    }

    function resolveCurrentQuip() {
      if (!state.latestOdds) {
        state.currentQuipKey = null;
        state.currentQuipText = null;
        state.currentQuipCategory = null;
        return null;
      }

      const category = classifyQuipCategory(
        state.latestOdds.probability,
        state.latestOdds.predicted,
        state.score1,
        state.score2,
      );
      if (!category) {
        state.currentQuipKey = null;
        state.currentQuipText = null;
        state.currentQuipCategory = null;
        return null;
      }

      const key = `${category}|${state.latestOdds.predicted}|${state.score1}-${state.score2}`;
      if (state.currentQuipKey === key && state.currentQuipText) {
        return { category: state.currentQuipCategory, text: state.currentQuipText };
      }

      state.currentQuipCategory = category;
      state.currentQuipKey = key;
      state.currentQuipText = selectQuipForCategory(category);
      return { category: category, text: state.currentQuipText };
    }

    function updateScoreHint() {
      const node = document.getElementById('scoreHint');
      if (!node) return;
      if (!state.latestOdds) {
        node.textContent = 'Pick players to see odds and matchup context.';
        return;
      }

      let topLine = `Predicted: ${state.latestOdds.predicted}`;
      if (state.score1 !== null && state.score2 !== null) {
        topLine += `  |  Final: ${state.score1}-${state.score2}`;
      }
      node.innerHTML = '';
      const topNode = document.createElement('div');
      topNode.textContent = topLine;
      node.appendChild(topNode);
      const quip = resolveCurrentQuip();
      if (quip) {
        const quipNode = document.createElement('div');
        quipNode.style.marginTop = '10px';
        const em = document.createElement('em');
        em.textContent = quip.text;
        quipNode.appendChild(em);
        node.appendChild(quipNode);
      }
    }

    function updateReview() {
      const review = document.getElementById('reviewText');
      try {
        const payload = buildPayload();
        const redDisplay = formatTeamDisplay('red', ' + ');
        const blueDisplay = formatTeamDisplay('blue', ' + ');
        const winner = payload.score1 > payload.score2 ? redDisplay : blueDisplay;
        const oddsText = state.latestOdds
          ? `<div><strong>Odds:</strong> ${state.latestOdds.ratio} (${Math.round(state.latestOdds.probability * 100)}% red-side win)</div>`
          : '';
        const quipState = resolveCurrentQuip();
        const quip = quipState
          ? `<div class='review-quip'>${quipState.text}</div>`
          : '';
        review.innerHTML =
          `<div><strong>Red:</strong> ${redDisplay}</div>` +
          `<div><strong>Blue:</strong> ${blueDisplay}</div>` +
          `<div class='review-score'>Final Score: ${payload.score1} - ${payload.score2}</div>` +
          `<div><strong>Winner:</strong> ${winner}</div>` +
          oddsText +
          quip;
      } catch {
        review.textContent = 'Complete lineup and score to enable submit.';
      }
    }

    function teamDisplayMembers(team, placeholder = '?') {
      if (team === 'red') {
        return state.mode === 'doubles'
          ? [state.selected.red_defense || placeholder, state.selected.red_offense || placeholder]
          : [state.selected.red_offense || placeholder];
      }
      return state.mode === 'doubles'
        ? [state.selected.blue_defense || placeholder, state.selected.blue_offense || placeholder]
        : [state.selected.blue_offense || placeholder];
    }

    function formatTeamDisplay(team, separator = ' / ', placeholder = '?') {
      return teamDisplayMembers(team, placeholder).join(separator);
    }

    function setStep(step) {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      const target = Math.max(1, Math.min(step, 4));
      for (let i = 1; i < target; i++) {
        if (!isStepComplete(i)) return;
      }
      state.step = target;
      adminMatchesSection.classList.remove('active');
      adminNavBtn.classList.remove('active');
      for (let i = 1; i <= 4; i += 1) {
        stepButtons[i].classList.toggle('active', i === state.step);
        stepSections[i].classList.toggle('active', i === state.step);
        stepButtons[i].disabled = !isStepReachable(i);
      }
      leaderboardSection.classList.toggle('active', state.step === 1);
      document.getElementById('backBtn').style.visibility = state.step === 1 ? 'hidden' : 'visible';
      document.getElementById('nextBtn').style.display = state.step === 4 ? 'none' : 'inline-block';
      document.getElementById('submitBtn').style.display = state.step === 4 ? 'inline-block' : 'none';
      document.getElementById('nextBtn').disabled = !isStepComplete(state.step);
      if (state.step === 4) {
        updateReview();
      }
    }

    function showAdminView() {
      if (state.offline || !state.isAdmin) {
        return;
      }
      for (let i = 1; i <= 4; i += 1) {
        stepButtons[i].classList.remove('active');
        stepSections[i].classList.remove('active');
      }
      leaderboardSection.classList.remove('active');
      adminMatchesSection.classList.add('active');
      adminNavBtn.classList.add('active');
      document.getElementById('backBtn').style.visibility = 'visible';
      document.getElementById('nextBtn').style.display = 'none';
      document.getElementById('submitBtn').style.display = 'none';
      loadAdminMatches().catch((e) => setAdminMatchesStatus(e.message, 'bad'));
    }

    async function refreshLeaderboard() {
      if (state.offline) {
        const cached = readCachedLeaderboard();
        if (cached.cachedAt) {
          state.leaderboardCacheAt = Date.parse(cached.cachedAt);
        }
        state.leaderboardSource = 'cache';
        renderLeaderboard(cached.items);
        renderLeaderboardFreshness();
        renderLiveStatus();
        return;
      }
      const requestVersion = state.leaderboardRequestVersion + 1;
      const requestScope = state.leaderboardFilter;
      state.leaderboardRequestVersion = requestVersion;
      const response = await apiFetch('/api/leaderboard?limit=50&scope=' + encodeURIComponent(state.leaderboardFilter), {
        trackKey: 'leaderboard',
        trackLabel: 'leaderboard',
      });
      if (!response.ok) {
        throw new Error('Could not refresh leaderboard.');
      }
      const payload = await response.json();
      if (requestVersion !== state.leaderboardRequestVersion || requestScope !== state.leaderboardFilter) {
        return;
      }
      const items = payload.items || [];
      state.leaderboardSource = 'live';
      renderLeaderboard(items);
      cacheLeaderboard(items);
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function predictedScore(prob) {
      const p = prob >= 0.5 ? prob : 1 - prob;
      let loser;
      if (p >= 0.93) loser = 0;
      else if (p >= 0.82) loser = 1;
      else if (p >= 0.70) loser = 2;
      else if (p >= 0.58) loser = 3;
      else loser = 4;
      return prob >= 0.5 ? `5-${loser}` : `${loser}-5`;
    }

    function oddsLabel(prob) {
      const p = Math.max(prob, 1 - prob);
      if (p >= 0.70) return { text: 'Strong Fav', cls: 'badge-accent' };
      if (p >= 0.55) return { text: 'Favorite', cls: 'badge-ok' };
      return { text: 'Even', cls: 'badge-muted' };
    }

    function hasUpsetRisk(prob) {
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      if (!redOff || !blueOff || !state.leaderboardItems.length) return false;
      const ri = state.leaderboardItems.find(r => r.name.toLowerCase() === redOff.toLowerCase());
      const bi = state.leaderboardItems.find(r => r.name.toLowerCase() === blueOff.toLowerCase());
      if (!ri || !bi) return false;
      const redPos = Number(ri.position);
      const bluePos = Number(bi.position);
      return (redPos > bluePos && prob > 0.52) || (bluePos > redPos && prob < 0.48);
    }

    function refreshH2H() {
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      const redDef = state.selected.red_defense;
      const blueDef = state.selected.blue_defense;
      const card = document.getElementById('h2hCard');
      const toggleRow = document.getElementById('h2hToggleRow');
      if (!redOff || !blueOff) {
        toggleRow.style.display = 'none';
        card.classList.remove('open');
        return;
      }
      toggleRow.style.display = '';
      if (!state.h2hOpen) return;
      card.innerHTML = '<span class="muted">Loading head-to-head...</span>';
      if (state.mode === 'doubles' && redDef && blueDef) {
        const redTeamDisplay = `${redDef} + ${redOff}`;
        const blueTeamDisplay = `${blueDef} + ${blueOff}`;
        const team1 = `${encodeURIComponent(redOff.toLowerCase())},${encodeURIComponent(redDef.toLowerCase())}`;
        const team2 = `${encodeURIComponent(blueOff.toLowerCase())},${encodeURIComponent(blueDef.toLowerCase())}`;
        apiFetch(`/api/team-h2h?team1=${team1}&team2=${team2}`, {
          trackKey: 'h2h',
          trackLabel: 'head-to-head',
        })
          .then(r => r.json())
          .then(data => {
            if (data.matches === 0) {
              card.innerHTML = `<div class='profile-meta' style='margin-bottom:8px;'>Current teams H2H</div>` +
                `<div class='h2h-pair'><div class='kv'><strong>${redTeamDisplay}</strong> vs <strong>${blueTeamDisplay}</strong></div>` +
                `<div class='sub'>No recorded doubles matches for this exact lineup order yet.</div></div>`;
              return;
            }
            const last = data.last_match ? data.last_match.slice(0, 10) : '?';
            card.innerHTML = `<div class='profile-meta' style='margin-bottom:8px;'>Current teams H2H</div>` +
              `<div class='h2h-pair'>` +
              `<div class='kv'><strong>${redTeamDisplay}</strong> ${data.team1_wins}\u2013${data.team2_wins} <strong>${blueTeamDisplay}</strong>${data.draws ? ` (${data.draws}D)` : ''}</div>` +
              `<div class='sub'>${data.matches} match${data.matches === 1 ? '' : 'es'} · last ${last}</div>` +
              `</div>`;
          })
          .catch(() => { card.innerHTML = '<span class="muted">Could not load H2H data.</span>'; });
        return;
      }

      apiFetch(`/api/h2h?p1=${encodeURIComponent(redOff.toLowerCase())}&p2=${encodeURIComponent(blueOff.toLowerCase())}`, {
        trackKey: 'h2h',
        trackLabel: 'head-to-head',
      })
        .then(r => r.json())
        .then(data => {
          if (data.matches === 0) {
            card.innerHTML = '<span class="muted">No recorded matches between these players yet.</span>';
            return;
          }
          const last = data.last_match ? data.last_match.slice(0, 10) : '?';
          card.innerHTML = `<div class='profile-meta' style='margin-bottom:8px;'>Head-to-head</div>` +
            `<div class='h2h-pair'>` +
            `<div class='kv'><strong>${redOff}</strong> ${data.p1_wins}\u2013${data.p2_wins} <strong>${blueOff}</strong>${data.draws ? ` (${data.draws}D)` : ''}</div>` +
            `<div class='sub'>${data.matches} match${data.matches === 1 ? '' : 'es'} · last ${last}</div>` +
            `</div>`;
        })
        .catch(() => { card.innerHTML = '<span class="muted">Could not load H2H data.</span>'; });
    }

    function toggleH2H() {
      state.h2hOpen = !state.h2hOpen;
      const card = document.getElementById('h2hCard');
      const btn = document.getElementById('h2hToggleBtn');
      card.classList.toggle('open', state.h2hOpen);
      btn.textContent = state.h2hOpen ? 'H2H \u25b4' : 'H2H \u25be';
      if (state.h2hOpen) refreshH2H();
    }

    async function refreshOdds() {
      if (state.offline) {
        return;
      }
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      if (!redOff || !blueOff) {
        state.latestOdds = null;
        renderOddsStatus();
        updateScoreHint();
        refreshH2H();
        return;
      }
      renderOddsStatus();
      const params = new URLSearchParams({ red_off: redOff.toLowerCase(), blue_off: blueOff.toLowerCase(), mode: state.mode });
      if (state.mode === 'doubles') {
        if (state.selected.red_defense) params.set('red_def', state.selected.red_defense.toLowerCase());
        if (state.selected.blue_defense) params.set('blue_def', state.selected.blue_defense.toLowerCase());
      }
      try {
        const resp = await apiFetch('/api/odds?' + params.toString(), {
          trackKey: 'odds',
          trackLabel: 'odds',
        });
        if (!resp.ok) {
          state.latestOdds = null;
          renderOddsStatus();
          updateScoreHint();
          return;
        }
        const data = await resp.json();
        const score = predictedScore(data.probability);
        state.latestOdds = { probability: data.probability, ratio: data.ratio, predicted: score };
        renderOddsStatus();
        updateScoreHint();
        refreshH2H();
      } catch {
        state.latestOdds = null;
        renderOddsStatus();
        updateScoreHint();
      }
    }

    async function loadPlayers() {
      const response = await apiFetch('/api/players', {
        trackKey: 'players',
        trackLabel: 'player list',
      });
      if (!response.ok) {
        throw new Error('Could not load players.');
      }
      const payload = await response.json();
      state.players = (payload.items || []).slice().sort((left, right) => left.localeCompare(right));
      renderPlayerButtons();
    }

    async function submitMatch() {
      if (state.isSubmitting) {
        setStatus('Submission already in progress...', 'bad');
        return;
      }

      const writePin = AUTH_MODE === 'clerk' || (window.Clerk && Clerk.session)
        ? 'managed-session'
        : ensureWritePin();
      if (!writePin) {
        setStatus('Enter writer PIN first.', 'bad');
        return;
      }

      let payload;
      try {
        payload = buildPayload();
      } catch (error) {
        setStatus(error.message, 'bad');
        return;
      }

      state.isSubmitting = true;
      const submitBtn = document.getElementById('submitBtn');
      const originalSubmitLabel = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';
      setStatus('Submitting result...');

      try {
        const idempotencyKey = window.crypto && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const response = await apiFetch('/api/matches', {
          method: 'POST',
          trackKey: 'submit',
          trackLabel: 'match submit',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': idempotencyKey,
          },
          body: JSON.stringify(payload),
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          setStatus(result.error || 'Submit failed.', 'bad');
          return;
        }

        setStatus('Result submitted. Leaderboard refreshed.', 'ok');
        await refreshLeaderboard();
        setStep(2);
      } finally {
        state.isSubmitting = false;
        submitBtn.disabled = false;
        submitBtn.textContent = originalSubmitLabel;
      }
    }

    async function addPlayer() {
      const writePin = AUTH_MODE === 'clerk' || (window.Clerk && Clerk.session)
        ? 'managed-session'
        : ensureWritePin();
      if (!writePin) {
        setAddPlayerStatus('Writer PIN is required to add players.', 'bad');
        return;
      }

      const input = document.getElementById('newPlayerName');
      const name = input.value.trim();
      if (!name) {
        setAddPlayerStatus('Enter a player name.', 'bad');
        return;
      }

      setAddPlayerStatus('Adding player...');
      const response = await apiFetch('/api/players', {
        method: 'POST',
        trackKey: 'players',
        trackLabel: 'player add',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name }),
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        setAddPlayerStatus(result.error || 'Could not add player.', 'bad');
        return;
      }

      input.value = '';
      setAddPlayerStatus(`Added ${result.name}.`, 'ok');
      await loadPlayers();
      await refreshPresence();
      await refreshLeaderboard();
    }

    function storedTeamDisplay(team) {
      const names = Array.isArray(team) ? team : [];
      return (names.length === 2 ? [names[1], names[0]] : names).join(' + ');
    }

    function renderAdminMatches() {
      const container = document.getElementById('adminMatchesList');
      container.replaceChildren();
      for (const match of state.adminMatches) {
        const card = document.createElement('div');
        card.className = 'review-card';
        const title = document.createElement('strong');
        title.textContent = `${storedTeamDisplay(match.team1)} ${match.score1}-${match.score2} ${storedTeamDisplay(match.team2)}`;
        const details = document.createElement('div');
        details.className = 'muted';
        details.textContent = `${match.status} · version ${match.version} · ${match.timestamp} · by ${match.submitted_by || 'unknown'}`;
        const latestEvent = (match.events || []).slice(-1)[0];
        const audit = document.createElement('div');
        audit.className = 'muted';
        audit.textContent = latestEvent && latestEvent.reason
          ? `Latest reason: ${latestEvent.reason}`
          : 'No correction reason recorded.';
        const button = document.createElement('button');
        button.className = 'btn small';
        button.type = 'button';
        button.textContent = match.status === 'active' ? 'Void match' : 'Restore match';
        button.addEventListener('click', () => {
          changeAdminMatchStatus(match).catch((error) => {
            setAdminMatchesStatus(error.message, 'bad');
          });
        });
        card.append(title, details, audit, button);
        container.appendChild(card);
      }
    }

    function setAdminMatchesStatus(message, kind = '') {
      const element = document.getElementById('adminMatchesStatus');
      element.textContent = message;
      element.className = `status ${kind}`.trim();
    }

    async function loadAdminMatches() {
      const response = await apiFetch('/api/admin/matches?limit=30', {
        trackKey: 'admin-matches',
        trackLabel: 'admin matches',
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || 'Could not load match corrections.');
      }
      state.adminMatches = payload.items || [];
      renderAdminMatches();
      setAdminMatchesStatus(`${state.adminMatches.length} matches loaded.`, 'ok');
    }

    async function changeAdminMatchStatus(match) {
      const action = match.status === 'active' ? 'void' : 'restore';
      const reason = window.prompt(`Reason to ${action} this match:`, '');
      if (!reason || reason.trim().length < 3) {
        setAdminMatchesStatus('A reason of at least 3 characters is required.', 'bad');
        return;
      }
      if (!window.confirm(`${action === 'void' ? 'Void' : 'Restore'} this match and recalculate rankings?`)) {
        return;
      }
      const requestId = window.crypto && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const response = await apiFetch(`/api/admin/matches/${encodeURIComponent(match.id)}/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': requestId,
        },
        body: JSON.stringify({
          reason: reason.trim(),
          expected_version: match.version,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || `Could not ${action} match.`);
      }
      setAdminMatchesStatus(`Match ${action === 'void' ? 'voided' : 'restored'}.`, 'ok');
      state.playerStats = null;
      state.playerStatsScope = null;
      state.expandedPlayer = null;
      await Promise.all([
        loadAdminMatches(),
        refreshLeaderboard(),
        fetchLeaderboardStats(),
        loadPlayers(),
      ]);
      refreshH2H();
      refreshOdds();
    }

    document.getElementById('modeSingles').addEventListener('click', () => setMode('singles'));
    document.getElementById('modeDoubles').addEventListener('click', () => setMode('doubles'));
    document.getElementById('slotRedOff').addEventListener('click', () => setActiveSlot('red_offense'));
    document.getElementById('slotRedDef').addEventListener('click', () => setActiveSlot('red_defense'));
    document.getElementById('slotBlueOff').addEventListener('click', () => setActiveSlot('blue_offense'));
    document.getElementById('slotBlueDef').addEventListener('click', () => setActiveSlot('blue_defense'));
    document.getElementById('swapSidesBtn').addEventListener('click', swapSides);
    document.getElementById('swapRedBtn').addEventListener('click', () => swapTeam('red'));
    document.getElementById('swapBlueBtn').addEventListener('click', () => swapTeam('blue'));
    document.getElementById('randomBtn').addEventListener('click', () => randomizeLineup().catch((e) => setStatus(e.message, 'bad')));
    document.getElementById('autoBtn').addEventListener('click', () => autoBalanceLineup().catch((e) => setStatus(e.message, 'bad')));
    document.getElementById('undoBtn').addEventListener('click', undoLastPick);
    document.getElementById('clearBtn').addEventListener('click', clearSelection);
    document.getElementById('sortTotalBtn').addEventListener('click', () => setLeaderboardSort('total'));
    document.getElementById('sortAtkBtn').addEventListener('click', () => setLeaderboardSort('offense'));
    document.getElementById('sortDefBtn').addEventListener('click', () => setLeaderboardSort('defense'));
    document.getElementById('sortFormBtn').addEventListener('click', () => setLeaderboardSort('form'));
    document.getElementById('sortStreakBtn').addEventListener('click', () => setLeaderboardSort('streak'));
    document.getElementById('sortImprovedBtn').addEventListener('click', () => setLeaderboardSort('improved'));
    document.getElementById('filterAllBtn').addEventListener('click', () => setLeaderboardFilter('all'));
    document.getElementById('filterThisQuarterBtn').addEventListener('click', () => setLeaderboardFilter('this_quarter'));
    document.getElementById('filterThisMonthBtn').addEventListener('click', () => setLeaderboardFilter('this_month'));
    document.getElementById('filterThisWeekBtn').addEventListener('click', () => setLeaderboardFilter('this_week'));
    document.getElementById('addPlayerBtn').addEventListener('click', () => addPlayer().catch((e) => setAddPlayerStatus(e.message, 'bad')));
    document.getElementById('newPlayerName').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addPlayer().catch((err) => setAddPlayerStatus(err.message, 'bad'));
      }
    });
    document.getElementById('nextBtn').addEventListener('click', () => setStep(state.step + 1));
    document.getElementById('backBtn').addEventListener('click', () => setStep(state.step - 1));
    document.getElementById('submitBtn').addEventListener('click', () => submitMatch().catch((e) => setStatus(e.message, 'bad')));
    stepButtons[1].addEventListener('click', () => setStep(1));
    stepButtons[2].addEventListener('click', () => setStep(2));
    stepButtons[3].addEventListener('click', () => setStep(3));
    stepButtons[4].addEventListener('click', () => setStep(4));
    adminNavBtn.addEventListener('click', showAdminView);

    const readPinInput = document.getElementById('readPin');
    const writePinInput = document.getElementById('writePin');
    const savedReadPin = getStoredReadPin();
    const savedWritePin = getStoredWritePin();
    if (savedReadPin) {
      readPinInput.value = savedReadPin;
    }
    if (savedWritePin) {
      writePinInput.value = savedWritePin;
    }
    readPinInput.addEventListener('input', () => {
      persistReadPin(readPinInput.value);
    });
    writePinInput.addEventListener('input', () => {
      persistWritePin(writePinInput.value);
    });

    async function initializeManagedAuth() {
      if (AUTH_MODE === 'legacy') {
        return { proceed: true };
      }
      document.getElementById('managedAuthPanel').style.display = '';
      document.getElementById('legacyAuthPanel').style.display =
        AUTH_MODE === 'hybrid' ? '' : 'none';
      if (!window.Clerk) {
        throw new Error('Managed sign-in failed to load.');
      }
      await Clerk.load({ ui: { ClerkUI: window.__internal_ClerkUICtor } });
      const status = document.getElementById('managedAuthStatus');
      if (Clerk.isSignedIn) {
        Clerk.mountUserButton(document.getElementById('clerkUserButton'));
        status.textContent = 'Signed in with managed identity.';
        if (AUTH_MODE === 'clerk') {
          appContent.style.display = '';
          stickyBar.style.display = '';
        }
        const identityResponse = await apiFetch('/api/auth/me', {
          allowOffline: true,
        });
        if (identityResponse.ok) {
          const identity = await identityResponse.json();
          if (identity.role === 'admin') {
            state.isAdmin = true;
            adminNavBtn.style.display = 'inline-block';
            await loadAdminMatches();
          }
        }
        return { proceed: true };
      }
      Clerk.mountSignIn(document.getElementById('clerkSignIn'));
      status.textContent = AUTH_MODE === 'hybrid'
        ? 'Sign in, or use transition PINs below.'
        : 'Sign in to use Fusball.';
      if (AUTH_MODE === 'clerk') {
        appContent.style.display = 'none';
        stickyBar.style.display = 'none';
        return { proceed: false };
      }
      return { proceed: true };
    }

    window.addEventListener('load', async () => {
      let authResult = { proceed: true };
      try {
        authResult = await initializeManagedAuth();
      } catch (error) {
        setStatus(error.message, 'bad');
        if (AUTH_MODE === 'clerk') {
          appContent.style.display = 'none';
          stickyBar.style.display = 'none';
          return;
        }
      }
      if (!authResult.proceed) {
        return;
      }
      setMode('singles');
      setActiveSlot('red_offense');
      seedInitialFreshness();
      startFreshnessTicker();
      renderScoreButtons();
      renderSlots();
      updateSummary();
      updateReview();
      updateScoreHint();
      setLeaderboardFilter('all');
      loadPlayers()
        .then(() => refreshPresence())
        .catch((e) => setStatus(e.message, 'bad'));
      startHealthMonitor();
    });
