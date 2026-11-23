(() => {
  const tabs = document.getElementById('studioTabs');
  const nowPlaying = document.getElementById('nowPlaying');
  const studioTitle = document.getElementById('studioTitle');
  const airNow = document.getElementById('airNow');
  const titles = {
    reporters: 'Reporteurs connectés',
    playlist: 'Playlist antenne',
    jingles: 'Jingles',
    stream: 'Diffusion',
  };

  let activeTab = 'reporters';
  let playlistState = null;
  let mediaSongs = [];
  let mediaJingles = [];
  let schedule = null;
  let statusTimer = 0;
  let passwordDirty = false;

  function $(id) { return document.getElementById(id); }

  function showMsg(el, msg) {
    if (!el) return;
    el.hidden = !msg;
    el.textContent = msg || '';
  }

  async function api(method, url, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json' }, cache: 'no-store' };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok && data && data.error) {
      const err = new Error(data.error);
      err.data = data;
      throw err;
    }
    return data;
  }

  function switchTab(name) {
    activeTab = name;
    document.querySelectorAll('.tab').forEach((btn) => {
      btn.classList.toggle('is-active', btn.getAttribute('data-tab') === name);
    });
    ['reporters', 'playlist', 'jingles', 'stream'].forEach((id) => {
      const panel = $('panel-' + id);
      if (panel) panel.hidden = id !== name;
    });
    if (studioTitle) studioTitle.textContent = titles[name] || 'Régie';
    if (nowPlaying) nowPlaying.hidden = name === 'reporters';
    if (name === 'playlist') refreshPlaylist().catch(() => {});
    if (name === 'jingles') refreshJingles().catch(() => {});
    if (name === 'stream') refreshStream().catch(() => {});
  }

  if (tabs) {
    tabs.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-tab]');
      if (!btn) return;
      switchTab(btn.getAttribute('data-tab'));
    });
  }

  function renderNow(st) {
    const cur = st.current;
    const nxt = st.next;
    const curLabel = cur ? ((cur.kind === 'jingle' ? '[Jingle] ' : '') + cur.title) : '—';
    const nextLabel = nxt ? ((nxt.kind === 'jingle' ? '[Jingle] ' : '') + nxt.title) : '—';
    if ($('npCurrent')) $('npCurrent').textContent = curLabel;
    if ($('npNext')) $('npNext').textContent = nextLabel;
    if (airNow) {
      airNow.textContent = st.streaming
        ? ('Diff. ' + (cur ? cur.title : '…'))
        : (st.playing ? ('Loc. ' + (cur ? cur.title : '…')) : 'Antenne arrêtée');
      airNow.className = 'pill' + (st.streaming || st.playing ? ' is-live' : '');
    }
    const bits = [];
    if (st.play_mode) bits.push('Mode ' + st.play_mode);
    if (st.streaming) bits.push('Icecast/Shoutcast ON');
    if (st.ffmpeg_found === false) bits.push('ffmpeg manquant');
    if (st.error) bits.push(st.error);
    if (typeof st.elapsed_s === 'number' && st.playing) bits.push(Math.floor(st.elapsed_s) + 's');
    if ($('npMeta')) $('npMeta').textContent = bits.join(' · ');
    if ($('stStatus')) {
      $('stStatus').textContent = st.streaming
        ? ('Statut : diffusion active' + (cur ? ' — ' + cur.title : ''))
        : (st.playing ? 'Statut : lecture locale' : 'Statut : arrêté');
    }
  }

  async function pollStatus() {
    try {
      const st = await api('GET', '/radio/status');
      renderNow(st);
    } catch (_) {}
  }

  function startStatusPoll() {
    clearInterval(statusTimer);
    statusTimer = setInterval(pollStatus, 1500);
    pollStatus();
  }

  // —— Playlist ——
  async function refreshPlaylist() {
    const [pl, media] = await Promise.all([
      api('GET', '/playlists'),
      api('GET', '/media?kind=song'),
    ]);
    playlistState = pl.active || (pl.playlists && pl.playlists[0]);
    mediaSongs = media.items || [];
    if ($('playMode') && playlistState) $('playMode').value = playlistState.play_mode || 'sequential';
    if ($('plLoop') && playlistState) $('plLoop').checked = !!playlistState.loop;
    renderPlaylistItems();
  }

  function renderPlaylistItems() {
    const ul = $('playlistItems');
    const empty = $('plEmpty');
    if (!ul) return;
    ul.innerHTML = '';
    const items = (playlistState && playlistState.items) || [];
    const byId = Object.fromEntries(mediaSongs.map((m) => [m.id, m]));
    if (empty) empty.hidden = items.length > 0 || mediaSongs.length > 0;

    // File playlist
    items.forEach((it, idx) => {
      const m = byId[it.media_id];
      const li = document.createElement('li');
      li.className = 'media-row';
      li.innerHTML = '<span class="media-title">' + escapeHtml((m && m.title) || it.media_id) + '</span>';
      const actions = document.createElement('div');
      actions.className = 'row-actions';
      const up = document.createElement('button');
      up.type = 'button';
      up.className = 'btn ghost btn-compact';
      up.textContent = '↑';
      up.disabled = idx === 0;
      up.onclick = () => moveItem(idx, -1);
      const down = document.createElement('button');
      down.type = 'button';
      down.className = 'btn ghost btn-compact';
      down.textContent = '↓';
      down.disabled = idx === items.length - 1;
      down.onclick = () => moveItem(idx, 1);
      const rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'btn ghost btn-compact';
      rm.textContent = 'Retirer';
      rm.onclick = () => {
        playlistState.items = items.filter((_, i) => i !== idx);
        renderPlaylistItems();
      };
      actions.appendChild(up);
      actions.appendChild(down);
      actions.appendChild(rm);
      li.appendChild(actions);
      ul.appendChild(li);
    });

    // Bibliothèque non dans la file
    const inPl = new Set(items.map((x) => x.media_id));
    mediaSongs.forEach((m) => {
      if (inPl.has(m.id)) return;
      const li = document.createElement('li');
      li.className = 'media-row is-lib';
      li.innerHTML = '<span class="media-title">' + escapeHtml(m.title) + ' <em class="meta">(bibliothèque)</em></span>';
      const actions = document.createElement('div');
      actions.className = 'row-actions';
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'btn ghost btn-compact';
      add.textContent = 'Ajouter à la file';
      add.onclick = () => {
        playlistState.items = (playlistState.items || []).concat([{ media_id: m.id, order: 0 }]);
        renderPlaylistItems();
      };
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn ghost btn-compact';
      del.textContent = 'Supprimer';
      del.onclick = async () => {
        await api('POST', '/media/delete', { id: m.id });
        await refreshPlaylist();
      };
      actions.appendChild(add);
      actions.appendChild(del);
      li.appendChild(actions);
      ul.appendChild(li);
    });
  }

  function moveItem(idx, delta) {
    const items = (playlistState.items || []).slice();
    const j = idx + delta;
    if (j < 0 || j >= items.length) return;
    const t = items[idx];
    items[idx] = items[j];
    items[j] = t;
    playlistState.items = items;
    renderPlaylistItems();
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  $('btnImportSong') && $('btnImportSong').addEventListener('click', async () => {
    showMsg($('plErr'), '');
    try {
      const path = ($('importSongPath').value || '').trim();
      if (!path) throw new Error('Indiquez le chemin du fichier');
      const data = await api('POST', '/media/import', { path, kind: 'song' });
      const item = data.item;
      playlistState = playlistState || { id: 'pl_default', items: [] };
      playlistState.items = (playlistState.items || []).concat([{ media_id: item.id, order: 0 }]);
      await api('POST', '/playlists/update', {
        id: playlistState.id,
        items: playlistState.items,
        play_mode: $('playMode').value,
        loop: $('plLoop').checked,
      });
      $('importSongPath').value = '';
      await refreshPlaylist();
    } catch (e) {
      showMsg($('plErr'), e.message || 'Import impossible');
    }
  });

  $('btnSavePlaylist') && $('btnSavePlaylist').addEventListener('click', async () => {
    showMsg($('plErr'), '');
    try {
      await api('POST', '/playlists/update', {
        id: playlistState.id,
        items: playlistState.items || [],
        play_mode: $('playMode').value,
        loop: $('plLoop').checked,
      });
      await refreshPlaylist();
    } catch (e) {
      showMsg($('plErr'), e.message || 'Enregistrement impossible');
    }
  });

  $('playMode') && $('playMode').addEventListener('change', async () => {
    try {
      await api('POST', '/playlists/mode', {
        id: playlistState && playlistState.id,
        play_mode: $('playMode').value,
      });
    } catch (e) {
      showMsg($('plErr'), e.message);
    }
  });

  // —— Jingles ——
  async function refreshJingles() {
    const [media, sched] = await Promise.all([
      api('GET', '/media?kind=jingle'),
      api('GET', '/jingles/schedule'),
    ]);
    mediaJingles = media.items || [];
    schedule = sched.schedule || {};
    const bt = schedule.between_tracks || {};
    if ($('btEnabled')) $('btEnabled').checked = !!bt.enabled;
    if ($('btEvery')) $('btEvery').value = String(bt.every_n_songs || 3);
    if ($('btPick')) $('btPick').value = bt.pick || 'random';
    renderJingleLists();
  }

  function renderJingleLists() {
    const cart = $('jingleCart');
    const list = $('jingleList');
    const clockUl = $('clockList');
    if (cart) cart.innerHTML = '';
    if (list) list.innerHTML = '';
    if (clockUl) clockUl.innerHTML = '';
    const pool = new Set(((schedule.between_tracks || {}).jingle_ids) || []);
    const favs = new Set(schedule.favorites || []);

    mediaJingles.forEach((m) => {
      if (cart) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'btn ghost btn-compact cart-btn';
        b.textContent = m.title;
        b.title = 'Jouer maintenant';
        b.onclick = () => api('POST', '/jingles/fire', { id: m.id }).then(pollStatus).catch((e) => showMsg($('jgErr'), e.message));
        cart.appendChild(b);
      }
      if (list) {
        const li = document.createElement('li');
        li.className = 'media-row';
        const inPool = pool.has(m.id);
        li.innerHTML = '<span class="media-title">' + escapeHtml(m.title) + (inPool ? ' · pool' : '') + '</span>';
        const actions = document.createElement('div');
        actions.className = 'row-actions';
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'btn ghost btn-compact';
        toggle.textContent = inPool ? 'Retirer du pool' : 'Ajouter au pool';
        toggle.onclick = () => {
          const bt = schedule.between_tracks || { jingle_ids: [] };
          const ids = new Set(bt.jingle_ids || []);
          if (ids.has(m.id)) ids.delete(m.id); else ids.add(m.id);
          bt.jingle_ids = [...ids];
          schedule.between_tracks = bt;
          renderJingleLists();
        };
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'btn ghost btn-compact';
        del.textContent = 'Supprimer';
        del.onclick = async () => {
          await api('POST', '/media/delete', { id: m.id });
          await refreshJingles();
        };
        actions.appendChild(toggle);
        actions.appendChild(del);
        li.appendChild(actions);
        list.appendChild(li);
      }
    });

    (schedule.clock || []).forEach((entry, idx) => {
      if (!clockUl) return;
      const li = document.createElement('li');
      li.className = 'media-row';
      li.innerHTML = '<span class="media-title">Horaire ' + escapeHtml(entry.time)
        + ' · ' + escapeHtml(entry.pick || 'sequential')
        + ' · ' + ((entry.jingle_ids || []).length) + ' jingle(s)</span>';
      const rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'btn ghost btn-compact';
      rm.textContent = 'Retirer';
      rm.onclick = () => {
        schedule.clock = (schedule.clock || []).filter((_, i) => i !== idx);
        renderJingleLists();
      };
      const actions = document.createElement('div');
      actions.className = 'row-actions';
      actions.appendChild(rm);
      li.appendChild(actions);
      clockUl.appendChild(li);
    });
  }

  $('btnImportJingle') && $('btnImportJingle').addEventListener('click', async () => {
    showMsg($('jgErr'), '');
    try {
      const path = ($('importJinglePath').value || '').trim();
      if (!path) throw new Error('Indiquez le chemin du fichier');
      const data = await api('POST', '/media/import', { path, kind: 'jingle' });
      const bt = schedule.between_tracks || { jingle_ids: [] };
      bt.jingle_ids = (bt.jingle_ids || []).concat([data.item.id]);
      schedule.between_tracks = bt;
      await api('POST', '/jingles/schedule', { schedule });
      $('importJinglePath').value = '';
      await refreshJingles();
    } catch (e) {
      showMsg($('jgErr'), e.message || 'Import impossible');
    }
  });

  $('btnAddClock') && $('btnAddClock').addEventListener('click', () => {
    const t = ($('clockTime').value || '').trim();
    if (!/^\d{1,2}:\d{2}$/.test(t)) {
      showMsg($('jgErr'), 'Format horaire HH:MM requis');
      return;
    }
    const pool = ((schedule.between_tracks || {}).jingle_ids) || [];
    schedule.clock = (schedule.clock || []).concat([{
      time: t,
      jingle_ids: pool.slice(),
      pick: $('btPick').value || 'sequential',
      days: [1, 2, 3, 4, 5, 6, 7],
    }]);
    $('clockTime').value = '';
    renderJingleLists();
  });

  $('btnSaveJingles') && $('btnSaveJingles').addEventListener('click', async () => {
    showMsg($('jgErr'), '');
    try {
      const bt = schedule.between_tracks || {};
      bt.enabled = $('btEnabled').checked;
      bt.every_n_songs = Number($('btEvery').value) || 3;
      bt.pick = $('btPick').value || 'random';
      schedule.between_tracks = bt;
      await api('POST', '/jingles/schedule', { schedule });
      await refreshJingles();
    } catch (e) {
      showMsg($('jgErr'), e.message || 'Enregistrement impossible');
    }
  });

  // —— Diffusion ——
  async function refreshStream() {
    const data = await api('GET', '/stream/config');
    const c = data.config || {};
    if ($('stProtocol')) $('stProtocol').value = c.protocol || 'icecast';
    if ($('stHost')) $('stHost').value = c.host || '';
    if ($('stPort')) $('stPort').value = String(c.port || 8000);
    if ($('stMount')) $('stMount').value = c.mount || '/stream';
    if ($('stUser')) $('stUser').value = c.username || 'source';
    if ($('stPass')) {
      $('stPass').value = c.has_password ? '••••••••' : '';
      passwordDirty = false;
    }
    if ($('stBitrate')) $('stBitrate').value = String(c.bitrate_kbps || 128);
    if ($('stFfmpeg')) $('stFfmpeg').value = c.ffmpeg_path || '';
    if ($('stSsl')) $('stSsl').checked = !!c.ssl;
    await pollStatus();
  }

  function streamPayload() {
    const payload = {
      protocol: $('stProtocol').value,
      host: $('stHost').value.trim(),
      port: Number($('stPort').value) || 8000,
      mount: $('stMount').value.trim() || '/stream',
      username: $('stUser').value.trim() || 'source',
      bitrate_kbps: Number($('stBitrate').value) || 128,
      ffmpeg_path: $('stFfmpeg').value.trim(),
      ssl: $('stSsl').checked,
      format: 'mp3',
    };
    if (passwordDirty) payload.password = $('stPass').value;
    return payload;
  }

  $('stPass') && $('stPass').addEventListener('input', () => { passwordDirty = true; });

  $('btnSaveStream') && $('btnSaveStream').addEventListener('click', async () => {
    showMsg($('stErr'), '');
    try {
      await api('POST', '/stream/config', { config: streamPayload() });
      passwordDirty = false;
      await refreshStream();
    } catch (e) {
      showMsg($('stErr'), e.message || 'Enregistrement impossible');
    }
  });

  $('btnTestStream') && $('btnTestStream').addEventListener('click', async () => {
    showMsg($('stErr'), '');
    try {
      const data = await api('POST', '/stream/test', { config: streamPayload() });
      if (data.warning) showMsg($('stErr'), data.warning);
      else if ($('stStatus')) $('stStatus').textContent = 'Statut : test OK' + (data.ffmpeg_path ? ' · ' + data.ffmpeg_path : '');
    } catch (e) {
      showMsg($('stErr'), e.message || 'Test échoué');
    }
  });

  $('btnStartStream') && $('btnStartStream').addEventListener('click', async () => {
    showMsg($('stErr'), '');
    try {
      await api('POST', '/stream/config', { config: streamPayload() });
      const st = await api('POST', '/stream/start', {});
      if (st.error) showMsg($('stErr'), st.error);
      renderNow(st);
    } catch (e) {
      showMsg($('stErr'), e.message || 'Démarrage impossible');
    }
  });

  $('btnStopStream') && $('btnStopStream').addEventListener('click', async () => {
    const st = await api('POST', '/stream/stop', {});
    renderNow(st);
  });

  $('btnRadioPlay') && $('btnRadioPlay').addEventListener('click', async () => {
    const st = await api('POST', '/radio/play', { stream: false });
    renderNow(st);
  });
  $('btnRadioSkip') && $('btnRadioSkip').addEventListener('click', async () => {
    const st = await api('POST', '/radio/skip', {});
    renderNow(st);
  });
  $('btnRadioStop') && $('btnRadioStop').addEventListener('click', async () => {
    const st = await api('POST', '/radio/stop', {});
    renderNow(st);
  });

  // Exposé pour app.js après ouverture studio
  window.TTRadio = {
    boot() {
      startStatusPoll();
      refreshPlaylist().catch(() => {});
    },
    switchTab,
  };
})();
