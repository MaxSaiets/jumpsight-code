/* Fitness test runner, drafts, skills list, default history and learn terms. */
(function () {
  'use strict';
  const NS = window.JS.coach;
  const FITNESS_TIME_TESTS = ['plank', 'balance_s'];
  const FITNESS_WINDOW_TESTS = ['squats_60s'];
  NS.fitRunIdx = 0;
  let fitRunResults = {};
  let fitRunTimerHandle = null;
  NS.fitRunActive = false, NS.fitRunSaving = false, NS.fitManualSaving = false;
  NS.fitRunTests = [];
  NS.fitnessOwner = null, NS.fitnessDraftsRestored = false;
  NS.fitnessLoadFailed = false;
  NS.fitManualValues = {}, NS.fitRunCurrent = '', NS.fitRunResume = false;
  NS.fitRunTimerRunning = false, NS.fitRunInterrupted = false;

  const fitnessKind = id => FITNESS_TIME_TESTS.includes(id) ? 'stopwatch'
    : FITNESS_WINDOW_TESTS.includes(id) ? 'window60' : 'number';
  const fitnessSignature = tests => JSON.stringify(tests.map(t => [t.id, fitnessKind(t.id)]));
  const fitnessKey = (kind, owner = NS.fitnessOwner) => `js.fitness.${owner}.${kind}`;
  function fitnessDraftNotice(message) {
    const note = document.getElementById('fitness-draft-notice');
    note.hidden = false; note.textContent = message;
  }
  function saveFitnessDraft(kind) {
    if (!NS.fitnessOwner || NS.fitnessOwner !== window.APP?.currentUid?.()) return null;
    if (kind === 'manual') NS.fitManualValues = Object.fromEntries(NS.fitnessTestDefs.map(t =>
      [t.id, document.getElementById(`fitness-in-${t.id}`)?.value || '']).filter(([, value]) => value !== ''));
    const revision = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const draft = { version: 1, owner: NS.fitnessOwner, revision, updated: Date.now(),
      signature: fitnessSignature(kind === 'runner' ? NS.fitRunTests : NS.fitnessTestDefs),
      ...(kind === 'manual' ? { values: NS.fitManualValues } : {
        index: NS.fitRunIdx, results: fitRunResults, current: NS.fitRunCurrent,
        interrupted: NS.fitRunTimerRunning || NS.fitRunInterrupted
      }) };
    try {
      localStorage.setItem(fitnessKey(kind), JSON.stringify(draft));
      return revision;
    } catch (_) {
      fitnessDraftNotice('Could not save the draft on this device. Results remain on the open page.');
      return null;
    }
  }
  function clearFitnessDraft(kind, owner, revision) {
    if (!owner || owner !== window.APP?.currentUid?.() || !revision) return;
    try {
      const key = fitnessKey(kind, owner);
      if (JSON.parse(localStorage.getItem(key) || 'null')?.revision === revision) localStorage.removeItem(key);
    } catch (_) { fitnessDraftNotice('Could not clear the local draft.'); }
  }
  function restoreFitnessDrafts() {
    if (NS.fitnessDraftsRestored || !NS.fitnessOwner || NS.fitnessOwner !== window.APP?.currentUid?.()) return;
    NS.fitnessDraftsRestored = true;
    const validValues = values => values && typeof values === 'object' && !Array.isArray(values)
      && Object.entries(values).every(([id, value]) => NS.fitnessTestDefs.some(t => t.id === id)
        && typeof value === 'string' && value.length <= 64 && (value === '' || Number.isFinite(Number(value))));
    for (const kind of ['manual', 'runner']) {
      const key = fitnessKey(kind);
      try {
        const raw = localStorage.getItem(key);
        if (!raw) continue;
        const saved = JSON.parse(raw);
        if (!saved || saved.version !== 1 || saved.owner !== NS.fitnessOwner
            || typeof saved.revision !== 'string' || !saved.revision
            || !Number.isFinite(saved.updated) || saved.updated > Date.now() || Date.now() - saved.updated > 86400000
            || saved.signature !== fitnessSignature(NS.fitnessTestDefs)
            || (kind === 'manual' ? !validValues(saved.values) :
              !validValues(saved.results) || !Number.isInteger(saved.index) || saved.index < 0 || saved.index > NS.fitnessTestDefs.length
              || typeof saved.current !== 'string' || saved.current.length > 64
              || (saved.current !== '' && !Number.isFinite(Number(saved.current))) || typeof saved.interrupted !== 'boolean')) {
          throw new Error('invalid draft');
        }
        if (kind === 'manual') {
          NS.fitManualValues = saved.values;
          NS.fitnessTestDefs.forEach(t => { document.getElementById(`fitness-in-${t.id}`).value = NS.fitManualValues[t.id] || ''; });
        } else {
          NS.fitRunTests = NS.fitnessTestDefs.slice(); NS.fitRunIdx = saved.index;
          fitRunResults = saved.results; NS.fitRunCurrent = saved.current;
          NS.fitRunInterrupted = saved.interrupted; NS.fitRunResume = true;
        }
        fitnessDraftNotice('You have unsaved results. Resume the tests or manual entry.');
      } catch (error) {
        if (error instanceof SyntaxError || error.message === 'invalid draft') {
          try { localStorage.removeItem(key); } catch (_) { }
          fitnessDraftNotice('The draft could not be restored: it expired, was damaged or the tests changed.');
        } else fitnessDraftNotice('Could not read the draft on this device. Local storage is unavailable.');
      }
    }
    const discard = document.getElementById('btn-fitness-discard-drafts');
    discard.onclick = () => {
      if (NS.fitRunActive || NS.fitManualSaving || NS.fitnessOwner !== window.APP?.currentUid?.()) return;
      try {
        localStorage.removeItem(fitnessKey('manual')); localStorage.removeItem(fitnessKey('runner'));
        NS.fitManualValues = {}; NS.fitRunResume = false; fitRunResults = {}; NS.fitRunCurrent = '';
        document.querySelectorAll('#fitness-edit-form input').forEach(input => { input.value = ''; });
        document.getElementById('fitness-draft-notice').hidden = true;
        syncFitnessControls();
      } catch (_) { fitnessDraftNotice('Could not clear the local draft.'); }
    };
  }

  function syncFitnessControls() {
    const busy = NS.fitRunActive || NS.fitManualSaving || NS.fitnessLoadFailed;
    const actions = document.getElementById('btn-fitness-start-run')?.closest('.rz-stack');
    if (actions) actions.hidden = NS.fitRunActive || NS.fitnessLoadFailed;
    ['btn-fitness-start-run', 'btn-fitness-toggle-edit'].forEach(id => {
      const button = document.getElementById(id); if (button) button.disabled = busy;
    });
    const run = document.getElementById('btn-fitness-start-run');
    run.dataset.live = '1';
    run.textContent = NS.fitRunResume ? 'Resume tests' : 'Take tests in order';
    const discard = document.getElementById('btn-fitness-discard-drafts');
    discard.textContent = 'Discard unsaved results';
    discard.hidden = NS.fitRunActive || !(NS.fitRunResume || Object.values(NS.fitManualValues).some(v => v !== ''));
    discard.disabled = busy;
  }

  async function saveFitnessResults(results, owner) {
    if (!owner || owner !== window.APP?.currentUid?.()) throw new Error('409');
    const response = await fetch('/coach/fitness', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results, lang: 'en', owner_uid: owner }) });
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    if (owner !== window.APP?.currentUid?.() || ('owner_uid' in data && data.owner_uid !== owner)) throw new Error('409');
    return data;
  }

  function fitnessSaveError(error) {
    if (error.message === '409') return 'The profile changed. Saving has stopped. Reload the page to continue in the correct profile.';
    return ['400', '422'].includes(error.message)
      ? 'Check the entered results. Your data remains in the form.'
      : 'Could not save. Your results remain here — try again.';
  }

  function startFitnessRun() {
    if (!NS.fitnessTestDefs.length || NS.fitRunActive || NS.fitManualSaving || NS.fitnessOwner !== window.APP?.currentUid?.()) return;
    NS.fitRunActive = true;
    if (!NS.fitRunResume) {
      NS.fitRunTests = NS.fitnessTestDefs.slice(); NS.fitRunIdx = 0; fitRunResults = {};
      NS.fitRunCurrent = ''; NS.fitRunInterrupted = false;
    }
    NS.fitRunResume = false;
    document.getElementById('fitness-edit-form').hidden = true;
    const runner = document.getElementById('fitness-runner');
    runner.hidden = false;
    syncFitnessControls();
    if (NS.fitRunIdx >= NS.fitRunTests.length) renderFitnessRunSummary();
    else renderFitnessRunnerStep();
    saveFitnessDraft('runner');
    /* On a phone the test card stayed above the slider — the person saw two
       "Pass" buttons and did not see the test itself */
    try { runner.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (_) { }
  }

  function stopFitnessRunTimer() {
    if (fitRunTimerHandle) { clearInterval(fitRunTimerHandle); fitRunTimerHandle = null; }
  }

  function renderFitnessRunnerStep() {
    stopFitnessRunTimer();
    const t = NS.fitRunTests[NS.fitRunIdx];
    document.getElementById('fitness-runner-status').hidden = true;
    document.getElementById('btn-fitness-runner-save').disabled = false;
    document.getElementById('btn-fitness-runner-save').textContent = 'Save · next';
    document.getElementById('btn-fitness-runner-save').setAttribute('data-t', 's038');
    document.getElementById('btn-fitness-runner-skip').hidden = false;
    updateFitnessStepLabel();
    document.getElementById('fitness-runner-name').textContent = t.name;
    document.getElementById('fitness-runner-how').innerHTML =
      (t.how || []).map(step => `<li style="margin-bottom:3px">${step}</li>`).join('');

    const widget = document.getElementById('fitness-runner-widget');
    const prevVal = NS.fitRunCurrent;

    if (FITNESS_TIME_TESTS.includes(t.id)) {
      /* stopwatch: start when the person lifts off the floor / the test starts, stop
         when the position is held (plank) or balance is lost (balance).
         The result can still be corrected manually before saving. */
      widget.innerHTML = `
        <div style="text-align:center">
          <div class="mono" id="fitrun-stopwatch-disp" style="font-size:52px;font-weight:700">0.0</div>
          <div id="fitrun-stopwatch-unit" style="font-size:13px;color:var(--dim2);margin-top:2px">seconds</div>
          <button class="btn btn--primary" id="fitrun-stopwatch-btn" style="margin-top:14px;min-height:64px;min-width:64px;border-radius:50%;font-size:15px">Start</button>
        </div>
        <input type="number" step="any" inputmode="decimal" aria-label="${NS.H(t.name)}" class="search-input" id="fitrun-in-${t.id}" placeholder="or enter manually, ${t.unit}" style="min-height:44px;margin-top:14px" value="${NS.H(prevVal ?? '')}">`;
      let running = false, startTs = 0;
      const disp = document.getElementById('fitrun-stopwatch-disp');
      const inp = document.getElementById(`fitrun-in-${t.id}`);
      document.getElementById('fitrun-stopwatch-btn').onclick = (e) => {
        if (!running) {
          running = true; startTs = performance.now();
          NS.fitRunTimerRunning = true; saveFitnessDraft('runner');
          e.target.textContent = 'Stop';
          fitRunTimerHandle = setInterval(() => {
            disp.textContent = ((performance.now() - startTs) / 1000).toFixed(1);
          }, 100);
        } else {
          running = false;
          stopFitnessRunTimer();
          const secs = (performance.now() - startTs) / 1000;
          disp.textContent = secs.toFixed(1);
          inp.value = secs.toFixed(1);
          NS.fitRunTimerRunning = false; NS.fitRunInterrupted = false;
          NS.fitRunCurrent = inp.value; saveFitnessDraft('runner');
          e.target.textContent = 'Start';
        }
      };
    } else if (FITNESS_WINDOW_TESTS.includes(t.id)) {
      /* 60-second timer + manual rep counter — counted by
         the person themselves (the system does not see movements outside the video); the timer only keeps
         the window honest. */
      widget.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div class="mono" id="fitrun-window-clock" style="font-size:32px;font-weight:700">60</div>
          <button class="btn btn--outline" id="fitrun-window-start" style="min-height:44px">Start 60s</button>
        </div>
        <div style="margin-top:14px;display:flex;align-items:center;gap:12px;justify-content:center">
          <button class="btn btn--outline" id="fitrun-window-minus" style="width:64px;height:64px;font-size:26px">−</button>
          <div class="mono" id="fitrun-window-count" style="font-size:48px;font-weight:700;min-width:70px;text-align:center">0</div>
          <button class="btn btn--primary" id="fitrun-window-plus" style="width:64px;height:64px;font-size:26px">+</button>
        </div>
        <input type="hidden" id="fitrun-in-${t.id}" value="${NS.H(prevVal ?? '')}">`;
      let count = prevVal != null ? Number(prevVal) : 0;
      const countDisp = document.getElementById('fitrun-window-count');
      const hidIn = document.getElementById(`fitrun-in-${t.id}`);
      countDisp.textContent = count;
      const sync = () => { countDisp.textContent = count; hidIn.value = count;
        NS.fitRunCurrent = String(count); saveFitnessDraft('runner'); };
      document.getElementById('fitrun-window-plus').onclick = () => { count++; sync(); };
      document.getElementById('fitrun-window-minus').onclick = () => { count = Math.max(0, count - 1); sync(); };
      document.getElementById('fitrun-window-start').onclick = (e) => {
        const startedAt = performance.now();
        count = 0; sync();
        NS.fitRunTimerRunning = true; saveFitnessDraft('runner');
        const clock = document.getElementById('fitrun-window-clock');
        clock.textContent = '60';
        e.target.disabled = true;
        fitRunTimerHandle = setInterval(() => {
          /* Background throttling delays the tick; duration is measured
             by monotonic time, not by the number of callbacks run. */
          const left = Math.max(0, Math.ceil(60 - (performance.now() - startedAt) / 1000));
          clock.textContent = left;
          if (left <= 0) { stopFitnessRunTimer(); e.target.disabled = false;
            NS.fitRunTimerRunning = false; NS.fitRunInterrupted = false; saveFitnessDraft('runner'); }
        }, 250);
      };
    } else {
      /* distance/flexibility — measured with a tape after the movement; just a number. */
      /* the norm reference is a caption under the field, not a placeholder
         (it gets cut off); the field holds only the unit */
      widget.innerHTML = `<input type="number" step="any" inputmode="decimal" aria-label="${NS.H(t.name)}" class="search-input" id="fitrun-in-${t.id}" placeholder="${NS.H(t.unit)}" style="min-height:52px;font-size:20px;text-align:center" value="${NS.H(prevVal ?? '')}" autofocus>`
        + (t.target ? `<p id="fitrun-reference" class="rz-note">reference: ${String(t.target).replace(/</g, '&lt;')}</p>` : '');
    }
    const currentInput = document.getElementById(`fitrun-in-${t.id}`);
    currentInput.oninput = () => { NS.fitRunCurrent = currentInput.value; saveFitnessDraft('runner'); };
    if (NS.fitRunInterrupted) {
      const status = document.getElementById('fitness-runner-status'); status.hidden = false;
      status.textContent = 'Interrupted test: the timer has stopped. Repeat the measurement; saved values can be corrected.';
    }

    document.getElementById('btn-fitness-runner-save').onclick = () => {
      const el = document.getElementById(`fitrun-in-${t.id}`);
      if (el && el.value !== '') fitRunResults[t.id] = el.value;
      advanceFitnessRun();
    };
    document.getElementById('btn-fitness-runner-skip').onclick = () => advanceFitnessRun();
  }

  async function advanceFitnessRun() {
    stopFitnessRunTimer();
    NS.fitRunTimerRunning = false; NS.fitRunInterrupted = false; NS.fitRunCurrent = '';
    NS.fitRunIdx++;
    const revision = saveFitnessDraft('runner');
    if (NS.fitRunIdx >= NS.fitRunTests.length) {
      if (!Object.keys(fitRunResults).length) { clearFitnessDraft('runner', NS.fitnessOwner, revision); finishFitnessRun(); return; }
      renderFitnessRunSummary();
      await persistFitnessRun();
      return;
    }
    renderFitnessRunnerStep();
  }

  function renderFitnessRunSummary() {
    stopFitnessRunTimer();
    updateFitnessStepLabel();
    document.getElementById('fitness-runner-name').textContent = 'Your results';
    document.getElementById('fitness-runner-how').replaceChildren();
    document.getElementById('fitness-runner-widget').innerHTML = NS.fitRunTests
      .map(t => `<div class="rz-field"><label class="rz-label" for="fitrun-summary-${NS.H(t.id)}">${NS.H(t.name)} (${NS.H(t.unit)})</label>
        <input id="fitrun-summary-${NS.H(t.id)}" class="search-input" type="number" step="any" inputmode="decimal" value="${NS.H(fitRunResults[t.id])}" style="min-height:44px"></div>`).join('');
    document.getElementById('btn-fitness-runner-skip').hidden = true;
    const button = document.getElementById('btn-fitness-runner-save');
    button.removeAttribute('data-t');
    button.textContent = 'Retry save';
    button.disabled = false;
    button.onclick = persistFitnessRun;
    document.querySelectorAll('#fitness-runner-widget input').forEach(input => {
      input.oninput = () => {
        const id = input.id.replace('fitrun-summary-', '');
        if (input.value === '') delete fitRunResults[id]; else fitRunResults[id] = input.value;
        saveFitnessDraft('runner');
      };
    });
    const status = document.getElementById('fitness-runner-status'); status.hidden = false;
    status.textContent = 'Results have not been saved yet. Check them and retry save.';
  }

  function finishFitnessRun() {
    document.getElementById('fitness-runner').hidden = true;
    NS.fitRunActive = false;
    NS.fitRunResume = false;
    fitRunResults = {};
    if (!Object.values(NS.fitManualValues).some(v => v !== '')) document.getElementById('fitness-draft-notice').hidden = true;
    syncFitnessControls();
  }

  function updateFitnessStepLabel() {
    const label = document.getElementById('fitness-runner-step');
    label.dataset.live = '1';
    label.textContent = NS.fitRunIdx >= NS.fitRunTests.length
      ? 'Tests complete'
      : `TEST ${NS.fitRunIdx + 1} OF ${NS.fitRunTests.length}`;
  }

  async function persistFitnessRun() {
    if (NS.fitRunSaving) return;
    const button = document.getElementById('btn-fitness-runner-save');
    const status = document.getElementById('fitness-runner-status');
    const inputs = [...document.querySelectorAll('#fitness-runner-widget input')];
    NS.fitRunTests.forEach(t => {
      const input = document.getElementById(`fitrun-summary-${t.id}`);
      if (!input) return;
      if (input.value === '') delete fitRunResults[t.id];
      else fitRunResults[t.id] = input.value;
    });
    status.hidden = false;
    if (!Object.keys(fitRunResults).length) {
      status.textContent = 'Enter at least one result.';
      return;
    }
    NS.fitRunSaving = true;
    const owner = NS.fitnessOwner;
    const revision = saveFitnessDraft('runner');
    inputs.forEach(input => { input.disabled = true; });
    button.disabled = true;
    status.textContent = 'Saving results…';
    try {
      NS.renderFitness(await saveFitnessResults(fitRunResults, owner));
      clearFitnessDraft('runner', owner, revision);
      finishFitnessRun();
    } catch (error) { status.textContent = fitnessSaveError(error); }
    finally {
      NS.fitRunSaving = false; button.disabled = false;
      inputs.forEach(input => { input.disabled = false; });
    }
  }

  function renderSkills(data) {
    const card = document.getElementById('progress-skills');
    const table = document.getElementById('skills-table');
    if (!card || !table) return;
    const jumps = (data.skill_map && data.skill_map.jumps) || [];
    if (!jumps.length) return;
    /* A table where EVERY row says "not enough data" is not a skill
       profile, but a message about its absence, stretched across
       the card. We show it only when there is something to show. */
    if (!jumps.some(j => j.enough_data)) { card.hidden = true; return; }
    /* A short honesty marker per jump with a small sample; the long
       explanation ("only N attempt(s) — not enough to tell a one-off
       slip from a real gap") stands once under the table. */
    const anyFew = jumps.some(j => !j.enough_data);
    table.innerHTML = jumps.map(j => {
      let standing;
      if (!j.enough_data) {
        standing = `<span style="color:var(--dim2)">` + `not enough data · ${j.attempts} ${j.attempts === 1 ? 'attempt' : 'attempts'}` + `</span>`;
      } else {
        const gaps = j.gaps || [];
        const top = gaps.find(gap => gap.verdict === 'not_owned')
          || gaps.find(gap => gap.verdict === 'unstable');
        if (top) {
          standing = `<span style="color:var(--short)">` + 'working on · '
            + (NS.SKILL_ERR_UK[top.code] || top.code)
            + (Number.isFinite(top.in_attempts) && Number.isFinite(top.of)
              ? ` · ${top.in_attempts}/${top.of} assessed` : '') + `</span>`;
        } else if ((j.clean_assessed_total ?? j.attempts) >= NS.MIN_ATTEMPTS_FOR_PCT && j.clean_pct >= 70) {
          standing = `<span style="color:var(--clean)">` + `owned · ${j.attempts} attempt${j.attempts === 1 ? '' : 's'}` + `</span>`;
        } else {
          standing = `<span style="color:var(--dim2)">` + `working on · ${j.attempts} attempt${j.attempts === 1 ? '' : 's'}` + `</span>`;
        }
      }
      /* The share — only for a sufficient sample (the same rule as in
         MIN_ATTEMPTS_FOR_PCT): "0% clean" from a single attempt is not a measurement.
         Rotations — only when there is a number; "best — · median —" is an empty
         line that says nothing. */
      const pct = j.enough_data && (j.clean_assessed_total ?? j.attempts) >= NS.MIN_ATTEMPTS_FOR_PCT && typeof j.clean_pct === 'number'
        ? `<span class="mono" style="font-size:14px">${j.clean_pct}% clean</span>` : '';
      const revs = (j.revolutions_best != null || j.revolutions_median != null)
        ? `<span class="mono" style="color:var(--dim2)">${j.revolutions_best != null ? `best ${j.revolutions_best.toFixed(2)}` : ''}${j.revolutions_best != null && j.revolutions_median != null ? ' · ' : ''}${j.revolutions_median != null ? `median ${j.revolutions_median.toFixed(2)}` : ''} rev</span>` : '';
      return `<div style="padding:12px 0;border-bottom:1px solid var(--line)">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <span style="font-size:15px;font-weight:600">${(window.APP && window.APP.jumpNameLocal && window.APP.jumpNameLocal(j.jump)) || j.jump}</span>
          ${pct}
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:13px;gap:8px;flex-wrap:wrap">
          <span>${standing}</span>
          ${revs}
        </div>
      </div>`;
    }).join('') + (anyFew
      ? `<div style="padding-top:8px;font-size:12px;color:var(--dim2)">` + '“not enough data” — too few attempts to tell a one-off miss from a real skill gap' + `</div>`
      : '');
    NS.lastSkillJumps = jumps;
    card.hidden = false;
  }

  function renderDefaultHistory() {
    const container = document.getElementById('log-rows-container');
    /* An empty journal leads, not only says where to go: on a phone a hint
       to use the bottom tab is one more tap to guess at, so
       the empty state has an action. */
    if (container) container.innerHTML =
      '<div class="rz-empty">' +
      'No analyses yet. Upload a jump video and the log will appear here.' +
      '<div class="rz-empty__act"><button type="button" class="btn btn--primary" onclick="window.APP.go(&quot;record&quot;)">' +
      'Record or choose a video' + '</button></div></div>';
    /* nothing to shorten and nothing to count in an empty journal */
    const qbtn = document.getElementById('btn-quick-mode'); if (qbtn) qbtn.hidden = true;
    const cnt = document.getElementById('log-count'); if (cnt) cnt.textContent = '';
  }

  function renderLearnTerms(cat = NS.currentLearnCat, query = NS.currentLearnSearch) {
    const container = document.getElementById('learn-terms-list');
    if (!container) return;
    let keys = Object.keys(NS.LEARN_TERMS_DATA);
    if (cat !== 'all') keys = keys.filter(k => NS.LEARN_TERMS_DATA[k].cat === cat);
    if (query.trim()) {
      const q = query.toLowerCase();
      keys = keys.filter(k => {
        const t = NS.LEARN_TERMS_DATA[k];
        const tt = t.title, tr = t.rule, td = t.desc;
        return tt.toLowerCase().includes(q) || tr.toLowerCase().includes(q) || td.toLowerCase().includes(q);
      });
    }
    if (!keys.length) {
      container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--dim2);font-size:14px">' + 'No matches. Press Enter to ask the knowledge base.' + '</div>';
      return;
    }
    /* The term row is just the name: cut off at the 60th
       symbol, the rule's preview gave five lines of jargon that added nothing
       to the choice. The full text is behind a tap. */
    container.innerHTML = keys.map(k => {
      const t = NS.LEARN_TERMS_DATA[k];
      return `
        <div role="button" tabindex="0" class="session-block-row" style="min-height:56px;cursor:pointer" onclick="window.COACH.openTermSheet('${k}')">
          <div style="flex:1;font-weight:600;font-size:15px">${t.title}</div>
          <span class="mono" style="color:var(--dim);font-size:18px">›</span>
        </div>`;
    }).join('');
  }

  let termOpener = null;
  function closeTermSheet() {
    const sheet = document.getElementById('sheet-term');
    sheet.hidden = true; sheet.style.display = 'none';
    if (termOpener?.isConnected) termOpener.focus({ preventScroll: true });
  }
  function openTermSheet(key) {
    termOpener = document.activeElement;
    const t = NS.LEARN_TERMS_DATA[key] || NS.LEARN_TERMS_DATA['under'];
    const sheet = document.getElementById('sheet-term');
    if (!sheet) return;
    document.getElementById('sheet-term-title').textContent = t.title;
    document.getElementById('sheet-term-rule').innerHTML = t.rule;
    document.getElementById('sheet-term-desc').textContent = t.desc;
    const btnAskCoach = document.getElementById('btn-term-ask-coach');
    if (btnAskCoach) btnAskCoach.onclick = () => {
      closeTermSheet();
      window.APP.go('coach');
      NS.askCoach(`Explain in more detail: ${t.title}`);
    };
    sheet.hidden = false; sheet.style.display = 'flex';
    document.getElementById('btn-close-term-sheet').focus();
    sheet.onkeydown = e => {
      if (e.key === 'Escape') { e.preventDefault(); closeTermSheet(); }
      if (e.key === 'Tab') {
        const buttons = [...sheet.querySelectorAll('button')].filter(b => !b.hidden && !b.disabled);
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    sheet.onclick = e => { if (e.target === sheet) closeTermSheet(); };
  }

  Object.assign(NS, {
     FITNESS_TIME_TESTS, fitnessSignature, saveFitnessDraft, clearFitnessDraft, restoreFitnessDrafts,
     syncFitnessControls, saveFitnessResults, fitnessSaveError, startFitnessRun, updateFitnessStepLabel,
     renderSkills, renderDefaultHistory, renderLearnTerms, closeTermSheet, openTermSheet,
  });
})();
