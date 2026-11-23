(() => {
  const viewLogin = document.getElementById('view-login');
  const viewStudio = document.getElementById('view-studio');
  const sessionStatus = document.getElementById('sessionStatus');
  const sessionHint = document.getElementById('sessionHint');
  const loginForm = document.getElementById('loginForm');
  const loginErr = document.getElementById('loginErr');
  const authLine = document.getElementById('authLine');
  const cacheLine = document.getElementById('cacheLine');
  const netStatus = document.getElementById('netStatus');

  const list = document.getElementById('reporterList');
  const emptyHint = document.getElementById('emptyHint');
  const listenStatus = document.getElementById('listenStatus');
  const btnStop = document.getElementById('btnStop');
  const btnLogout = document.getElementById('btnLogout');
  const btnSync = document.getElementById('btnSync');
  const audioMix = document.getElementById('audioMix');
  const err = document.getElementById('err');
  const autoModeEl = document.getElementById('autoMode');
  const studioTimerEl = document.getElementById('studioTimer');

  let cfg = null;
  let maxMix = 3;
  let autoMode = Number(sessionStorage.getItem('tt_studio_auto') || '3');
  if (![0, 1, 3].includes(autoMode)) autoMode = 3;

  /** @type {Map<string, any>} */
  const channels = new Map();
  /** @type {Map<string, {muted:boolean, volume:number}>} */
  const mixPrefs = new Map();
  let listTimer = 0;
  let clockTimer = 0;
  let netTimer = 0;
  let autoBusy = false;
  let lastRows = [];
  let studioOpenedAt = Date.now();
  let keepAlive = null;
  let kickBusy = false;
  let syncBusy = false;
  let networkOk = false;
  let onlineStatusAvailable = false;
  let fromCache = false;
  let offlineSession = false;

  function showErr(msg) {
    err.hidden = !msg;
    err.textContent = msg || '';
  }

  function showLoginErr(msg) {
    loginErr.hidden = !msg;
    loginErr.textContent = msg || '';
  }

  function formatCacheTime(ts) {
    const n = Number(ts) || 0;
    if (!n) return '';
    try {
      return new Date(n * 1000).toLocaleString('fr-FR');
    } catch (_) {
      return '';
    }
  }

  function setNetPill() {
    if (!netStatus) return;
    if (onlineStatusAvailable && networkOk) {
      netStatus.textContent = 'Réseau OK — statut live';
      netStatus.className = 'pill is-live';
    } else if (fromCache || offlineSession) {
      netStatus.textContent = 'Hors ligne — liste cache';
      netStatus.className = 'pill is-offline';
    } else {
      netStatus.textContent = 'Réseau indisponible';
      netStatus.className = 'pill is-offline';
    }
  }

  function setCacheLine(extra) {
    if (!cacheLine) return;
    const parts = [];
    if (offlineSession) parts.push('Session régie ouverte hors ligne (cache local)');
    if (fromCache) parts.push('Liste reporteurs depuis le cache local');
    if (extra) parts.push(extra);
    if (!onlineStatusAvailable) {
      parts.push('Statut en ligne indisponible sans réseau (internet ou LAN) + app téléphone');
    }
    cacheLine.textContent = parts.join(' · ');
  }

  function showStudio(auth, opts) {
    offlineSession = !!(opts && opts.offline);
    viewLogin.hidden = true;
    viewStudio.hidden = false;
    authLine.textContent = auth && auth.displayName
      ? ('Connecté : ' + auth.displayName + (offlineSession ? ' (hors ligne)' : ''))
      : (offlineSession ? 'Session régie (cache hors ligne)' : 'Session régie active');
    bootStudio();
    if (window.TTRadio && typeof window.TTRadio.boot === 'function') {
      window.TTRadio.boot();
    }
  }

  async function fetchNetworkStatus() {
    try {
      const res = await fetch('/network/status', { cache: 'no-store' });
      const data = await res.json();
      networkOk = !!data.network;
      onlineStatusAvailable = !!data.online_status_available;
      return data;
    } catch (_) {
      networkOk = false;
      onlineStatusAvailable = false;
      return { network: false, online_status_available: false };
    }
  }

  async function authCheck() {
    sessionStatus.textContent = 'Recherche d’une session régie (locale ou navigateur)…';
    if (sessionHint) sessionHint.hidden = false;
    const res = await fetch('/auth/check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    const data = await res.json();
    networkOk = !!data.network;
    if (data.ok && data.auth && data.auth.studio) {
      const src = data.source || 'session';
      const who = data.auth.displayName || 'admin';
      if (data.offline) {
        sessionStatus.textContent = 'Hors ligne — session cache (' + who + ') — ouverture…';
      } else {
        const label = src.indexOf('browser:') === 0
          ? ('Session ' + src.replace('browser:', '') + ' trouvée (' + who + ') — ouverture…')
          : ('Session app trouvée (' + who + ') — ouverture…');
        sessionStatus.textContent = label;
      }
      if (sessionHint) sessionHint.hidden = true;
      showStudio(data.auth || {}, { offline: !!data.offline });
      return;
    }
    if (sessionHint) sessionHint.hidden = false;
    if (data.auth && data.auth.loggedIn) {
      sessionStatus.textContent = data.error || 'Session navigateur trouvée, mais sans droit régie.';
    } else {
      sessionStatus.textContent = data.error || 'Aucune session admin ouverte. Connectez-vous ci-dessous.';
    }
  }

  loginForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    showLoginErr('');
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    const btn = document.getElementById('btnLogin');
    btn.disabled = true;
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Connexion refusée');
      showStudio(data.auth || {}, { offline: false });
    } catch (e) {
      showLoginErr(e.message || 'Erreur de connexion');
    } finally {
      btn.disabled = false;
    }
  });

  btnLogout.addEventListener('click', async () => {
    await stopAll().catch(() => {});
    await fetch('/auth/logout', { method: 'POST', body: '{}' });
    location.reload();
  });

  btnSync.addEventListener('click', () => {
    syncReporters(true).catch((e) => showErr(e.message));
  });

  // —— Régie (adapté de studio.js) ——
  function setListen(text, cls) {
    listenStatus.textContent = text;
    listenStatus.className = 'pill' + (cls ? ' ' + cls : '');
  }
  function autoLimit() {
    if (autoMode <= 0) return 0;
    return Math.min(autoMode, maxMix);
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }
  function getMixPref(id) {
    if (!mixPrefs.has(id)) mixPrefs.set(id, { muted: false, volume: 1 });
    return mixPrefs.get(id);
  }
  function applyChannelAudio(ch) {
    if (!ch || !ch.audio) return;
    ch.audio.muted = !!ch.muted;
    ch.audio.volume = Math.max(0, Math.min(1, Number(ch.volume) || 0));
  }
  function paintMeter(ch) {
    if (!ch) return;
    if (ch.meterBar) ch.meterBar.style.width = (Number(ch.level) || 0) + '%';
    if (ch.waveBars && ch.bands) {
      for (let i = 0; i < ch.waveBars.length; i++) {
        ch.waveBars[i].style.height = Math.max(8, Number(ch.bands[i]) || 0) + '%';
      }
    }
  }
  function attachRemoteMeter(ch, stream) {
    if (!ch || !stream || !TtDirect.createStreamMeter) return;
    try { if (ch.streamMeter) ch.streamMeter.stop(); } catch (_) {}
    ch.remoteStream = stream;
    ch.level = 0;
    ch.bands = new Array(16).fill(0);
    ch.streamMeter = TtDirect.createStreamMeter(stream, (lvl) => {
      ch.level = lvl; paintMeter(ch);
    }, (bands) => {
      ch.bands = bands; paintMeter(ch);
    });
  }

  function tickStudioClock() {
    const openFor = (Date.now() - studioOpenedAt) / 1000;
    let html = 'Régie ouverte : <strong>' + TtDirect.formatDuration(openFor) + '</strong>';
    if (channels.size) {
      const parts = [...channels.values()].map((ch) => escapeHtml(ch.name) + ' ' + TtDirect.formatDuration((Date.now() - ch.listenStartedAt) / 1000));
      html += ' · Mix : ' + parts.join(' · ');
    }
    studioTimerEl.innerHTML = html;
  }

  function updateStatus() {
    const n = channels.size;
    btnStop.hidden = n === 0;
    const modeLabel = autoMode === 0 ? 'manuel' : ('auto ' + autoMode);
    if (n === 0) setListen('En attente — ' + modeLabel);
    else if (n === 1) setListen('Écoute : ' + [...channels.values()][0].name, 'is-live');
    else setListen('Mix : ' + n + ' reporters', 'is-live');
    tickStudioClock();
    setNetPill();
  }

  function presenceLabel(r) {
    if (!onlineStatusAvailable || r.presence_unknown) {
      return 'présence inconnue (pas de réseau)';
    }
    if (r.online === false && !(r.online_for > 0)) {
      return 'hors ligne';
    }
    return 'en ligne ' + TtDirect.formatDuration(r.online_for || 0);
  }

  function renderList(rows) {
    lastRows = rows;
    list.innerHTML = '';
    emptyHint.hidden = rows.length > 0;
    if (!rows.length) {
      emptyHint.textContent = fromCache || !networkOk
        ? 'Aucun reporteur en cache. Connectez le PC et lancez « Sync reporteurs ».'
        : 'Aucun reporter en ligne pour le moment.';
    }
    rows.forEach((r) => {
      const li = document.createElement('li');
      li.className = 'reporter-card';
      const active = channels.has(r.id);
      const ch = active ? channels.get(r.id) : null;
      const pref = getMixPref(r.id);
      const presenceUnknown = !onlineStatusAvailable || !!r.presence_unknown;

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'reporter-main' + (active ? ' is-active' : '') + (presenceUnknown ? ' is-unknown' : '');
      let meta = presenceLabel(r);
      if (active) meta += ' · antenne ' + TtDirect.formatDuration(ch ? (Date.now() - ch.listenStartedAt) / 1000 : (r.listen_for || 0));
      btn.innerHTML = '<strong>' + escapeHtml(r.name) + '</strong><span class="meta">' + meta + '</span>'
        + (active ? '<span class="badge">À l’antenne</span>' : '');
      btn.addEventListener('click', () => {
        if (autoMode > 0 && !active) return;
        if (!onlineStatusAvailable) {
          showErr('Écoute live impossible hors réseau. Connectez le PC (internet ou LAN).');
          return;
        }
        toggleReporter(r);
      });
      li.appendChild(btn);

      if (active && ch) {
        const controls = document.createElement('div');
        controls.className = 'reporter-controls';
        const muteBtn = document.createElement('button');
        muteBtn.type = 'button';
        muteBtn.className = 'btn ghost btn-compact';
        muteBtn.textContent = ch.muted ? 'Muet' : 'Couper';
        muteBtn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          ch.muted = !ch.muted;
          pref.muted = ch.muted;
          applyChannelAudio(ch);
          renderList(lastRows);
        });
        const volLabel = document.createElement('label');
        volLabel.className = 'vol-label';
        volLabel.innerHTML = '<span>Volume</span>';
        const vol = document.createElement('input');
        vol.type = 'range'; vol.min = '0'; vol.max = '100';
        vol.value = String(Math.round((ch.volume ?? 1) * 100));
        vol.addEventListener('input', () => {
          const v = Number(vol.value) / 100;
          ch.volume = v; pref.volume = v;
          if (v > 0 && ch.muted) { ch.muted = false; pref.muted = false; }
          applyChannelAudio(ch);
        });
        volLabel.appendChild(vol);
        const meterWrap = document.createElement('div');
        meterWrap.className = 'ch-meters';
        meterWrap.innerHTML = '<div class="ch-wave"></div><div class="meter"><span class="ch-meter-bar"></span></div>';
        const waveEl = meterWrap.querySelector('.ch-wave');
        const bars = [];
        for (let i = 0; i < 16; i++) {
          const b = document.createElement('span');
          b.className = 'ch-wave-bar';
          waveEl.appendChild(b);
          bars.push(b);
        }
        ch.meterWrap = meterWrap;
        ch.meterBar = meterWrap.querySelector('.ch-meter-bar');
        ch.waveBars = bars;
        if (ch.remoteStream && !ch.streamMeter) attachRemoteMeter(ch, ch.remoteStream);
        paintMeter(ch);
        controls.appendChild(muteBtn);
        controls.appendChild(volLabel);
        controls.appendChild(meterWrap);
        li.appendChild(controls);
      }

      if (onlineStatusAvailable) {
        const kickBtn = document.createElement('button');
        kickBtn.type = 'button';
        kickBtn.className = 'btn ghost btn-compact';
        kickBtn.textContent = 'Terminer';
        kickBtn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          kickReporter(r).catch((e) => showErr(e.message));
        });
        li.appendChild(kickBtn);
      }
      list.appendChild(li);
    });
  }

  async function kickReporter(r) {
    if (!r || !r.id || kickBusy) return;
    if (!onlineStatusAvailable) {
      showErr('Action impossible hors réseau.');
      return;
    }
    if (!window.confirm('Terminer la session de « ' + (r.name || 'ce reporter') + ' » ?')) return;
    kickBusy = true;
    try {
      await dropChannel(r.id, false);
      await TtDirect.api('kick_reporter', { reporter_id: r.id });
      mixPrefs.delete(r.id);
      lastRows = lastRows.filter((x) => x.id !== r.id);
      renderList(lastRows);
      updateStatus();
      await refreshList().catch(() => {});
    } finally {
      kickBusy = false;
    }
  }

  function applyListPayload(data) {
    fromCache = !!data.from_cache || !!data.offline;
    networkOk = data.network !== false && !data.offline;
    onlineStatusAvailable = !!data.online_status_available && networkOk;
    if (typeof data.max_mix === 'number' && data.max_mix > 0) {
      maxMix = data.max_mix;
    }
    const rows = data.reporters || [];
    renderList(rows);
    const when = formatCacheTime(data.saved_at);
    setCacheLine(when ? ('Cache : ' + when) : '');
    setNetPill();
    return rows;
  }

  async function syncReporters(manual) {
    if (syncBusy) return;
    syncBusy = true;
    if (btnSync) btnSync.disabled = true;
    try {
      const res = await fetch('/reporters/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const data = await res.json();
      if (!data.ok && !(data.reporters && data.reporters.length)) {
        throw new Error(data.error || 'Sync impossible');
      }
      const rows = applyListPayload(data);
      if (onlineStatusAvailable) {
        await syncAuto(rows);
      } else {
        updateStatus();
      }
      if (manual && data.error && data.from_cache) {
        showErr(data.error);
      } else if (manual) {
        showErr('');
      }
      offlineSession = !networkOk;
    } finally {
      syncBusy = false;
      if (btnSync) btnSync.disabled = false;
    }
  }

  async function dropAllLiveChannels() {
    for (const id of [...channels.keys()]) {
      await dropChannel(id, false);
    }
  }

  function scheduleListPolling(fast) {
    clearInterval(listTimer);
    listTimer = setInterval(() => {
      refreshList().catch((e) => {
        if (onlineStatusAvailable) showErr(e.message);
      });
    }, fast ? 2000 : 8000);
  }

  /**
   * Applique les effets d’une transition réseau (reprise ou perte).
   * Centralisé pour éviter la course entre listTimer et netTimer :
   * refreshList() peut mettre onlineStatusAvailable à false avant que
   * netTimer ne capture prev — les canaux live doivent quand même être coupés.
   */
  async function applyNetworkTransition(wasOnline, nowOnline) {
    if (wasOnline === nowOnline) return;
    if (!wasOnline && nowOnline) {
      offlineSession = false;
      scheduleListPolling(true);
      syncReporters(false).catch(() => {});
      setCacheLine('Réseau de retour — sync en cours');
      return;
    }
    // Perte de réseau : stopper les polls WebRTC / signalisation
    scheduleListPolling(false);
    await dropAllLiveChannels();
    updateStatus();
    renderList(lastRows);
    offlineSession = true;
    setCacheLine('Réseau perdu — écoute live interrompue');
  }

  async function refreshList() {
    const wasOnline = onlineStatusAvailable;
    await fetchNetworkStatus();
    await applyNetworkTransition(wasOnline, onlineStatusAvailable);
    if (!onlineStatusAvailable) {
      // Hors ligne : lire le cache local, pas de poll live
      try {
        const res = await fetch('/reporters/cache', { cache: 'no-store' });
        const data = await res.json();
        applyListPayload(data);
        updateStatus();
      } catch (e) {
        showErr(e.message || 'Cache reporteurs indisponible');
      }
      return;
    }
    const data = await TtDirect.api('list_reporters', {});
    const rows = applyListPayload(data);
    await syncAuto(rows);
  }

  async function syncAuto(rows) {
    if (autoBusy) return;
    if (!onlineStatusAvailable) {
      updateStatus();
      return;
    }
    autoBusy = true;
    try {
      const online = new Set(rows.map((r) => r.id));
      for (const id of [...channels.keys()]) {
        if (!online.has(id)) await dropChannel(id, true);
      }
      const limit = autoLimit();
      if (limit <= 0) { updateStatus(); return; }
      for (const r of rows) {
        if (channels.size >= limit) break;
        if (channels.has(r.id)) continue;
        // Ne pas auto-connecter un reporteur dont la présence est inconnue
        if (r.presence_unknown) continue;
        try { await addChannel(r, false); } catch (e) { if (e && e.message) showErr(e.message); }
      }
      while (channels.size > limit) {
        await dropChannel(channels.keys().next().value, true);
      }
      updateStatus();
      renderList(rows);
    } finally {
      autoBusy = false;
    }
  }

  async function toggleReporter(r) {
    showErr('');
    if (channels.has(r.id)) {
      await dropChannel(r.id, true);
      updateStatus();
      renderList(lastRows);
      return;
    }
    if (channels.size >= maxMix) {
      showErr('Maximum ' + maxMix + ' reporters.');
      return;
    }
    await addChannel(r, true);
  }

  async function addChannel(r, rerender) {
    if (channels.has(r.id)) return;
    await TtDirect.api('select', { reporter_id: r.id });
    const audio = document.createElement('audio');
    audio.autoplay = true;
    audio.setAttribute('playsinline', '');
    audioMix.appendChild(audio);
    const postSignal = (payload) => TtDirect.api('signal', { role: 'studio', reporter_id: r.id, ...payload });
    const voice = TtDirect.createVoice({
      role: 'studio',
      iceServers: cfg.iceServers,
      mic: false,
      postSignal,
      onRemoteStream: (stream) => {
        audio.srcObject = stream;
        const existing = channels.get(r.id);
        if (existing) {
          applyChannelAudio(existing);
          attachRemoteMeter(existing, stream);
          renderList(lastRows);
        }
        const p = audio.play();
        if (p && p.catch) p.catch(() => {});
        updateStatus();
      },
      onState: (st) => {
        if (st === 'failed' || st === 'disconnected') rebuildChannel(r).catch(() => {});
      },
      onError: (m) => showErr(m),
    });
    const poll = setInterval(async () => {
      try {
        const signal = await TtDirect.api('poll', { role: 'studio', reporter_id: r.id });
        if (signal.ended) {
          await dropChannel(r.id, false);
          updateStatus();
          renderList(lastRows);
          return;
        }
        await voice.tick(signal);
      } catch (ex) {
        showErr(ex.message);
      }
    }, cfg.pollMs || 500);
    const pref = getMixPref(r.id);
    channels.set(r.id, {
      name: r.name, voice, audio, poll,
      listenStartedAt: Date.now(),
      muted: !!pref.muted,
      volume: typeof pref.volume === 'number' ? pref.volume : 1,
    });
    applyChannelAudio(channels.get(r.id));
    updateStatus();
    if (rerender) renderList(lastRows);
  }

  async function rebuildChannel(r) {
    if (!channels.has(r.id)) return;
    await dropChannel(r.id, true);
    await new Promise((res) => setTimeout(res, 400));
    if (lastRows.some((x) => x.id === r.id)) await addChannel(r, true);
  }

  async function dropChannel(id, notify) {
    const ch = channels.get(id);
    if (!ch) return;
    clearInterval(ch.poll);
    try { if (ch.streamMeter) ch.streamMeter.stop(); } catch (_) {}
    try { ch.voice.stop(true); } catch (_) {}
    try { ch.audio.srcObject = null; ch.audio.remove(); } catch (_) {}
    channels.delete(id);
    if (notify) {
      try { await TtDirect.api('deselect', { reporter_id: id }); } catch (_) {}
    }
  }

  async function stopAll() {
    for (const id of [...channels.keys()]) await dropChannel(id, false);
    try { await TtDirect.api('deselect_all', {}); } catch (_) {}
    updateStatus();
    renderList(lastRows);
  }

  function applyAutoMode(val) {
    autoMode = Number(val);
    if (![0, 1, 3].includes(autoMode)) autoMode = 3;
    sessionStorage.setItem('tt_studio_auto', String(autoMode));
    autoModeEl.value = String(autoMode);
    updateStatus();
    syncAuto(lastRows).catch((e) => showErr(e.message));
  }

  async function bootStudio() {
    if (!window.TtDirect) {
      showErr('Module audio indisponible');
      return;
    }
    keepAlive = TtDirect.createKeepAlive();
    showErr('');
    try {
      await fetchNetworkStatus();
      cfg = await TtDirect.api('config');
      if (!cfg.auth || !cfg.auth.studio) {
        showErr('Session régie invalide. Déconnectez-vous puis reconnectez-vous.');
        return;
      }
      maxMix = cfg.maxMix || cfg.max_mix || 3;
      window.TT_STUDIO.maxMix = maxMix;
      studioOpenedAt = Date.now();
      updateStatus();
      clearInterval(clockTimer);
      clockTimer = setInterval(() => { tickStudioClock(); renderList(lastRows); }, 1000);
      await keepAlive.start({ screenOn: true });
      autoModeEl.value = String(autoMode);
      autoModeEl.onchange = () => applyAutoMode(autoModeEl.value);

      // Première sync si réseau ; sinon cache
      if (onlineStatusAvailable) {
        await syncReporters(false).catch(() => refreshList());
      } else {
        await refreshList();
      }

      scheduleListPolling(onlineStatusAvailable);

      clearInterval(netTimer);
      netTimer = setInterval(async () => {
        const prev = onlineStatusAvailable;
        await fetchNetworkStatus();
        setNetPill();
        await applyNetworkTransition(prev, onlineStatusAvailable);
      }, 5000);
    } catch (ex) {
      showErr(ex.message || 'Impossible d’ouvrir la régie');
    }
  }

  btnStop.addEventListener('click', () => stopAll().catch((e) => showErr(e.message)));

  async function checkAppUpdate() {
    const banner = document.getElementById('updateBanner');
    const textEl = document.getElementById('updateBannerText');
    const linkEl = document.getElementById('updateBannerLink');
    const verLine = document.getElementById('appVersionLine');
    if (!banner || !textEl || !linkEl) return;
    try {
      const res = await fetch('/update');
      const data = await res.json();
      if (verLine && data && data.local) {
        verLine.hidden = false;
        verLine.textContent = 'Version ' + data.local;
      }
      // Hors ligne ou à jour : rien (pas de faux positif).
      if (!data || !data.available || !data.download) {
        banner.hidden = true;
        return;
      }
      textEl.textContent = data.message
        || ('Mise à jour ' + data.remote + ' disponible (vous avez ' + data.local + ').');
      linkEl.href = data.download;
      banner.hidden = false;
    } catch (_) {
      banner.hidden = true;
    }
  }

  checkAppUpdate().catch(() => {});

  authCheck().catch((e) => {
    sessionStatus.textContent = 'Impossible d’analyser les sessions : ' + (e.message || e);
  });
})();
