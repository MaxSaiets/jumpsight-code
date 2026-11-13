/* Live recording mode: camera stream, voice cues, part upload, live feed. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* ── Backend Upload & Instant Live Preview ── */
  /* In-app recorder. getUserMedia → MediaRecorder with
     timeslice 4 s → each part at once to POST /upload_part; 'Stop' →
     /upload_finish → watchJob. The button is shown only where there is a
     MediaRecorder and a camera (iOS 14.3+, Android Chrome). The system-camera
     path stays available. */
  const LIVE = { rows: [], rec: null, stream: null, job: null, seq: 0, queue: Promise.resolve(), t0: 0, timer: null, mime: '', failed: false,
    pending: new Map(), finishPending: false, retrying: false, duration: 0, generation: 0,
    starting: false, startEpoch: 0, owner: null };

  function liveMime() {
    const c = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4;codecs=avc1', 'video/mp4'];
    for (const m of c) { try { if (MediaRecorder.isTypeSupported(m)) return m; } catch (_) { } }
    return '';
  }

  /* SOUND AND VOICE ON THE ICE. The skater is a few meters from the phone
     the screen does not read (SPEC-user-needs: 'hear the attempt confirmation'). So a new jump is a short signal,
     and the ready verdict is two tones and a voice
     ('Double Lutz. Clean'). iOS allows voice only after a gesture:
     we unlock it with an empty phrase at the moment 'Start' is pressed. */
  const liveVoice = { unlocked: false };
  function liveUnlockVoice() {
    if (!NS.soundOn() || !('speechSynthesis' in window)) return;
    try { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance('')); liveVoice.unlocked = true; } catch (_) { }
  }
  function liveSay(text) {
    if (!NS.soundOn() || !('speechSynthesis' in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-US';
      u.rate = 1.0;
      window.speechSynthesis.speak(u);
    } catch (_) { }
  }
  function liveChime(kind, current = () => true) {
    if (!NS.soundOn()) return;
    if (kind === 'found') { NS.playClickSound(660, 0.09); return; }
    NS.playClickSound(kind === 'clean' ? 880 : 520, 0.12);
    setTimeout(() => {
      if (current()) NS.playClickSound(kind === 'clean' ? 1175 : 520, 0.14);
    }, 160);
  }

  async function liveStart() {
    if (LIVE.rec || LIVE.retrying || LIVE.starting) return;
    if (NS.activeJobId || NS.uploadInFlight) { NS.notice('Wait for the current analysis.'); return; }
    if (LIVE.finishPending) { liveUploadFailed(); return; }
    if (!NS.analysisSessionReady()) {
      NS.notice('Your profile is still loading. Wait for it, then press Start again.');
      return;
    }
    const owner = { ownerUid: NS.readyMeUid, generation: NS.identityGeneration, name: '' };
    const startEpoch = ++LIVE.startEpoch;
    LIVE.starting = true;
    try { await liveBegin(owner, startEpoch); }
    finally { if (startEpoch === LIVE.startEpoch) LIVE.starting = false; }
  }

  function stopStartingStream(stream) {
    if (!stream) return;
    stream.getTracks().forEach(track => {
      if (track.readyState !== 'ended') track.stop();
    });
    if (LIVE.stream === stream) LIVE.stream = null;
  }

  async function liveBegin(owner, startEpoch) {
    const box = document.getElementById('live-rec');
    const vid = document.getElementById('live-rec-video');
    const startScreen = NS.currentScreen;
    const current = () => startEpoch === LIVE.startEpoch && NS.jobOwnerCurrent(owner);
    let stream = null;
    liveUnlockVoice();
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 60 } }
      });
      if (!current()) { stopStartingStream(stream); return; }
      LIVE.stream = stream;
      const camera = stream.getVideoTracks()[0]?.getSettings?.() || {};
      const cameraInfo = document.getElementById('live-cam-settings');
      if (cameraInfo) cameraInfo.textContent = [
        camera.width && camera.height ? `${camera.width}×${camera.height}` : '',
        camera.frameRate ? `${Math.round(camera.frameRate)} fps` : ''
      ].filter(Boolean).join(' · ');
    } catch (e) {
      if (!current()) { stopStartingStream(stream); return; }
      const tn = document.getElementById('train-live-note');
      if (NS.currentScreen === 'today' && tn) {
        tn.hidden = false;
        tn.textContent = 'Camera unavailable: allow access in the browser (or open the app via https). For now, use “Record now” under Analyse.';
        return;
      }
      NS.analysisFailed('camera unavailable — allow access or use the system camera',
                     'Live recording did not start');
      return;
    }
    LIVE.mime = liveMime();
    const ext = LIVE.mime.startsWith('video/mp4') ? 'mp4' : 'webm';
    try {
      const response = await fetch('/upload_start', { method: 'POST', headers: { 'X-App-Ext': ext } });
      if (!current()) { stopStartingStream(stream); return; }
      let payload = {};
      try { payload = await response.json(); } catch (_) { }
      if (!current()) { stopStartingStream(stream); return; }
      if (!response.ok || typeof payload.job !== 'string' || !/^[A-Za-z0-9_-]+$/.test(payload.job)) {
        throw new Error(payload.error || (response.ok
          ? 'the server did not return a recording ID'
          : `HTTP ${response.status}`));
      }
      LIVE.job = payload.job;
      LIVE.owner = owner;
    } catch (e) {
      if (!current()) { stopStartingStream(stream); return; }
      liveTeardown();
      const reason = e && e.message ? e.message : 'no connection to the server';
      const note = document.getElementById('train-live-note');
      if (startScreen === 'today' && note) {
        note.hidden = false;
        note.textContent = `Could not start recording: ${reason}`;
      } else {
        NS.analysisFailed(reason);
      }
      return;
    }
    LIVE.seq = 0; LIVE.failed = false; LIVE.rows = []; LIVE.failureStatus = null; LIVE.queue = Promise.resolve();
    LIVE.pending = new Map(); LIVE.finishPending = true; LIVE.generation++;
    /* The live training button is also on the 'Today' screen, and the recorder lives
       inside scr-record. We do not start a hidden recording: after camera permission and
       successful job creation we first open a visible screen. */
    if (NS.currentScreen !== 'record') NS.go('record');
    vid.srcObject = LIVE.stream; box.hidden = false;
    try {
      LIVE.rec = new MediaRecorder(LIVE.stream, LIVE.mime ? { mimeType: LIVE.mime, videoBitsPerSecond: 8_000_000 } : undefined);
    } catch (_) {
      LIVE.finishPending = false; liveTeardown();
      NS.analysisFailed('The browser could not start recording. Use the system camera.');
      return;
    }
    const generation = LIVE.generation;
    LIVE.rec.ondataavailable = (ev) => {
      if (generation !== LIVE.generation || !ev.data || !ev.data.size) return;
      const seq = LIVE.seq++;
      const blob = ev.data;
      LIVE.pending.set(seq, blob);
      LIVE.queue = LIVE.queue.then(async () => {
        if (generation !== LIVE.generation || LIVE.failed) return;
        if (!await liveSendPart(seq, blob, generation)) {
          LIVE.failed = true;
          // Stop outside the queue: liveStop itself waits for this queue to finish.
          setTimeout(() => { if (generation === LIVE.generation) liveStop(); }, 0);
        }
      });
      // Stop the camera on backlog, keeping the blobs already received in the tab.
      if ([...LIVE.pending.values()].reduce((n, b) => n + b.size, 0) > 32 * 1048576) {
        setTimeout(() => { if (generation === LIVE.generation) liveStop(); }, 0);
      }
    };
    LIVE.rec.onerror = () => liveStop();
    LIVE.stream.getVideoTracks().forEach(track => track.onended = () => liveStop());
    LIVE.t0 = Date.now();
    LIVE.found = null;
    { const h = document.getElementById('live-hero'); if (h) h.hidden = true; const fr = document.getElementById('live-feed-rows'); if (fr) fr.innerHTML = ''; }
    const pollContext = { job: LIVE.job, owner: LIVE.owner, generation: LIVE.generation,
      pending: LIVE.pending, rec: LIVE.rec };
    const pollCurrent = () => LIVE.job === pollContext.job && LIVE.generation === pollContext.generation
      && LIVE.pending === pollContext.pending && LIVE.rec === pollContext.rec && !!LIVE.rec
      && NS.jobOwnerCurrent(pollContext.owner);
    LIVE.poll = setInterval(async () => {
      /* how many jumps the previous run has already found */
      if (!pollCurrent()) return;
      try {
        const r = await fetch(`/status/${pollContext.job}`);
        if (!pollCurrent() || !r.ok) return;
        const s = await r.json();
        if (!pollCurrent()) return;
        /* The server may be older than the client, so we do not print the server's reason */
        const liveWarning = s.live_warning || (s.live_degraded
          ? 'Live analysis is incomplete. The full recording will be checked after stopping.'
          : '');
        if (liveWarning) {
          const note = document.getElementById('live-rec-net');
          if (note) note.textContent = liveWarning;
        }
        if (s.state === 'recording' && s.found != null) {
          LIVE.found = s.found;
          LIVE.rows = s.live || [];
          renderLiveFeed(s);
          const n = document.getElementById('live-rec-net');
          const last = (s.live && s.live.length) ? s.live[s.live.length - 1] : null;
          if (n && !liveWarning) n.textContent = `jumps found: ${s.found}`
                              + (!s.live_state && s.preview_state && s.preview_state !== 'done' ? ' · …' : '');
        }
      } catch (_) { }
    }, 3000);
    LIVE.timer = setInterval(() => {
      const s = Math.floor((Date.now() - LIVE.t0) / 1000);
      const el = document.getElementById('live-rec-timer');
      if (el) el.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
      if (s >= 600) liveStop();                      // ceiling of 10 min
    }, 500);
    /* Chunk size 2 s. The live scan on the server lags the recording by
       at least one chunk; on the simulator the first live name appeared
       after 17–19 s with 4 s chunks, half of that lag being the chunk size itself. */
    try { LIVE.rec.start(2000); }
    catch (_) {
      LIVE.rec = null; LIVE.finishPending = false; liveTeardown();
      NS.analysisFailed('Recording did not start. Use the system camera.');
    }
  }

  /* After 'Stop' the person is not left on an empty screen:
     we show what was found DURING recording, with an honest caption
     'preliminary'; exact numbers are filled in by the full analysis in 15–40 s. */
  function renderLivePreview(rows) {
    const host = document.getElementById('rec-waiting');
    if (!host) return;
    let box = document.getElementById('live-preview');
    if (!rows || !rows.length) { if (box) box.remove(); return; }
    if (!box) {
      box = document.createElement('div');
      box.id = 'live-preview';
      box.className = 'card card--pad live-preview';
      /* right under the wait caption, not at the end of the screen, otherwise
         the most valuable thing (what is already found) sits below the fold */
      const anchor = document.getElementById('wait-eta');
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor.nextSibling);
      else host.appendChild(box);
    }
    const items = rows.slice(-6).map(r => {
      const t = (typeof r.t_s === 'number') ? `${r.time_source === 'frame_rate_estimate' ? '≈ ' : ''}${r.t_s.toFixed(1)} s` : '';
      const name = r.state === 'done' ? liveName(r) : 'jump found';
      const turns = r.state === 'done' ? liveTurns(r, { 1: 'single', 2: 'double', 3: 'triple', 4: 'quad' }) : '';
      const rev = turns ? ` · ${turns}` : '';
      return `<div class="live-preview__row">
        <span class="live-preview__name">${liveEsc(name)}${rev}</span>
        <span class="live-preview__time mono">${t}</span></div>`;
    }).join('');
    box.innerHTML = `<div class="eyebrow">FOUND WHILE RECORDING · PRELIMINARY</div>
      <div class="live-preview__list">${items}</div>
      <div class="sub-dim live-preview__note">${
        'Name, air time and errors follow in a few seconds, once the full analysis finishes. Rotations — if the footage allows counting them.'}</div>`;
  }

  function liveEsc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /* A preliminary live line must not turn an estimate into a fact. The final
     mapper already hides the raw name when the engine set name_uncertain; here
     we must apply the same rule to the preview, hero and voice. */
  function liveName(row) {
    const uncertain = [true, 'true', 'True'].includes(row && row.name_uncertain);
    const raw = row && (row.name_display || (!uncertain && row.name));
    return raw ? (NS.jumpPairLocal(raw) || NS.jumpNameLocal(raw) || raw)
      : 'name not resolved';
  }

  function liveTurns(row, counts) {
    if (!row || row.rev_usable === false || !Number.isFinite(row.turns)) return '';
    const estimated = [true, 'true', 'True'].includes(row.turns_estimated)
      || [true, 'true', 'True'].includes(row.count_estimated);
    return `${estimated ? '≈ ' : ''}${counts[row.turns] || row.turns}`;
  }

  function liveNeedsReview(row, coach) {
    return !!(row && (row.needs_review || row.rev_usable === false
      || [true, 'true', 'True'].includes(row.turns_estimated)
      || [true, 'true', 'True'].includes(row.count_estimated)))
      || !!(coach && ['await_final', 'insufficient'].includes(coach.state));
  }

  function liveTrustedErrors(row) {
    const tiers = row.errors_conf || {};
    return (Array.isArray(row.errors) ? row.errors : []).filter(code =>
      ['medium', 'high'].includes(String(tiers[code] || 'low').toLowerCase()));
  }

  /* LIVE ATTEMPT STRIP on the camera screen: each attempt is a row as soon as
     the engine sees it; the name and verdict fill in as soon as they are ready. */
  function renderLiveFeed(s) {
    const head = document.getElementById('live-feed-head');
    const box = document.getElementById('live-feed-rows');
    if (!head || !box) return;
    const rows = (s.live || []).slice().reverse();
    const cnt = { 1: 'single', 2: 'double', 3: 'triple', 4: 'quad' };
    /* Scan progress is measured; time to the first result depends on the recording,
       the network and the device. A separate run does not set a promise for all sessions. */
    const seen = typeof s.scanned_s === 'number' ? `${Math.floor(s.scanned_s / 60)}:${String(Math.floor(s.scanned_s % 60)).padStart(2, '0')}` : '';
    head.textContent = s.found
      ? `Jumps: ${s.found}` + (s.pending_analyzes ? ' · ' + 'analysing…' : '') + (seen ? ' · ' + `scanned to ${seen}` : '')
      : (seen ? `No jumps yet · scanned to ${seen}`
              : 'Skate — analysing the recording. Attempts and cues will appear here.');
    /* hero: the last attempt in large type */
    const hero = document.getElementById('live-hero');
    const hn = document.getElementById('live-hero-name');
    const hv = document.getElementById('live-hero-verdict');
    const hc = document.getElementById('live-hero-cue');
    const last = rows.find(r => r.state !== 'no_jump') || null;
    /* 'I see a jump' comes before the name: the server gives the landing of
       unclosed candidates (open_seen), about 5 s before the finished name. We do not guess the name:
       an early threshold gave a false one (tools/live_latency). */
    const openSeen = Array.isArray(s.open_seen) ? s.open_seen : [];
    const lastLand = last ? (Number.isFinite(last.landing_s) ? last.landing_s : (last.t_s ?? -1)) : -1;
    const newestSeen = openSeen.length ? openSeen[openSeen.length - 1] : null;
    if (hero && hn && hv && newestSeen !== null && newestSeen > lastLand + 0.5) {
      hero.hidden = false;
      /* the bounds of an unclosed candidate still 'drift' (9.64 -> 9.70 -> 10.69 s on
         one jump): one signal per jump, not per refinement */
      const prevSeen = Number(hero.dataset.seenAt);
      if (!(Number.isFinite(prevSeen) && Math.abs(newestSeen - prevSeen) < 1.5)) {
        hero.dataset.seenAt = String(newestSeen);
        hero.dataset.resultKey = 'seen:' + newestSeen.toFixed(1);
        hero.classList.remove('is-fresh'); void hero.offsetWidth; hero.classList.add('is-fresh');
        liveChime('found');
      }
      hn.textContent = 'Jump found';
      hv.className = 'live__hero-verdict is-wait';
      hv.textContent = 'analysing…';
      if (hc) hc.hidden = true;
    } else if (hero && hn && hv) {
      hero.hidden = !last;
      if (last) {
        const resultKey = JSON.stringify([last.t_s, last.state, liveName(last),
          liveTurns(last, cnt), liveNeedsReview(last, last.coach),
          last.coach && last.coach.state, last.coach && last.coach.text,
          Array.isArray(last.errors) ? last.errors : []]);
        const fresh = hero.dataset.resultKey !== resultKey;
        if (fresh) {
          hero.dataset.resultKey = resultKey;
          hero.classList.remove('is-fresh');
          void hero.offsetWidth;
          hero.classList.add('is-fresh');
          /* jump noticed, analysis still running: a short 'I see it' signal */
          if (last.state !== 'done' && last.state !== 'error') liveChime('found');
        }
        if (last.state === 'done') {
          const nm = liveName(last);
          const tn = liveTurns(last, cnt);
          const full = [tn, nm].filter(Boolean).join(' ');
          hn.textContent = full ? full[0].toUpperCase() + full.slice(1) : 'Jump';
          const errs = Array.isArray(last.errors) ? last.errors : [];
          const trustedErrors = liveTrustedErrors(last);
          const coach = last.coach || {};
          const coachText = coach.text || '';
          const pendingReview = liveNeedsReview(last, coach);
          const clean = coach.state === 'clean' && !pendingReview && !errs.length;
          hv.className = 'live__hero-verdict ' + (trustedErrors.length ? 'is-bad' : (clean ? 'is-clean' : 'is-wait'));
          const errTxt = (trustedErrors.length ? trustedErrors : errs).map(e => (NS.ERR_UA[e] ? NS.ERR_UA[e][0] : e)).slice(0, 2).join(' · ');
          hv.textContent = clean ? 'No errors detected'
            : (trustedErrors.length ? errTxt : errs.length
              ? `Possible: ${errTxt} (not certain)`
              : 'Still checking your form…');
          if (hc) {
            hc.hidden = !coachText;
            hc.className = 'live__hero-cue' + (coach.state === 'action' ? '' : ' is-wait');
            hc.textContent = coachText;
          }
          /* verdict ready: signal and voice, only when it is truly new
             (the same status line arrives once per second) */
          if (fresh && hero.dataset.spoken !== resultKey) {
            hero.dataset.spoken = resultKey;
            liveChime(clean ? 'clean' : (coach.state === 'action' ? 'bad' : 'found'),
              () => hero.dataset.resultKey === resultKey);
            const spokenText = `${hn.textContent}. ${coachText || hv.textContent}`;
            setTimeout(() => {
              if (hero.dataset.resultKey === resultKey) liveSay(spokenText);
            }, 380);
          }
        } else if (last.state === 'error') {
          hn.textContent = 'Attempt'; hv.className = 'live__hero-verdict is-wait'; hv.textContent = 'could not analyse'; if (hc) hc.hidden = true;
        } else {
          hn.textContent = 'Jump found'; hv.className = 'live__hero-verdict is-wait'; hv.textContent = 'analysing…'; if (hc) hc.hidden = true;
        }
      }
    }
    const newestKey = rows.length ? [rows[0].t_s, rows[0].state, rows[0].name_display || rows[0].name].join('|') : '';
    const previousKey = box.dataset.newestKey || '';
    box.dataset.newestKey = newestKey;
    box.innerHTML = rows.slice(0, 8).map((r, index) => {
      const t = typeof r.t_s === 'number' ? `${r.time_source === 'frame_rate_estimate' ? '≈ ' : ''}${Math.floor(r.t_s / 60)}:${String(Math.floor(r.t_s % 60)).padStart(2, '0')}` : '';
      let name = '', chip = '';
      if (r.state === 'done') {
        const nm = liveName(r);
        const tn = liveTurns(r, cnt);
        name = [tn, nm].filter(Boolean).join(' ');
        const errs = Array.isArray(r.errors) ? r.errors : [];
        const trustedErrors = liveTrustedErrors(r);
        const coach = r.coach || {};
        if (coach.state === 'clean' && !liveNeedsReview(r, coach) && !errs.length) chip = `<span class="live__feed-chip is-clean">no errors detected</span>`;
        else if (trustedErrors.length) chip = `<span class="live__feed-chip is-bad">${liveEsc(trustedErrors.map(e => (NS.ERR_UA[e] ? NS.ERR_UA[e][0] : e)).slice(0, 2).join(', '))}</span>`;
        else if (errs.length) chip = `<span class="live__feed-chip is-wait">possible issue, not certain</span>`;
        else if (coach.state === 'await_final' || coach.state === 'insufficient') chip = `<span class="live__feed-chip is-wait">confirming…</span>`;
        else chip = `<span class="live__feed-chip is-wait">checking…</span>`;
      } else if (r.state === 'no_jump') { name = 'not confirmed'; chip = ''; }
      else if (r.state === 'error') { name = 'could not analyse'; }
      else { name = 'jump found'; chip = `<span class="live__feed-chip is-wait">analysing…</span>`; }
      const fresh = index === 0 && newestKey && newestKey !== previousKey ? ' is-new' : '';
      return `<div class="live__feed-row${fresh}">
        <span class="live__feed-name">${liveEsc(name)}</span>
        <span class="live__feed-meta">${chip}${t ? ` <span class="live__feed-time">${t}</span>` : ''}</span></div>`;
    }).join('');
  }

  function liveTeardown() {
    clearInterval(LIVE.timer); clearInterval(LIVE.poll);
    try { LIVE.stream && LIVE.stream.getTracks().forEach(t => t.stop()); } catch (_) { }
    LIVE.stream = null;
    const box = document.getElementById('live-rec'); if (box) box.hidden = true;
    const vid = document.getElementById('live-rec-video'); if (vid) vid.srcObject = null;
  }

  async function liveStop() {
    if (!LIVE.rec) return;
    const rec = LIVE.rec; LIVE.rec = null;
    const dur = LIVE.duration = (Date.now() - LIVE.t0) / 1000;
    await new Promise(res => { rec.onstop = res; try { rec.stop(); } catch (_) { res(); } });
    liveTeardown();
    document.getElementById('rec-intro').hidden = true;
    document.getElementById('rec-waiting').hidden = false;
    NS.resetWaitLoop(); NS.resetWaitAsk(false);      /* the previous upload's state must not show through */
    NS.setWaitEta(dur);
    renderLivePreview(LIVE.rows);
    await LIVE.queue;                                // wait for the last part
    if (LIVE.failed || LIVE.pending.size) { liveUploadFailed(); return; }
    await liveFinish();
  }

  async function liveSendPart(seq, blob, generation) {
    const job = LIVE.job, pending = LIVE.pending;
    for (let attempt = 0; attempt < 3; attempt++) {
      if (generation !== LIVE.generation) return false;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 20000);
      try {
        const res = await fetch(`/upload_part/${job}?seq=${seq}`, { method: 'POST', body: blob,
          signal: controller.signal, headers: { 'Content-Type': 'application/octet-stream' } });
        if (res.ok) {
          const result = await res.json();
          if (result.ok !== true || !(result.parts > seq)) throw new Error('missing acknowledgement');
          pending.delete(seq);
          const n = document.getElementById('live-rec-net');
          if (n && generation === LIVE.generation) n.textContent = `sent ${(result.bytes / 1048576).toFixed(1)} MB`;
          return true;
        }
        LIVE.failureStatus = res.status;
        if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) return false;
      } catch (_) { }
      finally { clearTimeout(timeout); }
      if (attempt < 2) await new Promise(r => setTimeout(r, 1500));
    }
    return false;
  }

  function liveUploadFailed() {
    const reason = LIVE.failureStatus === 422 ? 'The server cannot read the video or it is too long. '
      : LIVE.failureStatus === 413 ? 'The recording exceeds the server size limit. ' : '';
    NS.analysisFailed(reason + 'Recording stopped. Unsent parts are kept only in this tab. Retry sending or discard the recording; do not close or reload the page.',
      'Recording has not been sent yet');
    const retry = document.getElementById('btn-retry-analysis');
    retry.hidden = false; retry.disabled = false;
    retry.textContent = 'Retry sending';
    const discard = document.getElementById('btn-discard-live');
    discard.hidden = false;
    discard.textContent = 'Discard this recording';
    discard.onclick = () => {
      if (LIVE.retrying) return;
      if (!window.confirm('Unsent parts will be lost. Discard the recording?')) return;
      liveCancel();
      document.getElementById('rec-fail-note').hidden = true;
    };
    retry.onclick = async () => {
      if (LIVE.retrying) return;
      LIVE.retrying = true; retry.disabled = true; discard.disabled = true;
      try {
        await LIVE.queue;
        const generation = LIVE.generation;
        for (const [seq, blob] of LIVE.pending) {
          if (!await liveSendPart(seq, blob, generation)) { liveUploadFailed(); return; }
        }
        LIVE.failed = false;
        LIVE.failureStatus = null;
        NS.prepareWaiting('');
        await liveFinish();
      } finally { LIVE.retrying = false; retry.disabled = false; discard.disabled = false; }
    };
  }

  async function liveFinish() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const res = await fetch(`/upload_finish/${LIVE.job}?duration_s=${LIVE.duration.toFixed(2)}`, { method: 'POST', signal: controller.signal });
      if (!res.ok) { LIVE.failureStatus = res.status; throw new Error(`HTTP ${res.status}`); }
      const result = await res.json();
      if (result.job !== LIVE.job) throw new Error('invalid job');
      LIVE.finishPending = false;
      NS.watchJob(result.job);
    } catch (_) { liveUploadFailed(); }
    finally { clearTimeout(timeout); }
  }

  function liveCancel() {
    LIVE.generation++; LIVE.pending.clear(); LIVE.finishPending = false;
    if (LIVE.rec) { try { LIVE.rec.stop(); } catch (_) { } LIVE.rec = null; }
    liveTeardown();
  }

  window.addEventListener('beforeunload', event => {
    if (LIVE.rec || LIVE.finishPending) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && LIVE.rec) liveStop();
  });

  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('btn-live-rec');
    const ok = !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    if (b) { b.hidden = !ok; b.addEventListener('click', liveStart); }
    const tl = document.getElementById('btn-train-live');
    const note = document.getElementById('train-live-note');
    if (tl) tl.addEventListener('click', () => {
      if (ok) { liveStart(); return; }
      const insecure = location.protocol !== 'https:' && !/^(localhost|127\.0\.0\.1)$/.test(location.hostname);
      if (note) {
        note.hidden = false;
        note.textContent = insecure
          ? 'The browser camera requires HTTPS. Open the secure service address or upload a video from the system camera.'
          : 'This browser cannot record video. Use “Record now” under Analyse.';
      }
    });
    const s = document.getElementById('btn-live-stop'); if (s) s.addEventListener('click', liveStop);
    const c = document.getElementById('btn-live-cancel'); if (c) c.addEventListener('click', liveCancel);
  });

  Object.assign(NS, {
     LIVE, liveStart, stopStartingStream, renderLivePreview, renderLiveFeed, liveStop, liveUploadFailed,
  });
})();
