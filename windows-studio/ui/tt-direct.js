window.TtDirect = (() => {
  function normalizeSdp(sdp) {
    if (!sdp || typeof sdp !== 'string') return sdp;
    return sdp.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      .split('\n').map((l) => l.trim()).filter((l) => l.length)
      .join('\r\n') + '\r\n';
  }

  async function api(action, body = {}) {
    const payload = { action, ...body };
    // Secours régie : pin embarqué si la session WP n’est pas renvoyée au POST.
    if (payload.pin == null && window.TT_STUDIO && window.TT_STUDIO.pin) {
      payload.pin = window.TT_STUDIO.pin;
    }
    const apiUrl = (window.TT_API_URL || 'api.php');
    const res = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
      credentials: 'same-origin',
    });
    const text = await res.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      throw new Error('Réponse API invalide (pas de JSON)');
    }
    if (!res.ok || data.ok !== true) {
      throw new Error(data.error || ('Erreur API ' + res.status));
    }
    return data;
  }

  function formatDuration(sec) {
    sec = Math.max(0, Math.floor(Number(sec) || 0));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (h > 0) {
      return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    }
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  /**
   * Maintien de liaison longue durée :
   * - Wake Lock écran (anti-verrouillage)
   * - Audio HTML silencieux en boucle (survie arrière-plan / écran verrouillé)
   * - Web Audio + Media Session (le système traite la page comme un appel média)
   */
  function createKeepAlive() {
    let wakeLock = null;
    let ctx = null;
    let osc = null;
    let gainNode = null;
    let silentAudio = null;
    let running = false;
    let preferScreenOn = true;
    let reacquireTimer = 0;
    let tickTimer = 0;

    // WAV quasi silencieux (~0.2s) — boucle pour empêcher la suspension navigateur.
    const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';

    function setMediaSession(active) {
      try {
        if (!('mediaSession' in navigator)) return;
        if (active) {
          navigator.mediaSession.metadata = new MediaMetadata({
            title: 'Direct audio',
            artist: 'TIC TAC Hebdo',
            album: 'Reporter en ligne',
          });
          navigator.mediaSession.playbackState = 'playing';
          try {
            navigator.mediaSession.setActionHandler('pause', () => {});
            navigator.mediaSession.setActionHandler('play', () => { resume(); });
            navigator.mediaSession.setActionHandler('stop', () => {});
          } catch (_) {}
        } else {
          navigator.mediaSession.playbackState = 'none';
        }
      } catch (_) {}
    }

    async function ensureSilentAudio() {
      if (!silentAudio) {
        silentAudio = new Audio(SILENT_WAV);
        silentAudio.loop = true;
        silentAudio.preload = 'auto';
        silentAudio.volume = 0.01;
        silentAudio.setAttribute('playsinline', '');
        silentAudio.setAttribute('webkit-playsinline', '');
      }
      try {
        await silentAudio.play();
      } catch (_) {}
    }

    async function ensureWebAudio() {
      try {
        if (!ctx) {
          ctx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (ctx.state === 'suspended') await ctx.resume();
        if (!osc) {
          osc = ctx.createOscillator();
          gainNode = ctx.createGain();
          gainNode.gain.value = 0.00004;
          osc.frequency.value = 18;
          osc.connect(gainNode);
          gainNode.connect(ctx.destination);
          osc.start();
        }
      } catch (_) {}
    }

    async function requestWake() {
      if (!preferScreenOn || !running) return;
      try {
        if ('wakeLock' in navigator) {
          if (wakeLock && !wakeLock.released) return;
          wakeLock = await navigator.wakeLock.request('screen');
          wakeLock.addEventListener('release', () => {
            wakeLock = null;
            if (running && preferScreenOn && document.visibilityState === 'visible') {
              requestWake().catch(() => {});
            }
          });
        }
      } catch (_) {}
    }

    async function start(opts) {
      running = true;
      if (opts && typeof opts.screenOn === 'boolean') preferScreenOn = opts.screenOn;
      await ensureSilentAudio();
      await ensureWebAudio();
      setMediaSession(true);
      if (preferScreenOn) await requestWake();
      else {
        try { if (wakeLock) await wakeLock.release(); } catch (_) {}
        wakeLock = null;
      }
      clearInterval(reacquireTimer);
      clearInterval(tickTimer);
      // Réacquérir périodiquement (certains OS lâchent le lock).
      reacquireTimer = setInterval(() => {
        if (!running) return;
        resume().catch(() => {});
      }, 20000);
      // Micro-tick audio pour contrer la suspension agressive.
      tickTimer = setInterval(() => {
        if (!running) return;
        try {
          if (silentAudio && silentAudio.paused) silentAudio.play().catch(() => {});
          if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
        } catch (_) {}
      }, 5000);
      return {
        screenOn: preferScreenOn,
        wakeLock: !!(wakeLock && !wakeLock.released),
      };
    }

    async function resume() {
      if (!running) return;
      await ensureSilentAudio();
      await ensureWebAudio();
      setMediaSession(true);
      if (preferScreenOn && document.visibilityState === 'visible') {
        await requestWake();
      }
    }

    async function setScreenOn(on) {
      preferScreenOn = !!on;
      if (!running) return preferScreenOn;
      if (preferScreenOn) {
        await requestWake();
      } else {
        try { if (wakeLock) await wakeLock.release(); } catch (_) {}
        wakeLock = null;
        // L’audio silencieux reste actif pour survivre au verrouillage.
        await ensureSilentAudio();
        await ensureWebAudio();
        setMediaSession(true);
      }
      return preferScreenOn;
    }

    function isScreenOnPreferred() {
      return preferScreenOn;
    }

    function hasWakeLock() {
      return !!(wakeLock && !wakeLock.released);
    }

    function stop() {
      running = false;
      clearInterval(reacquireTimer);
      clearInterval(tickTimer);
      reacquireTimer = 0;
      tickTimer = 0;
      setMediaSession(false);
      try { if (osc) osc.stop(); } catch (_) {}
      osc = null;
      gainNode = null;
      try { if (ctx) ctx.close(); } catch (_) {}
      ctx = null;
      try {
        if (silentAudio) {
          silentAudio.pause();
          silentAudio.src = '';
        }
      } catch (_) {}
      silentAudio = null;
      try { if (wakeLock) wakeLock.release(); } catch (_) {}
      wakeLock = null;
    }

    return { start, resume, stop, setScreenOn, isScreenOnPreferred, hasWakeLock };
  }

  function createVoice({ role, iceServers, postSignal, onRemoteStream, onState, onError, mic = true, existingStream = null }) {
    let pc = null;
    let localStream = existingStream || null;
    let closed = false;
    let offerSent = false;
    let answerSent = false;
    let hasRemoteDesc = false;
    let pendingRemoteIce = [];
    let appliedReporterIce = 0;
    let appliedStudioIce = 0;
    let tickBusy = false;
    let analyser = null;
    let audioCtx = null;
    let raf = 0;
    let appliedOfferSdp = null;

    function setState(s) { if (onState) onState(s); }

    async function getMic() {
      if (!mic) return null;
      if (localStream) return localStream;
      localStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      setState('mic-ok');
      return localStream;
    }

    function startMeter(onLevel) {
      if (!localStream || !onLevel) return;
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const src = audioCtx.createMediaStreamSource(localStream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        src.connect(analyser);
        const data = new Uint8Array(analyser.frequencyBinCount);
        const loop = () => {
          if (closed) return;
          analyser.getByteFrequencyData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) sum += data[i];
          onLevel(Math.min(100, (sum / data.length) * 1.6));
          raf = requestAnimationFrame(loop);
        };
        loop();
      } catch (_) {}
    }

    async function ensurePc() {
      if (pc) return pc;
      pc = new RTCPeerConnection({ iceServers: iceServers || [], iceCandidatePoolSize: 8 });
      pc.onicecandidate = (ev) => {
        if (!ev.candidate || closed) return;
        postSignal({ type: 'ice', candidate: ev.candidate.toJSON() }).catch(() => {});
      };
      pc.onconnectionstatechange = () => { if (pc) setState(pc.connectionState); };
      pc.oniceconnectionstatechange = () => {
        if (!pc) return;
        const s = pc.iceConnectionState;
        if (s === 'connected' || s === 'completed') setState('connected');
        else if (s === 'checking' || s === 'new') setState('checking');
        else if (s === 'failed') setState('failed');
        else if (s === 'disconnected') setState('disconnected');
      };
      pc.ontrack = (ev) => {
        const stream = ev.streams && ev.streams[0] ? ev.streams[0] : new MediaStream([ev.track]);
        if (onRemoteStream) onRemoteStream(stream);
      };

      if (mic) {
        const stream = await getMic();
        stream.getTracks().forEach((t) => pc.addTrack(t, stream));
      } else {
        pc.addTransceiver('audio', { direction: 'recvonly' });
      }
      return pc;
    }

    async function addIce(candidate) {
      if (!pc || !candidate) return;
      if (!hasRemoteDesc) { pendingRemoteIce.push(candidate); return; }
      try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); }
      catch (_) { pendingRemoteIce.push(candidate); }
    }

    async function flushIce() {
      const batch = pendingRemoteIce.splice(0);
      for (const c of batch) {
        try { await pc.addIceCandidate(new RTCIceCandidate(c)); } catch (_) {}
      }
    }

    async function applyIce(list, from) {
      if (!list) return from;
      for (let i = from; i < list.length; i++) await addIce(list[i]);
      await flushIce();
      return list.length;
    }

    async function tick(signal) {
      if (closed || !signal || tickBusy) return;
      if (signal.ended) {
        stop(false);
        setState('ended');
        return;
      }
      tickBusy = true;
      try {
        if (role === 'reporter') {
          if (!signal.selected) {
            setState('waiting');
            tickBusy = false;
            return;
          }
          const conn = await ensurePc();
          if (!offerSent) {
            setState('negotiating');
            const offer = await conn.createOffer({ offerToReceiveAudio: false });
            await conn.setLocalDescription(offer);
            await postSignal({ type: 'offer', sdp: offer.sdp });
            offerSent = true;
          }
          if (signal.answer && !conn.currentRemoteDescription) {
            await conn.setRemoteDescription({ type: 'answer', sdp: normalizeSdp(signal.answer) });
            hasRemoteDesc = true;
            await flushIce();
          }
          appliedStudioIce = await applyIce(signal.ice_studio || [], appliedStudioIce);
        } else {
          if (!signal.offer) {
            setState('waiting-offer');
            tickBusy = false;
            return;
          }
          // Nouvelle offre (ex. reporter a rechargé) → renégocier
          if (appliedOfferSdp && appliedOfferSdp !== signal.offer) {
            resetNegotiation();
            appliedOfferSdp = null;
          }
          const conn = await ensurePc();
          if (!conn.currentRemoteDescription) {
            await conn.setRemoteDescription({ type: 'offer', sdp: normalizeSdp(signal.offer) });
            hasRemoteDesc = true;
            appliedOfferSdp = signal.offer;
            if (!answerSent) {
              const answer = await conn.createAnswer();
              await conn.setLocalDescription(answer);
              await postSignal({ type: 'answer', sdp: answer.sdp });
              answerSent = true;
            }
            await flushIce();
          }
          appliedReporterIce = await applyIce(signal.ice_reporter || [], appliedReporterIce);
        }
      } catch (err) {
        if (onError) onError(err.message || 'Erreur audio');
        setState('error');
      } finally {
        tickBusy = false;
      }
    }

    function resetNegotiation() {
      try { if (pc) pc.close(); } catch (_) {}
      pc = null;
      offerSent = false;
      answerSent = false;
      hasRemoteDesc = false;
      pendingRemoteIce = [];
      appliedReporterIce = 0;
      appliedStudioIce = 0;
      appliedOfferSdp = null;
    }

    function stop(stopMic = true) {
      closed = true;
      cancelAnimationFrame(raf);
      try { if (audioCtx) audioCtx.close(); } catch (_) {}
      try { if (stopMic && localStream) localStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
      try { if (pc) pc.close(); } catch (_) {}
      pc = null;
      if (stopMic) localStream = null;
    }

    return { ensurePc, getMic, startMeter, tick, stop, resetNegotiation, setState };
  }

  /**
   * Liaison audio sendrecv entre deux reporters (mesh).
   * L’ID lexico plus petit est offerer.
   */
  function createPeerVoice({ iceServers, localStream, isOfferer, postSignal, onRemoteStream, onState, onError }) {
    let pc = null;
    let closed = false;
    let offerSent = false;
    let answerSent = false;
    let hasRemoteDesc = false;
    let pendingRemoteIce = [];
    let appliedPeerIce = 0;
    let tickBusy = false;
    let appliedOfferSdp = null;
    let localOfferSdp = null;

    function setState(s) { if (onState) onState(s); }

    async function ensurePc() {
      if (pc) return pc;
      pc = new RTCPeerConnection({ iceServers: iceServers || [], iceCandidatePoolSize: 8 });
      pc.onicecandidate = (ev) => {
        if (!ev.candidate || closed) return;
        postSignal({ type: 'ice', candidate: ev.candidate.toJSON() }).catch(() => {});
      };
      pc.onconnectionstatechange = () => { if (pc) setState(pc.connectionState); };
      pc.oniceconnectionstatechange = () => {
        if (!pc) return;
        const s = pc.iceConnectionState;
        if (s === 'connected' || s === 'completed') setState('connected');
        else if (s === 'failed') setState('failed');
        else if (s === 'disconnected') setState('disconnected');
      };
      pc.ontrack = (ev) => {
        const stream = ev.streams && ev.streams[0] ? ev.streams[0] : new MediaStream([ev.track]);
        if (onRemoteStream) onRemoteStream(stream);
      };
      if (localStream) {
        localStream.getTracks().forEach((t) => pc.addTrack(t, localStream));
      } else {
        pc.addTransceiver('audio', { direction: 'sendrecv' });
      }
      return pc;
    }

    async function addIce(candidate) {
      if (!pc || !candidate) return;
      if (!hasRemoteDesc) { pendingRemoteIce.push(candidate); return; }
      try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); }
      catch (_) { pendingRemoteIce.push(candidate); }
    }

    async function flushIce() {
      const batch = pendingRemoteIce.splice(0);
      for (const c of batch) {
        try { await pc.addIceCandidate(new RTCIceCandidate(c)); } catch (_) {}
      }
    }

    async function applyIce(list, from) {
      if (!list) return from;
      for (let i = from; i < list.length; i++) await addIce(list[i]);
      await flushIce();
      return list.length;
    }

    function resetNegotiation() {
      try { if (pc) pc.close(); } catch (_) {}
      pc = null;
      offerSent = false;
      answerSent = false;
      hasRemoteDesc = false;
      pendingRemoteIce = [];
      appliedPeerIce = 0;
      appliedOfferSdp = null;
      localOfferSdp = null;
    }

    async function tick(signal) {
      if (closed || !signal || tickBusy) return;
      if (signal.ended) {
        stop();
        setState('ended');
        return;
      }
      tickBusy = true;
      try {
        if (isOfferer) {
          // Signalisation vidée (reprise après refresh) → renvoyer une offre
          if (offerSent && !signal.offer && !signal.answer) {
            resetNegotiation();
          }
          const conn = await ensurePc();
          if (!offerSent) {
            setState('negotiating');
            const offer = await conn.createOffer({ offerToReceiveAudio: true });
            await conn.setLocalDescription(offer);
            localOfferSdp = offer.sdp;
            await postSignal({ type: 'offer', sdp: offer.sdp });
            offerSent = true;
          }
          if (signal.answer && !conn.currentRemoteDescription) {
            await conn.setRemoteDescription({ type: 'answer', sdp: normalizeSdp(signal.answer) });
            hasRemoteDesc = true;
            await flushIce();
          }
        } else {
          if (!signal.offer) {
            if (answerSent || hasRemoteDesc) resetNegotiation();
            setState('waiting-offer');
            tickBusy = false;
            return;
          }
          if (appliedOfferSdp && appliedOfferSdp !== signal.offer) {
            resetNegotiation();
          }
          const conn = await ensurePc();
          if (!conn.currentRemoteDescription) {
            await conn.setRemoteDescription({ type: 'offer', sdp: normalizeSdp(signal.offer) });
            hasRemoteDesc = true;
            appliedOfferSdp = signal.offer;
            if (!answerSent) {
              const answer = await conn.createAnswer();
              await conn.setLocalDescription(answer);
              await postSignal({ type: 'answer', sdp: answer.sdp });
              answerSent = true;
            }
            await flushIce();
          }
        }
        appliedPeerIce = await applyIce(signal.ice_peer || [], appliedPeerIce);
      } catch (err) {
        if (onError) onError(err.message || 'Erreur audio pair');
        setState('error');
      } finally {
        tickBusy = false;
      }
    }

    function stop() {
      closed = true;
      try { if (pc) pc.close(); } catch (_) {}
      pc = null;
    }

    return { tick, stop, setState, resetNegotiation };
  }

  /** Coupe / réactive les pistes micro sans fermer la session. */
  function setMicMuted(stream, muted) {
    if (!stream) return;
    stream.getAudioTracks().forEach((t) => {
      t.enabled = !muted;
    });
  }

  /**
   * Choix de sortie audio (haut-parleur / écouteurs) via setSinkId quand le navigateur le permet.
   */
  function createAudioOutput() {
    /** @type {Set<HTMLMediaElement>} */
    const elements = new Set();
    let mode = sessionStorage.getItem('tt_audio_out') || 'auto'; // auto | speaker | headphones | device:<id>
    let devices = [];
    let currentSinkId = '';

    function register(el) {
      if (!el) return;
      elements.add(el);
      applyTo(el).catch(() => {});
    }

    function unregister(el) {
      if (!el) return;
      elements.delete(el);
    }

    function classify(dev) {
      const label = String(dev.label || '').toLowerCase();
      if (/headphone|headset|écouteur|ecouteur|airpod|earbud|casque|bluetooth/.test(label)) return 'headphones';
      if (/speaker|haut.?parleur|loudspeaker|hdmi|display/.test(label)) return 'speaker';
      return 'other';
    }

    async function refreshDevices() {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
          devices = [];
          return devices;
        }
        const list = await navigator.mediaDevices.enumerateDevices();
        devices = list.filter((d) => d.kind === 'audiooutput');
      } catch (_) {
        devices = [];
      }
      return devices;
    }

    function pickSinkId() {
      if (!devices.length) return '';
      if (mode.startsWith('device:')) {
        const id = mode.slice(7);
        return devices.some((d) => d.deviceId === id) ? id : '';
      }
      if (mode === 'headphones') {
        const hp = devices.find((d) => classify(d) === 'headphones');
        if (hp) return hp.deviceId;
        // sinon premier non-speaker si possible
        const nonSp = devices.find((d) => classify(d) !== 'speaker');
        return (nonSp || devices[0]).deviceId;
      }
      if (mode === 'speaker') {
        const sp = devices.find((d) => classify(d) === 'speaker');
        if (sp) return sp.deviceId;
        // Forcer le défaut système souvent = haut-parleur PC ; éviter les casques
        const notHp = devices.find((d) => classify(d) !== 'headphones');
        return (notHp || devices[0]).deviceId;
      }
      // auto = sink par défaut du navigateur
      return '';
    }

    async function applyTo(el) {
      if (!el || typeof el.setSinkId !== 'function') return false;
      const sinkId = pickSinkId();
      currentSinkId = sinkId;
      try {
        await el.setSinkId(sinkId || '');
        return true;
      } catch (_) {
        return false;
      }
    }

    async function applyAll() {
      await refreshDevices();
      let ok = false;
      for (const el of elements) {
        if (await applyTo(el)) ok = true;
      }
      return ok;
    }

    async function setMode(next) {
      mode = next || 'auto';
      sessionStorage.setItem('tt_audio_out', mode);
      return applyAll();
    }

    function getMode() {
      return mode;
    }

    function supportsSinkId() {
      return typeof HTMLMediaElement !== 'undefined'
        && typeof HTMLMediaElement.prototype.setSinkId === 'function';
    }

    function listChoices() {
      const choices = [
        { value: 'auto', label: 'Auto (sortie système)' },
        { value: 'speaker', label: 'Haut-parleur (éviter les écouteurs)' },
        { value: 'headphones', label: 'Écouteurs / casque si branchés' },
      ];
      devices.forEach((d, i) => {
        const name = d.label || ('Sortie ' + (i + 1));
        choices.push({ value: 'device:' + d.deviceId, label: name });
      });
      return choices;
    }

    return {
      register,
      unregister,
      refreshDevices,
      setMode,
      getMode,
      applyAll,
      supportsSinkId,
      listChoices,
      getCurrentSinkId: () => currentSinkId,
    };
  }

  function createStreamMeter(stream, onLevel, onBands) {
    let closed = false;
    let raf = 0;
    let audioCtx = null;
    if (!stream || !onLevel) {
      return { stop() {} };
    }
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.55;
      src.connect(analyser);
      const freq = new Uint8Array(analyser.frequencyBinCount);
      const time = new Uint8Array(analyser.fftSize);
      const loop = () => {
        if (closed) return;
        analyser.getByteFrequencyData(freq);
        analyser.getByteTimeDomainData(time);
        let sum = 0;
        for (let i = 0; i < freq.length; i++) sum += freq[i];
        let peak = 0;
        for (let i = 0; i < time.length; i++) {
          const v = Math.abs(time[i] - 128);
          if (v > peak) peak = v;
        }
        const lvl = Math.min(100, Math.max((sum / freq.length) * 1.85, peak * 1.35));
        onLevel(lvl);
        if (onBands) {
          const bands = 16;
          const out = new Array(bands);
          const slice = Math.floor(freq.length / bands);
          for (let b = 0; b < bands; b++) {
            let s = 0;
            const start = b * slice;
            for (let i = start; i < start + slice; i++) s += freq[i] || 0;
            out[b] = Math.min(100, (s / Math.max(1, slice)) * 1.9);
          }
          onBands(out);
        }
        raf = requestAnimationFrame(loop);
      };
      const resume = () => {
        if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
      };
      resume();
      document.addEventListener('click', resume, { once: true });
      loop();
    } catch (_) {}
    return {
      stop() {
        closed = true;
        if (raf) cancelAnimationFrame(raf);
        try { if (audioCtx) audioCtx.close(); } catch (_) {}
        audioCtx = null;
      },
    };
  }

  return { api, createVoice, createPeerVoice, formatDuration, createKeepAlive, createAudioOutput, setMicMuted, createStreamMeter };
})();
