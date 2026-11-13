/* Coach chat and the workout player: session, reps, rests, finish and feedback. */
(function () {
  'use strict';
  const NS = window.JS.coach;
  let chatBusy = false;
  async function askCoach(question) {
    const stream = document.getElementById('coach-chat-stream');
    const input = document.getElementById('coach-chat-input');
    const send = document.getElementById('btn-coach-chat-send');
    if (!stream || !question?.trim() || chatBusy) return;
    chatBusy = true; if (send) send.disabled = true;
    if (input) input.value = '';
    const message = (text, role) => {
      const row = document.createElement('div');
      row.className = 'chat-msg chat-msg--' + role;
      const content = document.createElement('div');
      content.className = 'chat-msg-text';
      content.textContent = text; row.appendChild(content); stream.appendChild(row);
      stream.scrollTop = stream.scrollHeight; return row;
    };
    message(question, 'user');
    const typing = message('Searching the knowledge base…', 'coach');
    typing.setAttribute('role', 'status');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45000);
    try {
      const res = await fetch('/coach/ask', {
        method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, lang: 'en' })
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      typing.remove();
      const reply = message(data.answer || 'The knowledge base has no supported answer to this question.', 'coach');
      if (data.verification_scope === 'source_excerpt') {
        const scope = document.createElement('p');
        scope.className = 'sub-dim';
        scope.textContent = 'Exact source excerpt. Discuss how it applies to your technique with your coach.';
        reply.appendChild(scope);
      }
      if (data.verification_scope === 'numbers_only') {
        const scope = document.createElement('p');
        scope.className = 'sub-dim';
        scope.textContent = 'Numbers were checked against sources; a coach should verify the advice itself.';
        reply.appendChild(scope);
      }
      if (data.failure_kind || data.no_answer || data.grounded === false) {
        const status = document.createElement('p');
        status.className = 'sub-dim';
        status.textContent = data.note || (data.no_answer
          ? 'No answer was found in the sources.'
          : 'Showing a source excerpt; the answer was not fully verified.');
        reply.appendChild(status);
      }
      if (Array.isArray(data.sources) && data.sources.length) {
        const sources = document.createElement('p');
        sources.className = 'sub-dim';
        sources.append('Sources: ');
        data.sources.forEach((x, i) => {
          if (i) sources.append(' · ');
          const name = x.source || x.title || String(x);
          if (typeof x.url === 'string' && /^https:\/\//i.test(x.url)) {
            const link = document.createElement('a');
            link.href = x.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = name;
            sources.appendChild(link);
          } else sources.append(name);
        });
        reply.appendChild(sources);
      }
    } catch (_) {
      typing.remove();
      const failure = message('Could not get an answer. Please try again.', 'coach');
      failure.setAttribute('role', 'alert');
      const retry = document.createElement('button'); retry.className = 'btn btn--outline';
      retry.textContent = 'Retry question';
      retry.onclick = () => { if (!chatBusy) { failure.remove(); askCoach(question); } };
      failure.appendChild(retry);
    } finally {
      clearTimeout(timeout); chatBusy = false; if (send) send.disabled = false;
      stream.scrollTop = stream.scrollHeight;
    }
  }

  /* ── 2-Metre Session Player Engine ── */
  function startSession(drill = null, blockIdx = 0) {
    /* Dosage is not invented:
       sets/reps only when parsed from the prescription. */
    if (!NS.livePlan.length && !drill) {
      window.APP.go('today');
      NS.renderEmptyToday();
      return;                       /* no plan, nothing to play */
    }
    const plan = NS.livePlan;
    const resumed = NS.sessionState.resume && NS.sessionState.resume.blockIdx === blockIdx ? NS.sessionState.resume :
      (!drill && NS.sessionState.sessionId && NS.sessionState.drill && NS.sessionState.blockIdx === blockIdx
        ? { ...NS.sessionState } : null);
    NS.sessionState.resume = null;
    if (!NS.sessionState.sessionId) NS.sessionState.sessionId = 'workout-' + (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
    document.getElementById('workout-draft-notice')?.remove();
    if (!NS.sessionState.signature) NS.sessionState.signature = NS.planSignature();
    if (!drill) drill = plan[blockIdx % plan.length];
    NS.sessionState.drill = drill;
    NS.sessionState.blockIdx = blockIdx;
    NS.sessionState.set = 1;
    NS.sessionState.rep = 0;
    /* Dosage is PARSED from the prescribed text, not invented:
       "3x6" -> 3 sets of 6; "5 from each leg" -> 2 sets of 5
       (each leg = its own set); "5" -> 1x5; otherwise 1 set
       with a manual "Done". */
    const parsed = NS.parseDosage(drill.dosageDesc);
    NS.sessionState.totalSets = drill.sets || parsed.sets || 1;
    NS.sessionState.targetReps = drill.reps || parsed.reps || 1;
    /* block by time: no sets/reps, but with the duration in the text */
    NS.sessionState.timedSec = (!drill.sets && !parsed.sets && !drill.reps && !parsed.reps && parsed.seconds) ? parsed.seconds : 0;
    NS.sessionState.timedLabel = parsed.secondsLabel || '';
    clearInterval(NS.sessionState.timedTimer); NS.sessionState.timedTimer = null; NS.sessionState.timedLeft = NS.sessionState.timedSec;
    /* coach hub: the "current workout" card lives only during a session */
    const awCard = document.getElementById('coach-active-workout-card');
    if (awCard) {
      awCard.hidden = false;
      const d = document.getElementById('coach-workout-day');
      const nm = document.getElementById('coach-workout-block-name');
      const ds = document.getElementById('coach-workout-dosage');
      if (d) d.textContent = `BLOCK ${blockIdx + 1}`;
      if (nm) nm.textContent = (NS.NAME(drill.drill_id, drill.title || drill.name) || '');
      const repsShown = drill.reps || parsed.repsLabel || NS.sessionState.targetReps;
      if (ds) ds.textContent = NS.sessionState.totalSets && NS.sessionState.targetReps
        ? `${NS.sessionState.totalSets} sets × ${repsShown}` : '';
    }
    const stLbl = document.getElementById('player-start-label');
    if (stLbl) stLbl.textContent = NS.sessionState.totalSets > 1 || NS.sessionState.targetReps > 1
      ? `Start set · ${NS.sessionState.totalSets} × ${drill.reps || parsed.repsLabel || NS.sessionState.targetReps}`
      : 'Start set';
    NS.sessionState.holdSec = drill.holdSec || 0;
    NS.sessionState.restSec = drill.rest || 45;
    NS.sessionState.feedback = false;
    if (resumed) {
      NS.sessionState.set = Math.max(1, Math.min(NS.sessionState.totalSets, Math.floor(Number(resumed.set) || 1)));
      NS.sessionState.rep = Math.max(0, Math.min(NS.sessionState.targetReps, Math.floor(Number(resumed.rep) || 0)));
      if (Number.isFinite(resumed.timedLeft)) NS.sessionState.timedLeft = Math.max(0, Math.min(NS.sessionState.timedSec, resumed.timedLeft));
    }

    const bTitle = document.getElementById('player-block-title');
    if (bTitle) {
      /* "Warm-up: General warm-up" — the word twice and a cut-off name
         on the phone. The category stays only when it is not in the name. */
      /* The header shows only the drill name: with the category prefix ("Preparation:
         Jumps into position…") it is cut off on the phone next to "Block 2
         of 8 · set 1 of 3". The category is in the session list. */
      bTitle.textContent = String(drill.title || String(drill.category || '').split('·')[0].trim());
    }

    const cueDisp = document.getElementById('player-cue-display');
    /* A warm-up drill must not show a jump tip. No hint — the card is hidden,
       not a stranger's hint substituted. */
    if (cueDisp) {
      cueDisp.hidden = !drill.cue;
      if (drill.cue) cueDisp.textContent = `“${drill.cue}”`;   /* English quotes in EN */
    }

    // Show step-by-step instructions below the video
    const stepsContainer = document.getElementById('player-steps-list');
    if (stepsContainer && drill.steps) {
      stepsContainer.innerHTML = drill.steps.map((s, i) => 
        `<div class="rz-player-step">
          <span class="rz-player-step__ic">${i+1}</span>
           <span class="rz-player-step__text">${NS.H(s)}</span>
        </div>`
      ).join('');
    }
    
    // Show common mistakes
    const mistakesContainer = document.getElementById('player-mistakes-list');
    if (mistakesContainer) {
      const ms = Array.isArray(drill.mistakes) ? drill.mistakes : [];
      mistakesContainer.innerHTML = ms.map(m => 
        `<div class="rz-player-step rz-player-step--mistake">
          <span class="rz-player-step__warn">⚠</span>
           <span class="rz-player-step__text">${NS.H(m)}</span>
        </div>`
      ).join('');
      /* an empty "Common mistakes" heading is not information */
      const det = mistakesContainer.closest('details'); if (det) det.hidden = !ms.length;
    }
    if (stepsContainer) {
      const det = stepsContainer.closest('details');
      if (det) det.hidden = !(drill.steps && drill.steps.length);
    }

    const pVid = document.getElementById('player-video-loop');
    if (pVid) {
      /* The source is decided by the BACKEND (/api/drill_media): mascot — the 3D character that
         passed the gates; none — an honest "no demo". The coach's original videos
         are never shown. */
      pVid.removeAttribute('src'); pVid.load();
      const stage = pVid.closest('.rz-player__video');
      /* The caption sits AFTER the scene, not inside it: the scene is hidden when the demo
         is missing, and the line "3D demonstration is still being prepared" was hidden with it
         (no explanation of why there is no video). */
      const cap = document.getElementById('player-video-source')
        || (() => { const c = document.createElement('div');
             c.id = 'player-video-source';
             c.className = 'rz-player__source';
             (stage || pVid).insertAdjacentElement('afterend', c); return c; })();
      cap.textContent = '';
      if (stage) stage.hidden = false;
      /* no demo — no black rectangle: one line remains */
      const setView = document.getElementById('player-set-view');
      if (setView) setView.classList.remove('is-text-only');
      const noDemo = () => {
        if (NS.sessionState.drill !== drill) return;
        if (stage) stage.hidden = true;
        if (setView) setView.classList.add('is-text-only');
        cap.textContent = 'This drill has no video demonstration — follow the steps.';
      };
      /* a block without drill_id (general warm-up) — there is nowhere to send a request;
         a GET /api/drill_media/ went out and returned 404 in the console */
      if (!drill.id) noDemo();
      else fetch(`/api/drill_media/${encodeURIComponent(drill.id)}`)
          .then(r => r.ok ? r.json() : null)
          .then(m => {
            if (NS.sessionState.drill !== drill) return;
            if (m && m.url) {
              pVid.src = m.url;
              /* synthesized voice is labeled (TTS terms) */
              /* the demo of a related drill is labeled as related */
              cap.textContent = [m.kind === 'related' && m.note ? m.note : '',
                                 m.voice_note ? 'AI-generated voice' : '']
                .filter(Boolean).join(' · ');
              /* the file is in the list but does not play — not a black box */
              pVid.onerror = noDemo;
            } else noDemo();
          }).catch(() => { noDemo(); if (NS.sessionState.drill === drill) cap.textContent = 'Video unavailable — follow the steps.'; });
    }

    document.getElementById('scr-player').hidden = false;
    document.getElementById('scr-player').style.display = 'flex';
    document.getElementById('player-set-view').hidden = false;
    document.getElementById('player-set-view').style.display = 'flex';
    document.getElementById('player-rest-view').hidden = true;
    document.getElementById('player-rest-view').style.display = 'none';
    document.getElementById('player-rpe-view').hidden = true;
    document.getElementById('player-rpe-view').style.display = 'none';
    updatePlayerUI();
    if (resumed && resumed.feedback) finishWorkout();
    else if (resumed && resumed.resting) startRest(resumed.restRemainingSec);
  }

  function updatePlayerUI() {
    NS.saveWorkoutDraft();
    const setLbl = document.getElementById('player-set-eyebrow');
    if (setLbl) {
      /* Where I am in the session: block N of M — always; set — only when there are several
         ("Set 1 of 1" above the warm-up timer is noise). */
      const nBlocks = NS.livePlan.length;
      const blockTxt = nBlocks > 1 && Number.isFinite(NS.sessionState.blockIdx)
        ? `Block ${NS.sessionState.blockIdx + 1} of ${nBlocks}` : '';
      const setTxt = NS.sessionState.totalSets > 1
        ? `set ${NS.sessionState.set} of ${NS.sessionState.totalSets}` : '';
      /* "Single turn on both legs" — on the floor; without the marker
         the person on the ice would do it on the ice */
      const cur = Number.isFinite(NS.sessionState.blockIdx) ? NS.livePlan[NS.sessionState.blockIdx] : null;
      const whereTxt = cur && cur.where === 'off_ice' ? 'off-ice' : '';
      setLbl.textContent = [blockTxt, whereTxt, setTxt].filter(Boolean).join(' · ');
      setLbl.hidden = !setLbl.textContent;
    }

    const repCount = document.getElementById('player-rep-counter');
    if (repCount) repCount.textContent = `${NS.sessionState.rep} / ${NS.sessionState.targetReps}`;

    const holdTxt = document.getElementById('player-hold-txt');
    if (holdTxt) holdTxt.textContent = `${NS.sessionState.holdSec.toFixed(1)} s`;

    const ring = document.getElementById('player-hold-ring');
    if (ring) ring.style.strokeDashoffset = 0;

    /* The ring timer applies only to hold drills (holdSec>0) —
       for regular reps (e.g. "3x6") it hung statically at
       "0.0 s", which means nothing for this drill. Found in a live
       walkthrough of the session. */
    const holdBox = document.getElementById('player-hold-box');
    if (holdBox) holdBox.hidden = !NS.sessionState.holdSec;

    /* time-based block: a timer instead of a rep counter */
    const timed = !!NS.sessionState.timedSec;
    const tBox = document.getElementById('player-timed');
    const tBtn = document.getElementById('btn-timed-start');
    const tLbl = document.getElementById('btn-timed-start-label');
    const repBtn = document.getElementById('btn-rep-done');
    if (tBox) tBox.hidden = !timed;
    if (repCount) repCount.hidden = timed;
    if (repBtn) repBtn.hidden = timed;
    if (tBtn) tBtn.hidden = !timed;
    if (timed) {
      const clock = document.getElementById('player-timed-clock');
      const note = document.getElementById('player-timed-note');
      const left = NS.sessionState.timedLeft ?? NS.sessionState.timedSec;
      if (clock) clock.textContent = `${Math.floor(left / 60)}:${String(Math.round(left % 60)).padStart(2, '0')}`;
      if (note) note.textContent = NS.sessionState.timedLabel
        ? `as prescribed: ${NS.sessionState.timedLabel}` : '';
      if (tLbl) tLbl.textContent = NS.sessionState.timedTimer
        ? 'Pause'
        : (left < NS.sessionState.timedSec ? 'Resume' : 'Start');
    }
  }

  /* Block timer by time: start/pause; zero means the signal and the block is complete. */
  function toggleTimedBlock() {
    if (!NS.sessionState.timedSec) return;
    if (NS.sessionState.timedTimer) {
      clearInterval(NS.sessionState.timedTimer); NS.sessionState.timedTimer = null;
      updatePlayerUI();
      return;
    }
    if (NS.sessionState.timedLeft <= 0) NS.sessionState.timedLeft = NS.sessionState.timedSec;
    NS.sessionState.timedTimer = setInterval(() => {
      NS.sessionState.timedLeft = Math.max(0, NS.sessionState.timedLeft - 1);
      updatePlayerUI();
      if (NS.sessionState.timedLeft <= 0) {
        clearInterval(NS.sessionState.timedTimer); NS.sessionState.timedTimer = null;
        NS.playTone(980, 0.15); setTimeout(() => NS.playTone(980, 0.15), 250);
        NS.sessionState.rep = NS.sessionState.targetReps;
        onSetDone();
      }
    }, 1000);
    updatePlayerUI();
  }

  function onRepDone() {
    /* Drills without a hold (holdSec=0 — all live ones, from /coach/today, because
       the backend does not provide this field) increment directly, without a
       100 ms clearInterval timer: each next quick tap would cancel the
       previous one and the rep count would be lost. */
    if (!NS.sessionState.holdSec) {
      if (NS.sessionState.rep < NS.sessionState.targetReps) {
        NS.sessionState.rep++;
        updatePlayerUI();
        if (NS.sessionState.rep >= NS.sessionState.targetReps) onSetDone();
      }
      return;
    }
    let left = NS.sessionState.holdSec;
    const btnRep = document.getElementById('btn-rep-done');
    const ring = document.getElementById('player-hold-ring');
    const txt = document.getElementById('player-hold-txt');

    if (btnRep) btnRep.classList.add('is-active');
    if (txt) txt.textContent = `HOLD · ${left.toFixed(1)} s`;

    clearInterval(NS.sessionState.holdTimer);
    NS.sessionState.holdTimer = setInterval(() => {
      left = Math.max(0, left - 0.1);
      if (txt) txt.textContent = `HOLD · ${left.toFixed(1)} s`;
      if (ring) {
        const pct = (left / NS.sessionState.holdSec) * 283;
        ring.style.strokeDashoffset = (283 - pct);
      }
      if (left <= 0) {
        clearInterval(NS.sessionState.holdTimer);
        NS.playTone(980, 0.12);
        if (btnRep) btnRep.classList.remove('is-active');
        if (NS.sessionState.rep < NS.sessionState.targetReps) {
          NS.sessionState.rep++;
          updatePlayerUI();
          if (NS.sessionState.rep >= NS.sessionState.targetReps) {
            onSetDone();
          }
        }
      }
    }, 100);
  }

  function onSetDone() {
    clearInterval(NS.sessionState.holdTimer);
    clearInterval(NS.sessionState.timedTimer); NS.sessionState.timedTimer = null;
    if (NS.sessionState.set < NS.sessionState.totalSets) {
      startRest();
    } else {
      const plan = NS.livePlan;
      if (NS.sessionState.drill && NS.sessionState.drill.id)
        NS.sessionState.completed.add(NS.sessionState.drill.id);
      if (NS.sessionState.blockIdx < plan.length - 1) {
        startSession(null, NS.sessionState.blockIdx + 1);
      } else {
        finishWorkout();
      }
    }
  }

  function startRest(remaining = null) {
    NS.sessionState.resting = true;
    document.getElementById('player-set-view').hidden = true;
    document.getElementById('player-set-view').style.display = 'none';
    document.getElementById('player-rest-view').hidden = false;
    document.getElementById('player-rest-view').style.display = 'flex';
    NS.sessionState.restRemainingSec = Number.isFinite(remaining) ? Math.max(0, remaining) : (NS.sessionState.restSec || 90);
    NS.saveWorkoutDraft();
    const clock = document.getElementById('player-rest-clock');
    clearInterval(NS.sessionState.restTimer);

    function fmt(s) {
      const m = Math.floor(s / 60);
      const r = s % 60;
      return `${m}:${r < 10 ? '0' : ''}${r}`;
    }
    clock.textContent = fmt(NS.sessionState.restRemainingSec);

    NS.sessionState.restTimer = setInterval(() => {
      NS.sessionState.restRemainingSec--;
      NS.saveWorkoutDraft();
      clock.textContent = fmt(NS.sessionState.restRemainingSec);
      if (NS.sessionState.restRemainingSec <= 0) {
        clearInterval(NS.sessionState.restTimer);
        NS.playTone(1050, 0.25);
        skipRest();
      }
    }, 1000);
  }

  function addRest30() {
    const clock = document.getElementById('player-rest-clock');
    NS.sessionState.restRemainingSec += 30;
    const m = Math.floor(NS.sessionState.restRemainingSec / 60);
    const r = NS.sessionState.restRemainingSec % 60;
    clock.textContent = `${m}:${r < 10 ? '0' : ''}${r}`;
  }

  function skipRest() {
    NS.sessionState.resting = false;
    clearInterval(NS.sessionState.restTimer);
    NS.sessionState.set++;
    NS.sessionState.rep = 0;
    document.getElementById('player-rest-view').hidden = true;
    document.getElementById('player-rest-view').style.display = 'none';
    document.getElementById('player-set-view').hidden = false;
    document.getElementById('player-set-view').style.display = 'flex';
    updatePlayerUI();
  }

  function finishWorkout() {
    clearInterval(NS.sessionState.timedTimer); NS.sessionState.timedTimer = null;
    clearInterval(NS.sessionState.restTimer); NS.sessionState.restTimer = null;
    clearInterval(NS.sessionState.holdTimer); NS.sessionState.holdTimer = null;
    NS.sessionState.resting = false;
    NS.sessionState.feedback = true;
    NS.saveWorkoutDraft();
    document.getElementById('player-set-view').hidden = true;
    document.getElementById('player-set-view').style.display = 'none';
    document.getElementById('player-rest-view').hidden = true;
    document.getElementById('player-rest-view').style.display = 'none';
    document.getElementById('player-rpe-view').hidden = false;
    document.getElementById('player-rpe-view').style.display = 'flex';
    document.querySelectorAll('[data-post-rpe]').forEach(button => {
      const selected = button.getAttribute('data-post-rpe') === NS.sessionState.rpe;
      button.classList.toggle('is-on', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    const box = document.getElementById('player-outcomes');
    if (!box) return;
    box.replaceChildren();
    const done = NS.livePlan.filter(drill => NS.sessionState.completed.has(drill.id));
    box.hidden = !done.length;
    if (!done.length) return;
    const heading = document.createElement('h3');
    heading.textContent = 'How did each drill go?';
    box.appendChild(heading);
    for (const drill of done) {
      const row = document.createElement('div');
      row.className = 'rz-player__outcome';
      const title = document.createElement('p');
      title.className = 'rz-player__outcome-title';
      title.textContent = drill.title;
      row.appendChild(title);
      const options = document.createElement('div');
      options.className = 'rz-player__outcome-options';
      for (const [value, en] of [
        ['ok', 'Clean'],
        ['partial', 'Partly'],
        ['fail', 'Not yet']
      ]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn--outline';
        button.textContent = en;
        button.setAttribute('aria-pressed', String(NS.sessionState.outcomes[drill.id] === value));
        button.classList.toggle('is-on', NS.sessionState.outcomes[drill.id] === value);
        button.onclick = () => {
          NS.sessionState.outcomes[drill.id] = value;
          NS.saveWorkoutDraft();
          options.querySelectorAll('button').forEach(b => {
            b.classList.toggle('is-on', b === button);
            b.setAttribute('aria-pressed', String(b === button));
          });
        };
        options.appendChild(button);
      }
      row.appendChild(options);
      box.appendChild(row);
    }
  }

  async function saveFeedbackAndExit() {
    const save = document.getElementById('btn-save-session-feedback');
    const error = document.getElementById('player-save-error');
    if (save.disabled) return;
    save.disabled = true;
    error.hidden = true;
    try {
      const response = await fetch('/coach/today/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          done: [...NS.sessionState.completed],
          focus: (NS.todayData && (NS.todayData.focus_goal || NS.todayData.focus || '')) || '',
          effort: NS.sessionState.rpe,
          session_id: NS.sessionState.sessionId,
          outcomes: NS.sessionState.outcomes
        })
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
    } catch (e) {
      error.textContent = 'Session was not saved. Check the connection and retry.';
      error.hidden = false;
      save.disabled = false;
      return;
    }
    NS.sessionState.sessionId = '';
    NS.sessionState.signature = '';
    NS.sessionState.feedback = false;
    NS.clearWorkoutDraft();
    NS.sessionState.completed.clear();
    NS.sessionState.outcomes = {};
    NS.sessionState.rpe = '';
    document.querySelectorAll('[data-post-rpe]').forEach(button => {
      button.classList.remove('is-on');
    });
    save.disabled = false;

    document.getElementById('scr-player').hidden = true;
    document.getElementById('scr-player').style.display = 'none';
    const awCard = document.getElementById('coach-active-workout-card');
    if (awCard) awCard.hidden = true;
    window.APP.go('today');
    /* after "Save · back to Today" a confirmation shows and
       "🔥 1 day in a row" updates at once (fillLiveStats also runs here, not only at page start). */
    try { window.APP.notice && window.APP.notice('✓ Session saved'); } catch (_) { }
    await NS.refresh(true);
    try { await NS.fillLiveStats(); } catch (_) { }
  }

  Object.assign(NS, {
     askCoach, startSession, toggleTimedBlock, onRepDone, onSetDone, addRest30, skipRest, finishWorkout,
     saveFeedbackAndExit,
  });
})();
