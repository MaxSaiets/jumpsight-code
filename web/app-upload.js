/* Video file upload and the jump-name helpers shared with the journal. */
(function () {
  'use strict';
  const NS = window.JS.app;
  async function handleFileUpload(file) {
    if (!file) return;
    if (NS.LIVE.finishPending) { NS.liveUploadFailed(); return; }
    if (NS.uploadInFlight || NS.activeJobId || NS.LIVE.starting || NS.LIVE.rec) {
      /* A refused file must say why (a silent button press looks broken). Without stopWatching:
         the current analysis must not be killed by a message. */
      const box = document.getElementById('rec-fail-note');
      const why = document.getElementById('rec-fail-reason');
      if (why) why.textContent = 'The previous video is still being analysed. Return to Analyse to see its status.';
      if (box) { box.hidden = false; box.focus(); }
      return;
    }
    NS.lastUploadFile = null;
    NS.retryJobId = null; NS.retryJobOwner = null;
    if (!file.size || (!file.type.startsWith('video/') && !/\.(mp4|mov|m4v|webm|mkv|avi|3gp|mpeg|mpg)$/i.test(file.name))) {
      NS.analysisFailed('Choose a non-empty video file. Photos and documents cannot be analysed.');
      return;
    }
    NS.lastUploadFile = file;
    /* A file picked in the first second after opening must not fail with
       'Profile not ready yet' while the /coach/me request is still in flight
       (slow mobile network). Wait for readiness up to 10 s; the owner
       is fixed AFTER it, so the video does not bind to someone else's profile. */
    if (!NS.analysisSessionReady()) {
      NS.uploadInFlight = true;
      const hint = document.getElementById('record-file-hint');
      const hintWas = hint ? hint.textContent : '';
      if (hint) hint.textContent = 'Preparing your profile for upload…';
      const t0 = Date.now();
      while (!NS.analysisSessionReady() && Date.now() - t0 < 10000) await new Promise(r => setTimeout(r, 150));
      if (hint) hint.textContent = hintWas;
      NS.uploadInFlight = false;
    }
    if (!NS.analysisSessionReady()) {
      NS.analysisFailed('Your profile is not ready to upload. Check your connection and select Retry once it has loaded.',
                     'Video has not been uploaded yet');
      return;
    }
    const owner = { ownerUid: NS.readyMeUid, generation: NS.identityGeneration, name: file.name };
    const uploadEpoch = ++NS.uploadRequestEpoch;
    const current = () => uploadEpoch === NS.uploadRequestEpoch && NS.jobOwnerCurrent(owner);
    NS.uploadInFlight = true;
    NS.prepareWaiting(file.name);
    /* The jump is not declared before upload: we ask while the server computes */
    NS.resetWaitAsk(!NS.declaredJump, uploadEpoch);
    // Local preview does not decode the video in the background without need.
    NS.previewJobId = null;
    try {
      if (NS.previewUrl) URL.revokeObjectURL(NS.previewUrl);
      const blobUrl = NS.previewUrl = URL.createObjectURL(file);
      const waitVid = document.getElementById('wait-live-video');
      if (waitVid) {
        waitVid.src = blobUrl;
        NS.startWaitPreview(waitVid);
        const wbox = waitVid.closest('.rz-video'); if (wbox) wbox.hidden = false;
        /* the time promise is computed from THIS video's LENGTH, not
           a fixed phrase. */
        waitVid.onloadedmetadata = null;
      }
      NS.setWaitEta(null);
      const ansVid = document.getElementById('ans-video');
      if (ansVid) { ansVid.src = blobUrl; }
    } catch (e) { }

    document.getElementById('rec-intro').hidden = true;
    document.getElementById('rec-waiting').hidden = false;

    const fd = new FormData();
    fd.append('file', file);
    if (NS.declaredJump) fd.append('declared', NS.declaredJump);
    if (NS.declaredJump && NS.declaredTurns) fd.append('declared_turns', NS.declaredTurns);
    { const tc = document.getElementById('train-consent'); if (NS.declaredJump && tc && tc.checked) fd.append('train_consent', '1'); }

    try {
      /* A lost response may already have started the computation. Re-sending the file is
         a user action, not an automatic second expensive POST. */
      const res = await fetch('/upload', { method: 'POST', body: fd });
      if (!current()) return;
      if (res.ok) {
        const data = await res.json();
        if (!current()) return;
        if (typeof data.job !== 'string' || !/^[A-Za-z0-9_-]+$/.test(data.job)) throw new Error('missing job');
        NS.previewJobId = data.job;
        if (NS.WAIT_ASK.upload === uploadEpoch) NS.WAIT_ASK.job = data.job;
        /* the declaration belongs to THIS video; the next one starts from a clean choice */
        if (NS.declaredJump) document.dispatchEvent(new Event('js:declare-sent'));
        NS.watchJob(data.job, { owner });
      } else {
        /* The server answers with JSON carrying an error field (415/413/422:
           type, size, duration); we show it in words, not 'HTTP 415'. */
        let msg = 'HTTP ' + res.status;
        try { const j = await res.json(); if (j && j.error) msg = j.error; } catch (e) { }
        if (!current()) return;
        NS.analysisFailed(msg);
      }
    } catch (e) {
      if (!current()) return;
      NS.analysisFailed('no connection to the server');
    } finally { if (uploadEpoch === NS.uploadRequestEpoch) NS.uploadInFlight = false; }
  }

  /* Fields with MEASURED values are marked data-live after every render, so
     relocalize() does not replace the real answer with the placeholder from the markup. */
  const MEASURED_FIELD_IDS = [
    'last-ans-name', 'last-ans-verdict', 'last-ans-sub',
    'ans-attempt-eyebrow', 'ans-verdict-t', 'ans-verdict-s',
    'lbl-ph-takeoff', 'lbl-ph-flight', 'lbl-ph-landing',
    'ans-err-count', 'ans-stability-category', 'ans-stability-cue',
    'btn-next-attempt-txt', 'progress-records-sub'];

  function markMeasuredLive() {
    MEASURED_FIELD_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el && el.textContent.trim()) el.dataset.live = '1';
    });
  }

  /* The jump name in plain words. In English it is already the way people say it
     ('Toe loop'), so no further mapping is needed. */
  /* The pair name from the server ('Flip / Lutz') in plain words. It is not
     hardcoded as 'Lutz or Flip': the server may narrow it to another pair. */
  function jumpPairLocal(s) {
    if (!s) return null;
    const parts = String(s).split('/').map(x => x.trim()).filter(Boolean);
    const named = parts.map(x => jumpNameLocal(x) || x);
    if (named.length < 2) return named[0] || null;
    return named.join(' or ');
  }

  /* One form of 'name + count' in the log, the cabinet and the labels:
     EN: 'Double loop', as on the answer screen; without a name: 'Name not
     resolved · double', because a count is not attached to an unknown name. */
  function jumpWithCount(row, name) {
    const nm = name || (!row.jump || row.jump === 'None' ? 'Jump not resolved' : historyJumpName(row));
    /* the jump is not confirmed: there is no count to attach to (coach_mobile: refused_job) */
    const hasJump = row.jump && row.jump !== 'None';
    const c = hasJump && row.count_named && row.count_named !== 'None' ? row.count_named : '';
    if (!c) return nm;
    const est = row.count_estimated === true || row.count_estimated === 'True' ? '≈ ' : '';
    const sure = row.jump && row.jump !== 'None' && ![true, 'true', 'True'].includes(row.name_uncertain)
      && ![true, 'true', 'True'].includes(row.name_is_family);
    if (!sure) return `${nm} · ${est}${c}`;
    return `${est}${c.charAt(0).toUpperCase()}${c.slice(1)} ${nm}`;
  }
  window.APP_jumpWithCount = jumpWithCount;

  function historyJumpName(row) {
    if ([true, 'true', 'True'].includes(row.name_uncertain)) return 'Name not resolved';
    if (row.name_display) return jumpPairLocal(row.name_display);
    if ([true, 'true', 'True'].includes(row.name_is_family)) return 'Name not resolved';
    return jumpNameLocal(row.jump) || row.jump;
  }

  function historyIsClean(row) {
    return !['partial', 'unavailable'].includes(row.execution_state)
      && !(Array.isArray(row.errors) && row.errors.length)
      && [true, 'true', 'True'].includes(row.clean);
  }

  /* 'No findings' (checked): among the checked signs nothing was found,
     not even 'possibly'. The same meaning as 'No errors found: N signs checked' on the answer.
     historyIsClean requires a FULL check, and the two signs (both feet, knee) are never checked by
     the engine from one angle, so 'clean' on 'Progress' is always 0. */
  function historyNoFindings(row) {
    return !!row && row.execution_state !== 'unavailable'
      && !(Array.isArray(row.errors) && row.errors.length)
      && (Number(row.checks_run) > 0 || (Array.isArray(row.errors_checked_clean) && row.errors_checked_clean.length > 0)
          || [true, 'true', 'True'].includes(row.clean));
  }

  /* The execution line for the log, in the same language as the answer: findings by
     confidence, otherwise 'no errors found'; no 'partially assessed' jargon. */
  function historyExecutionLabel(row) {
    const f = NS.findings(row.errors, row.errors_conf);
    if (f.text) return f.text;
    if (historyNoFindings(row)) return 'no errors found';
    return row.execution_state === 'unavailable' ? 'errors not checked' : '';
  }

  /* ONE LANGUAGE OF CONFIDENCE: coach and student read the same words for the
     same analysis; confidence sits next to each conclusion. */
  function confWord(value) {
    return ({ high: 'confident', medium: 'likely', low: 'possible' })[
      String(value || '').toLowerCase()] || 'confidence unknown';
  }

  function historyConfidenceLabel(value, kind) {
    const label = kind === 'name' ? 'name' : kind === 'count' ? 'count' : 'signal';
    return `${label} — ${confWord(value)}`;
  }

  /* a finding with low (or unknown) confidence is 'possibly', as in the answer */
  function historyErrorSignalLabel(row, code) {
    const name = NS.ERR_UA[code]?.[0] || String(code).replace(/_/g, ' ');
    const tier = String(row.errors_conf?.[code] || 'low').toLowerCase();
    return ['medium', 'high'].includes(tier) ? `${name} — ${confWord(tier)}`
      : `possibly: ${name.toLowerCase()}`;
  }

  function jumpNameLocal(name) {
    if (!name) return null;
    const k = String(name).toLowerCase().replace(/[\s_]+/g, '');
    const EN = { axel: 'Axel', salchow: 'Salchow', toeloop: 'toe loop',
                 loop: 'loop', flip: 'flip', lutz: 'Lutz' };
    return EN[k] || null;
  }

  Object.assign(NS, {
     handleFileUpload, markMeasuredLive, jumpPairLocal, jumpWithCount, historyJumpName, historyNoFindings,
     historyExecutionLabel, confWord, historyConfidenceLabel, historyErrorSignalLabel, jumpNameLocal,
  });
})();
