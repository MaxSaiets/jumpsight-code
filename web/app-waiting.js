/* Waiting screen, pending-job storage, job watching and status polling. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* The step list reads the REAL server stages (jumpsight → probe →
     pose → verdict) and the live total/done counters from /status. The labels
     are never invented, and found attempts are shown. One row, one fact.
     Instead of a static 'queued / checking…', live rows from measured
     events: what we are searching for now, how many jumps were found and where (from
     /status.early), 'measuring…'. Future steps are empty, with no 'queued'.
     Stage time only if the server sent it (timing.jumpsight). */
  function stageFoundText(s, oneKey, manyKey, countKey) {
    const early = s && s.early, win = earlyWindow(early);
    const n = early && Number.isFinite(Number(early.attempts)) ? Number(early.attempts) : (Number(s && s.total) || 0);
    if (win && n >= 1)
      return (n > 1 ? TX(manyKey).replace('{n}', String(n)) : TX(oneKey)).replace('{t}', fmtAt(win[0]));
    if (n >= 1) return TX(countKey).replace('{n}', String(n));
    return null;
  }
  function updateStageVisuals(stageNum, s = {}) {
    const ids = [['stg-1-icon', 'stg-attempts-val'], ['stg-2-icon', 'stg-2-val'],
                 ['stg-3-icon', 'stg-3-val'], ['stg-4-icon', 'stg-4-val']];
    const doing = [TX('stgValReading'), TX('stgValLooking'), TX('stgValMeasuring'), TX('stgValDone')];
    const early = s.early && typeof s.early === 'object' ? s.early : null;
    const found = stageFoundText(s, 'stgValFound1', 'stgValFoundN', 'stgValFoundCount')
      || (early && Number(early.attempts) === 0 ? TX('stgValNone') : null);
    const took = s.timing && Number.isFinite(Number(s.timing.jumpsight)) && Number(s.timing.jumpsight) > 0
      ? TX('stgValTook').replace('{s}', Number(s.timing.jumpsight).toFixed(1)) : null;
    ids.forEach(([icId, vId], i) => {
      const ic = document.getElementById(icId), v = document.getElementById(vId);
      if (!ic || !v) return;
      let icon = '○', txt = '', color = '';
      if (i < stageNum) {
        icon = '✓'; color = 'var(--clean)';
        txt = i === 1 && found ? found : '';
      } else if (i === stageNum) {
        icon = i === 3 ? '✓' : '●'; color = i === 3 ? 'var(--clean)' : 'var(--action)';
        txt = i === 3 && took ? `${doing[i]} · ${took}` : doing[i];
      }
      ic.textContent = icon; ic.style.color = color;
      v.textContent = txt; v.style.color = color;
    });
  }

  /* Live stage heading: a row from what the server has already measured. */
  function liveStageTitle(s) {
    if (s.state === 'done') return TX('waitLiveDone');
    if (s.stage === 'jumpsight') return TX('waitLiveReading');
    if (s.stage === 'probe') return TX('waitLiveLooking');
    if (s.stage === 'pose') return stageFoundText(s, 'waitLiveFound1', 'waitLiveFoundN', 'waitLiveFoundCount') || TX('waitLivePreparing');
    if (s.stage === 'verdict') return TX('waitLiveMeasuring');
    return null;
  }

  /* Human explanations of silent failures instead of raw keys. */
  const WARN_TEXT = {
    jumpsight_error: ['the fast engine failed, the backup engine answered (slower)'],
    e2e_error: ['the backup engine could not handle this video either'],
    preload_error: ['the video could not be fully prepared'],
    spins_error: ['spins were not counted'],
  };

  /* Live events instead of polling every 400 ms. The same
     state handler as in pollJob, only the source differs. A drop or absence of
     EventSource falls back to pollJob. */
  function stopWatching() {
    NS.watcherEpoch++;
    if (NS.eventSource) NS.eventSource.close();
    NS.eventSource = null;
    clearTimeout(NS.watcherTimer);
    if (NS.statusRequest) NS.statusRequest.abort();
    NS.statusRequest = null;
    NS.activeJobId = null;
    NS.activeJobOwner = null;
  }

  /* The wait preview plays by itself: muted and
     playsinline allow autoplay in mobile browsers, and an explicit play()
     after loadeddata is needed because src is set from JS. If the browser
     forbids it (saver mode, policy), an honest ▶ button remains. */
  function startWaitPreview(vid) {
    const btn = document.getElementById('btn-wait-play');
    vid.muted = true; vid.defaultMuted = true; vid.loop = true; vid.playsInline = true;
    const tryPlay = () => {
      if (vid.hidden || !vid.src) return;
      const p = vid.play();
      if (p && typeof p.then === 'function') {
        p.then(() => { if (btn) btn.hidden = true; })
         .catch(() => { if (btn && vid.paused) btn.hidden = false; });
      }
    };
    if (btn) {
      btn.hidden = true;
      btn.onclick = () => { vid.play().then(() => { btn.hidden = true; }).catch(() => { }); };
    }
    vid.onplaying = () => { if (btn) btn.hidden = true; };
    if (vid.readyState >= 2) tryPlay();
    else vid.addEventListener('loadeddata', tryPlay, { once: true });
  }

  /* EARLY MEASURED NUMBERS. The engine knows the attempt window from
     attempts.confirmed and the flight time from attempt.timing, long before the full
     answer. The server puts them in /status.early; here the preview seeks to the
     window and plays only it, slowed down, with 'Jump found at 0:07' under it
     and the 'In the air' tile. Only what arrived in early is shown. */
  const TX = k => (window.TEXT ? window.TEXT.t(k) : '');
  const WAIT_LOOP = { win: null, key: null };
  function waitLoopTick() {
    const v = document.getElementById('wait-live-video'), w = WAIT_LOOP.win;
    if (!v || !w) return;
    if (v.currentTime >= w[1] || v.currentTime < w[0] - 0.25) v.currentTime = w[0];
  }
  function resetWaitLoop() {
    WAIT_LOOP.win = null; WAIT_LOOP.key = null;
    const v = document.getElementById('wait-live-video');
    if (v) { v.removeEventListener('timeupdate', waitLoopTick); v.playbackRate = 1; }
    const box = document.getElementById('wait-early'); if (box) box.hidden = true;
    const air = document.getElementById('wait-early-air'); if (air) air.hidden = true;
    const bt = document.getElementById('wait-vid-badge-text');
    if (bt) { delete bt.dataset.live; bt.textContent = TX('s008'); }
  }
  function startWaitLoop(win) {
    const v = document.getElementById('wait-live-video');
    const vbox = v && v.closest('.rz-video');
    if (!v || !v.getAttribute('src') || (vbox && vbox.hidden)) return;
    const key = win.join('-');
    if (WAIT_LOOP.key === key) return;
    WAIT_LOOP.key = key;
    const apply = () => {
      if (WAIT_LOOP.key !== key) return;
      const d = v.duration;
      if (Number.isFinite(d) && win[0] >= d) return;     /* window is outside the preview file */
      WAIT_LOOP.win = [win[0], Number.isFinite(d) ? Math.min(win[1], d) : win[1]];
      v.playbackRate = 0.5;
      v.removeEventListener('timeupdate', waitLoopTick);
      v.addEventListener('timeupdate', waitLoopTick);
      try { v.currentTime = win[0]; } catch (_) { }
      const bt = document.getElementById('wait-vid-badge-text');
      if (bt) { bt.textContent = TX('waitEarlyLoop'); bt.dataset.live = '1'; }
    };
    if (v.readyState >= 1) apply(); else v.addEventListener('loadedmetadata', apply, { once: true });
  }
  /* '0:07' is the second at which the window starts (downward, like a player clock) */
  const fmtAt = sec => {
    const n = Math.max(0, Math.floor(Number(sec) || 0));
    return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  };
  function earlyWindow(early) {
    const w = early && early.first_window_s;
    return Array.isArray(w) && w.length === 2 && w.every(Number.isFinite) && w[1] > w[0] && w[0] >= 0 ? w : null;
  }
  function paintEarly(early) {
    if (!early || typeof early !== 'object') return;
    const n = Number(early.attempts), win = earlyWindow(early);
    const box = document.getElementById('wait-early'), found = document.getElementById('wait-early-found');
    if (!win || !(n >= 1) || !box || !found) return;
    found.textContent = (n > 1 ? TX('waitEarlyFoundMany').replace('{n}', String(n)) : TX('waitEarlyFound'))
      .replace('{t}', fmtAt(win[0]));
    box.hidden = false;
    startWaitLoop(win);
    const air = Number(early.air_s), airBox = document.getElementById('wait-early-air');
    if (airBox && Number.isFinite(air) && air > 0) {
      document.getElementById('wait-early-air-v').textContent = `${air.toFixed(2)} s`;
      airBox.hidden = false;
    }
  }

  /* 'What did you jump?' for the wait time. The same options as
     'Which jump was it?' on the answer (verdict_feedback keys). The answer
     is kept in memory and goes as a pre_reveal label along the same route as soon as
     the server names the stem of the first attempt shown (sendWaitAnswer). */
  const ASK_JUMPS = [['axel', 'Axel'], ['salchow', 'Salchow'],
                     ['toe_loop', 'Toe loop'], ['loop', 'Loop'],
                     ['flip', 'Flip'], ['lutz', 'Lutz']];
  const WAIT_ASK = { job: null, upload: 0, jump: null, turns: null };
  function askLabel(jump, turns) {
    const j = ASK_JUMPS.find(x => x[0] === jump);
    return (j ? (j[1]) : String(jump || '')) + (turns ? ` · ${turns}` : '');
  }
  function paintWaitAsk() {
    const jb = document.getElementById('wait-ask-jumps'), tb = document.getElementById('wait-ask-turns');
    if (!jb || !tb) return;
    jb.innerHTML = ASK_JUMPS.map(([k, en]) =>
      `<button type="button" class="rz-chip${WAIT_ASK.jump === k ? ' is-on' : ''}" data-ask-jump="${k}" aria-pressed="${WAIT_ASK.jump === k}">${en}</button>`).join('');
    tb.innerHTML = [1, 2, 3, 4].map(n =>
      `<button type="button" class="rz-chip${WAIT_ASK.turns === n ? ' is-on' : ''}" data-ask-turns="${n}" aria-pressed="${WAIT_ASK.turns === n}">${n}</button>`).join('');
    document.getElementById('wait-ask-turns-box').hidden = !WAIT_ASK.jump;
    const saved = document.getElementById('wait-ask-saved');
    if (saved) {
      saved.hidden = !WAIT_ASK.jump;
      saved.textContent = WAIT_ASK.jump ? TX('waitAskSaved').replace('{j}', askLabel(WAIT_ASK.jump, WAIT_ASK.turns)) : '';
    }
    jb.querySelectorAll('[data-ask-jump]').forEach(b => {
      b.onclick = () => {
        const k = b.getAttribute('data-ask-jump');
        WAIT_ASK.jump = WAIT_ASK.jump === k ? null : k;      /* a repeated tap clears the choice */
        if (!WAIT_ASK.jump) WAIT_ASK.turns = null;
        paintWaitAsk();
      };
    });
    tb.querySelectorAll('[data-ask-turns]').forEach(b => {
      b.onclick = () => {
        const n = parseInt(b.getAttribute('data-ask-turns'), 10);
        WAIT_ASK.turns = WAIT_ASK.turns === n ? null : n;
        paintWaitAsk();
      };
    });
  }
  /* show=false: the jump is already declared before upload (the label will come from
     the server), or this is not a fresh file upload: we do not duplicate the form */
  function resetWaitAsk(show = false, upload = 0) {
    WAIT_ASK.job = null; WAIT_ASK.upload = upload; WAIT_ASK.jump = null; WAIT_ASK.turns = null;
    const box = document.getElementById('wait-ask');
    if (box) box.hidden = !show;
    if (show) paintWaitAsk();
  }
  /* After readiness: a pre_reveal label for the attempt shown first (the same
     choice the server makes for the declaration: the smallest rank among the ready ones) */
  async function sendWaitAnswer(jobId, rows, mapped) {
    if (WAIT_ASK.job !== jobId || !WAIT_ASK.jump) return;
    const ans = { jump: WAIT_ASK.jump, turns: WAIT_ASK.turns };
    WAIT_ASK.job = null;
    const rankOf = r => (Number.isInteger(r.rank) ? r.rank : 99);
    const top = (rows || []).filter(r => r && r.state === 'done' && typeof r.stem === 'string' && r.stem)
      .sort((a, b) => rankOf(a) - rankOf(b))[0];
    if (!top) return;
    const ctl = new AbortController();
    const tm = setTimeout(() => ctl.abort(), 4000);
    try {
      const r = await fetch('/coach/verdict_feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctl.signal,
        body: JSON.stringify({ stem: top.stem, jump: ans.jump, turns: ans.turns, source: 'pre_reveal' }) });
      const d = r.ok ? await r.json() : null;
      if (d && d.ok) {
        /* this attempt's quick 'Yes/No' row is already answered; otherwise
           the label after display would overwrite the valuable label before display */
        try { localStorage.setItem('js.vc.' + top.stem, '1'); } catch (_) { }
        const att = (mapped || []).find(m => m && m.stem === top.stem);
        if (att) att.preRevealLabel = ans;
      }
    } catch (_) { /* offline does not block the measurement display */ }
    finally { clearTimeout(tm); }
  }

  function prepareWaiting(name) {
    resetWaitLoop();
    resetWaitAsk(false);
    document.getElementById('rec-intro').hidden = true;
    document.getElementById('rec-waiting').hidden = false;
    document.getElementById('rec-fail-note').hidden = true;
    document.getElementById('rec-waiting').setAttribute('aria-busy', 'true');
    const fileName = document.getElementById('wait-file-name');
    fileName.textContent = name || ''; fileName.hidden = !name;
    document.getElementById('wait-title').focus();
    const bar = document.getElementById('wait-prog-bar');
    bar.classList.add('is-indeterminate');
    bar.style.background = ''; bar.style.transform = '';
    document.getElementById('wait-stage-name').textContent = 'Uploading video';
    /* the previous task's state must not show through under the new video */
    const wv = document.getElementById('wait-warn'); if (wv) { wv.hidden = true; wv.textContent = ''; }
    /* the preview exists only for the file just selected; after a reload
       there is no blob URL, so an empty player box is pointless */
    const pv = document.getElementById('wait-live-video');
    const pbox = pv && pv.closest('.rz-video');
    if (pbox) pbox.hidden = true;
    updateStageVisuals(-1);
    NS.setWaitEta(null);
    startWaitClock();
  }

  function analysisSessionReady() {
    return !!(typeof NS.readyMeUid === 'string' && NS.readyMeUid && NS.ME && NS.ME.uid === NS.readyMeUid && NS.readyMeEpoch === NS.meRequestEpoch);
  }

  function jobOwnerCurrent(owner) {
    /* An accepted job survives a same-UID refresh and a temporary null ME. */
    return !!(owner && owner.ownerUid === NS.commentDraftOwner && owner.generation === NS.identityGeneration);
  }

  function pendingRecord(raw) {
    let record;
    try { record = JSON.parse(raw); } catch (_) { return null; }
    return record && record.version === 1 && typeof record.job === 'string'
      && /^[A-Za-z0-9_-]+$/.test(record.job) && typeof record.name === 'string'
      && typeof record.ownerUid === 'string' && record.ownerUid ? record : null;
  }

  const pendingStorageWarning = () => 'This analysis is running, but it will not resume automatically after a reload. Open the completed result in this profile’s history.';

  function savePendingJob(jobId, owner, pendingRaw) {
    let saved = false;
    if (owner) try {
      const raw = sessionStorage.getItem('js.pendingJob');
      const previous = pendingRecord(raw);
      if (raw !== null && !(previous && previous.job === jobId && previous.ownerUid === owner.ownerUid)) {
        const archiveRaw = sessionStorage.getItem('js.pendingJobQuarantine');
        const archive = archiveRaw === null ? [] : JSON.parse(archiveRaw);
        if (!Array.isArray(archive) || !archive.every(value => typeof value === 'string')) throw new Error('unknown pending archive');
        if (!archive.includes(raw)) archive.push(raw);
        /* Archive before overwrite: even an empty or invalid raw is not lost. */
        sessionStorage.setItem('js.pendingJobQuarantine', JSON.stringify(archive));
      }
      sessionStorage.setItem('js.pendingJob', pendingRaw ?? JSON.stringify({
        version: 1, job: jobId, name: owner.name, ownerUid: owner.ownerUid
      }));
      saved = true;
    } catch (_) { }
    WAIT.persistenceUnavailable = !saved;
    if (!saved) {
      NS.notice(pendingStorageWarning(), 8000);
      const warning = document.getElementById('wait-warn');
      if (warning) { warning.textContent = pendingStorageWarning(); warning.hidden = false; }
    }
  }

  function clearPendingJob(jobId, owner) {
    if (!jobId || !jobOwnerCurrent(owner)) return;
    try {
      const record = pendingRecord(sessionStorage.getItem('js.pendingJob'));
      if (record && record.job === jobId && record.ownerUid === owner.ownerUid) sessionStorage.removeItem('js.pendingJob');
    } catch (_) { }
  }

  function restorePendingJob(uid) {
    /* Only the current successful /me after guest bootstrap may restore
       the bound record. Reading someone else's /status does not prove ownership. */
    if (!NS.ME || NS.ME.uid !== uid || NS.activeJobId || NS.uploadInFlight || NS.LIVE.starting || NS.LIVE.rec || NS.LIVE.finishPending) return;
    let raw;
    try { raw = sessionStorage.getItem('js.pendingJob'); } catch (_) { return; }
    if (raw === null) return;
    const pending = pendingRecord(raw);
    if (!pending || pending.ownerUid !== uid) {
      /* Entries without a stamp stay in storage, with no cancel or display
         of a foreign file name. */
      NS.notice('The previous analysis was not resumed automatically. Open the completed result in the history of the profile that uploaded it.', 8000);
      return;
    }
    prepareWaiting(pending.name);
    watchJob(pending.job, { owner: { ownerUid: uid, generation: NS.identityGeneration, name: pending.name }, pendingRaw: raw });
  }

  function watchJob(jobId, { owner = null, pendingRaw = null } = {}) {
    if (owner && !jobOwnerCurrent(owner)) return;
    stopWatching();
    NS.activeJobId = jobId; NS.retryJobId = jobId;
    NS.activeJobOwner = owner; NS.retryJobOwner = owner;
    /* Unknown-owner LIVE stays memory-only until a separate owner contract. */
    savePendingJob(jobId, owner, pendingRaw);
    const epoch = NS.watcherEpoch;
    if (typeof EventSource === 'undefined') { pollJob(jobId, epoch); return; }
    const fallback = () => {
      if (epoch !== NS.watcherEpoch || !NS.eventSource) return;
      NS.eventSource.close(); NS.eventSource = null;
      clearTimeout(NS.watcherTimer);
      pollJob(jobId, epoch);
    };
    try { NS.eventSource = new EventSource(`/events/${encodeURIComponent(jobId)}`); }
    catch (_) { pollJob(jobId, epoch); return; }
    NS.watcherTimer = setTimeout(fallback, 8000);
    NS.eventSource.addEventListener('gone', fallback);
    NS.eventSource.onerror = fallback;
    NS.eventSource.onmessage = m => {
      if (epoch !== NS.watcherEpoch) return;
      let state; try { state = JSON.parse(m.data); } catch (_) { return; }
      clearTimeout(NS.watcherTimer);
      applyJobStatus(jobId, state);
    };
  }

  /* Engine warnings from /status, for the answer screen (the same
     list as on the wait screen). The key is the task id, so an
     analysis from the log does not inherit someone else's warnings. */
  const JOB_WARNINGS = {};

  /* wait clock: start, server forecast, ticker once per second */
  const WAIT = { startedAt: 0, eta: null, done: false, ticker: null, persistenceUnavailable: false };
  function paintWaitClock() {
    const timeEl = document.getElementById('wait-time-left');
    const eta = document.getElementById('wait-eta');
    if (!timeEl || !WAIT.startedAt) return;
    const el = (Date.now() - WAIT.startedAt) / 1000;
    const e = WAIT.eta;
    timeEl.textContent = fmtClock(el) + (e ? ` / usually ${fmtClock(e.lo)}–${fmtClock(e.hi)}` : '');
    if (eta && e && !WAIT.done) {
      /* The forecast is already shown on the right in seconds, so the note does not repeat
         'about a minute' and says only what is not there. */
      eta.textContent = el > e.hi
        ? 'Taking longer than usual for this video length — the analysis is running and the server responds.'
        : 'No need to wait here: we will tell you when the analysis is ready.';
      eta.dataset.live = '1';
    }
  }
  function startWaitClock() {
    WAIT.startedAt = Date.now(); WAIT.eta = null; WAIT.done = false;
    clearInterval(WAIT.ticker);
    WAIT.ticker = setInterval(() => {
      const w = document.getElementById('rec-waiting');
      if (!w || w.hidden || WAIT.done) { clearInterval(WAIT.ticker); WAIT.ticker = null; return; }
      paintWaitClock();
    }, 1000);
    paintWaitClock();
  }

  const fmtClock = sec => {
    const n = Math.max(0, Math.round(Number(sec) || 0));
    return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  };

  function applyJobStatus(jobId, s) {
    const title = document.getElementById('wait-stage-name');
    /* Server stage order (src/webapp.py, _on_ev): "jumpsight" —
       the engine opened the file; "probe" — the video is read, the SEARCH for attempts
       is running (10 of 15 s on a measured real run); "pose" — attempts
       are confirmed, each is being analyzed; "verdict" — the answer. */
    title.textContent = s.state === 'queued'
      ? 'Video queued' + (s.queue_position ? ` · ${s.queue_position}` : '')
      : liveStageTitle(s) || 'Analysing video';
    /* LIVE PROGRESS. The server gives
       total/done (how many candidates were found and how many already analyzed),
       elapsed and the measured forecast eta_lo/eta_hi, so the person
       sees that the system is really working: how many attempts it has already found,
       how much time has passed, and how long it usually takes for a video of this length. */
    const found = Number(s.total) || 0, done = Number(s.done) || 0;
    /* The step list under the heading follows the same stage as the heading. */
    const stageIdx = { jumpsight: 0, probe: 1, pose: 2, verdict: 3 }[s.stage] ?? 0;
    /* 'verdict' is still the revolution measurement (row 3); '✓ Answer' is done only */
    if (s.state !== 'queued') updateStageVisuals(s.state === 'done' ? 3 : Math.min(stageIdx, 2), s);
    /* The bar becomes defined as soon as there is something to count: a quarter per stage, and
       inside the analysis of attempts, the share analyzed. This is the real state of
       the server queue, not an animation of 'something is happening'. */
    const bar0 = document.getElementById('wait-prog-bar');
    if (bar0 && s.state !== 'queued' && s.state !== 'done' && found > 0) {
      const frac = Math.min(0.96, (stageIdx + (stageIdx === 2 ? done / found : 0)) / 4 + 0.1);
      bar0.classList.remove('is-indeterminate');
      bar0.style.transform = `scaleX(${frac.toFixed(3)})`;
    }
    /* The clock runs from the button press (client time), not from the
       server's elapsed: SSE sends an event only on a state change, and the server
       number stood between events ('0:00' for six seconds on a real run of
       15.09). The forecast is the server's, from the video length. */
    const lo = Number(s.eta_lo), hi = Number(s.eta_hi);
    if (Number.isFinite(lo) && Number.isFinite(hi) && hi > 0) WAIT.eta = { lo, hi };
    /* …but not BEHIND the server: after a page reload during
       analysis the clock started at 0:00 with the server at 40 s. The server's
       elapsed moves the start point forward; then the client ticks on. */
    const srvEl = Number(s.elapsed);
    if (Number.isFinite(srvEl) && srvEl > 0) {
      const cli = WAIT.startedAt ? (Date.now() - WAIT.startedAt) / 1000 : 0;
      if (!WAIT.startedAt || srvEl > cli + 3) WAIT.startedAt = Date.now() - srvEl * 1000;
    }
    WAIT.done = s.state === 'done';
    paintWaitClock();
    if (s.state !== 'done' && s.state !== 'error') paintEarly(s.early);
    /* A silent engine failure is not silent: the server names the key, WARN_TEXT
       translates it, and the person sees why the answer may be slower
       or poorer. The same lines then also appear on the answer screen. */
    const warn = s.warnings && typeof s.warnings === 'object' ? Object.keys(s.warnings) : [];
    if (warn.length) JOB_WARNINGS[jobId] = warn;
    const warnEl = document.getElementById('wait-warn');
    if (warnEl) {
      const lines = warn.map(k => WARN_TEXT[k] ? (WARN_TEXT[k][0]) : String(k).replace(/_/g, ' '));
      if (WAIT.persistenceUnavailable) lines.push(pendingStorageWarning());
      warnEl.textContent = lines.join(' · ');
      warnEl.hidden = !lines.length;
    }
    if (s.state === 'done') {
      const owner = NS.activeJobOwner;
      stopWatching();
      NS.activeJobId = jobId;
      NS.activeJobOwner = owner;
      title.textContent = TX('waitLiveDone');
      const bar = document.getElementById('wait-prog-bar');
      bar.classList.remove('is-indeterminate'); bar.style.transform = 'scaleX(1)';
      NS.fetchJobResults(jobId, { completionContext: { jobId, owner, watcherEpoch: NS.watcherEpoch } });
      return true;
    }
    if (s.state === 'error') {
      NS.retryJobId = null;
      NS.analysisFailed(s.error || 'Analysis stopped', null, { jobId, owner: NS.activeJobOwner });
      return true;
    }
    return false;
  }

  function pollJob(jobId, epoch = NS.watcherEpoch) {
    let misses = 0;
    const poll = async () => {
      if (epoch !== NS.watcherEpoch) return;
      NS.statusRequest = new AbortController();
      const timeout = setTimeout(() => NS.statusRequest?.abort(), 15000);
      try {
        const res = await fetch(`/status/${encodeURIComponent(jobId)}`, { signal: NS.statusRequest.signal });
        if (epoch !== NS.watcherEpoch) return;
        if (res.status === 404) {
          NS.retryJobId = null;
          NS.analysisFailed('This analysis is no longer available. Choose the video again.', null, { jobId, owner: NS.activeJobOwner });
          return;
        }
        if (!res.ok) throw new Error('status unavailable');
        const s = await res.json();
        if (epoch !== NS.watcherEpoch) return;
        misses = 0;
        if (applyJobStatus(jobId, s)) return;
      } catch (_) {
        if (epoch !== NS.watcherEpoch) return;
        misses++;
        document.getElementById('wait-stage-name').textContent = 'Reconnecting. Analysis continues on the server.';
      } finally { clearTimeout(timeout); }
      if (epoch === NS.watcherEpoch) NS.watcherTimer = setTimeout(poll, Math.min(10000, 1200 * 2 ** Math.min(misses, 3)));
    };
    poll();
  }

  Object.assign(NS, {
     WARN_TEXT, stopWatching, startWaitPreview, TX, resetWaitLoop, WAIT_ASK, askLabel, resetWaitAsk,
     sendWaitAnswer, prepareWaiting, analysisSessionReady, jobOwnerCurrent, clearPendingJob, restorePendingJob,
     watchJob, JOB_WARNINGS, applyJobStatus, pollJob,
  });
})();
