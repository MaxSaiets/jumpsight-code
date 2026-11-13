/* Progress screen: weekly summary and trend, skills, goal and fitness tests. */
(function () {
  'use strict';
  const NS = window.JS.coach;
  const WEEK_S = 7 * 86400;

  /* THIS WEEK: a reply to parents within a minute — only
     journal counters for the last 7 days, without any new assessment. */
  function renderWeekSummary(items) {
    const card = document.getElementById('progress-week');
    if (!card) return;
    const since = Date.now() / 1000 - WEEK_S;
    const rows = (items || []).filter(a => a && isFinite(Number(a.ts)) && Number(a.ts) >= since
      && a.jump && a.jump !== 'None' && a.outcome !== 'not_measured');
    if (!rows.length) { card.hidden = true; return; }
    const days = new Set(rows.map(a => new Date(Number(a.ts) * 1000).toDateString())).size;
    const errsOf = a => Array.isArray(a.errors) ? a.errors : [];
    /* drops — only confident ones (medium+); "maybe" — separately, not
       in the count. "Clean" is not used: it requires checking ALL features,
       and two (two legs, knee) from one angle are never checked.
       "No findings" has the same meaning as "no errors found". */
    const fallTier = a => String((a.errors_conf || {}).fall || 'low').toLowerCase();
    const falls = rows.filter(a => errsOf(a).includes('fall') && ['medium', 'high'].includes(fallTier(a))).length;
    const fallsMaybe = rows.filter(a => errsOf(a).includes('fall') && !['medium', 'high'].includes(fallTier(a))).length;
    const noFind = window.APP && window.APP.historyNoFindings
      ? rows.filter(a => window.APP.historyNoFindings(a)).length
      : rows.filter(a => !errsOf(a).length && Number(a.checks_run) > 0).length;
    const tile = (v, l) => `<div class="rz-week__t"><div class="rz-week__v mono">${v}</div><div class="rz-week__l">${l}</div></div>`;
    card.innerHTML = `<span class="rz-eyebrow">Last 7 days</span>
      <div class="rz-week">${tile(rows.length, (rows.length === 1 ? 'jump' : 'jumps'))}${
        tile(days, (days === 1 ? 'day with video' : 'days with video'))}${
        tile(noFind, 'no errors found')}${tile(falls, (falls === 1 ? 'fall' : 'falls')
          + (fallsMaybe ? ` · ${fallsMaybe} more possible` : ''))}</div>`;
    card.hidden = false;
  }

  function renderWeeklyTrend(items) {
    /* design/3.5: weekly bar charts + "what changed" — from REAL
       /coach/history, without any assessment. A week with fewer than 2 attempts does not
       draw a trend line (one point proves nothing); it shows
       a hatched bar with an explanation, as in the mockup. */
    const card = document.getElementById('progress-trend');
    const body = document.getElementById('progress-trend-body');
    if (!card || !body) return;
    /* Same rotation-validity rule: only rotations that the engine recognized as a measurement
       (rev_usable) go into the trend. A row without a usable number gives no column, so
       "a week with data" is counted only over such rows — otherwise the card
       showed one column and the caption "too few weeks". */
    const usableRev = a => a.rev_usable !== false && isFinite(Number(a.revolutions)) && Number(a.revolutions) > 0;
    const rows = (items || []).filter(a => a && a.ts && isFinite(Number(a.ts)) && usableRev(a));
    /* A trend is a comparison over TIME. Two analyses on one day are not a trend:
       a card of six empty columns with the caption "few weeks"
       would occupy the screen to say there was nothing to say. The condition is
       substantive: two DIFFERENT weeks with data (measured on "Progress"
       with two analyses, 7 of 10 cards reported a lack of
       data). */
    if (rows.length < 2) { card.hidden = true; return; }
    const _wk = a => Math.floor(Number(a.ts) / WEEK_S);
    if (new Set(rows.map(_wk)).size < 2) { card.hidden = true; return; }

    const now = Date.now() / 1000;
    const NW = 6;
    const weeks = Array.from({ length: NW }, () => []);
    for (const a of rows) {
      const age = now - Number(a.ts);
      const idx = NW - 1 - Math.floor(age / WEEK_S);
      if (idx >= 0 && idx < NW) weeks[idx].push(a);
    }
    if (!weeks.some(w => w.length)) { card.hidden = true; return; }

    const bestOf = (w, field) => {
      const vs = w.map(a => Number(a[field])).filter(v => isFinite(v) && v > 0);
      return vs.length ? Math.max(...vs) : null;
    };
    const bests = weeks.map(w => bestOf(w, 'revolutions'));
    const maxBest = Math.max(...bests.filter(v => v != null), 0.01);

    /* "T1…T6" says nothing to parents; the label is the week's start date */
    const weekLabel = i => new Date((now - (NW - i) * WEEK_S) * 1000)
      .toLocaleDateString(NS.LOC(), { day: 'numeric', month: 'numeric' });
    const bars = weeks.map((w, i) => {
      const b = bests[i];
      const wNum = weekLabel(i);
      if (b == null) {
        return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px" title="no videos">
          <div style="width:100%;height:4px;border-radius:3px;background:var(--line)"></div>
          <div class="mono" style="font-size:10px;color:var(--dim)">${wNum}</div>
        </div>`;
      }
      /* number above the column: without it the bar height says nothing */
      const h = Math.max(6, Math.round((b / maxBest) * 84));
      const solo = w.length < 2;
      const bg = solo
        ? 'repeating-linear-gradient(135deg,var(--line) 0 5px,var(--well) 5px 10px)'
        : (i === weeks.length - 1 ? 'var(--action)' : 'var(--line2)');
      const tip = solo ? '1 attempt — too few to compare'
                       : `${w.length} attempt${w.length === 1 ? '' : 's'}`;
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px" title="${tip}">
          <div class="mono" style="font-size:11px;color:${solo ? 'var(--dim)' : 'var(--ink)'}">${b.toFixed(2)}</div>
          <div style="width:100%;height:${h}px;border-radius:3px;background:${bg}"></div>
          <div class="mono" style="font-size:10px;color:${solo ? 'var(--dim)' : 'var(--dim2)'}">${wNum}</div>
        </div>`;
    }).join('');

    const firstIdx = weeks.findIndex(w => bestOf(w, 'revolutions') != null);
    const lastIdx = (() => { for (let i = weeks.length - 1; i >= 0; i--) if (bestOf(weeks[i], 'revolutions') != null) return i; return -1; })();
    let movedHtml = '';
    if (firstIdx >= 0 && lastIdx > firstIdx) {
      /* a change within the measurement error is not progress. Next to each
         number its ±; if the bands of two weeks overlap, we say so,
         without an arrow. Without a known error the row is not shown. */
      const bestRow = (w, field) => w.filter(a => isFinite(Number(a[field])) && Number(a[field]) > 0)
        .sort((x, y) => Number(y[field]) - Number(x[field]))[0] || null;
      const halfOf = (r, field) => {
        if (!r) return null;
        if (field === 'revolutions') { const h = Number(r.band); return isFinite(h) && h > 0 ? h : null; }
        if (field === 'height_m' && Array.isArray(r.height_band_m) && r.height_band_m.length === 2) {
          const h = (Number(r.height_band_m[1]) - Number(r.height_band_m[0])) / 2; return isFinite(h) && h > 0 ? h : null;
        }
        return null;
      };
      const rowFor = (field, unit, digits, k = 1) => {
        const ra = bestRow(weeks[firstIdx], field), rb = bestRow(weeks[lastIdx], field);
        const ha = halfOf(ra, field), hb = halfOf(rb, field);
        if (!ra || !rb || ha == null || hb == null) return '';
        const a = Number(ra[field]), b = Number(rb[field]);
        const fmt = (v, h) => `${(v * k).toFixed(digits)}<span style="color:var(--dim);font-size:12px"> ±${(h * k).toFixed(digits) === (0).toFixed(digits) ? (1 / Math.pow(10, digits)).toFixed(digits) : (h * k).toFixed(digits)}</span>`;
        const within = Math.abs(b - a) <= ha + hb;
        const verdict = within
          ? `<span style="font-size:12px;color:var(--dim2)">within error</span>`
          : `<span style="font-size:12px;color:${b > a ? 'var(--clean)' : 'var(--bad)'}">${b > a ? 'up' : 'down'}</span>`;
        return `<div style="display:grid;grid-template-columns:1fr auto;gap:2px 10px;border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:8px">
          <span style="font-weight:600;font-size:14px">${unit}</span>
          <span class="mono" style="font-size:15px;text-align:right">${fmt(a, ha)} → ${fmt(b, hb)}</span>
          <span></span><span style="text-align:right">${verdict}</span>
        </div>`;
      };
      const movedRows = rowFor('revolutions', 'Rotations in flight', 2)
        + rowFor('height_m', 'Height, cm', 0, 100);
      movedHtml = movedRows ? `<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--line)">
        <div style="font-size:11px;letter-spacing:.08em;color:var(--dim2);margin-bottom:10px">WHAT CHANGED · BEST OF THE WEEK</div>
        ${movedRows}
      </div>` : '';
    } else {
      movedHtml = `<div style="margin-top:12px;font-size:13px;color:var(--dim2)">` + 'Not enough weeks with data to compare — a trend appears once at least two weeks have attempts.' + `</div>`;
    }

    body.innerHTML = `<div class="rz-note" style="margin:0 0 8px">most measured rotations per week</div>
      <div style="display:flex;align-items:flex-end;gap:9px;height:118px">${bars}</div>${movedHtml}`;
    card.hidden = false;
  }

  const FITNESS_GRADE_COLOR = { A: 'var(--clean)', B: 'var(--action)', C: 'var(--short)' };
  const SKILL_ERR_I18N = {
    fall: ['falls'], two_foot_landing: ['two-foot landings'],
    touch_down: ['free-foot touches'], hand_down: ['hand downs'],
    step_out: ['step-outs'], stiff_landing_knee: ['stiff landing knee'],
    tilted_axis: ['tilted axis'], late_check_out: ['late check-out'],
  };
  const SKILL_ERR_UK = new Proxy({}, { get: (_, k) => {
    const e = SKILL_ERR_I18N[k]; return e ? e[0] : undefined; } });
  NS.fitnessTestDefs = [];
  NS.lastSkillJumps = [];
  let fitnessLoadVersion = 0;

  async function loadFitnessAndSkills() {
    const version = ++fitnessLoadVersion;
    const owner = window.APP?.currentUid?.();
    try {
      const responses = await Promise.allSettled([
        fetch(`/coach/fitness/tests?lang=en`),
        fetch(`/coach/fitness?lang=en`),
        fetch(`/coach/skill_profile?lang=en`),
      ]);
      const [testsRes, fitRes, skillRes] = responses.map(r => r.status === 'fulfilled' ? r.value : null);
      const tests = testsRes?.ok ? await testsRes.json().catch(() => null) : null;
      const fitness = fitRes?.ok ? await fitRes.json().catch(() => null) : null;
      if (version !== fitnessLoadVersion) return;
      if (owner && owner === window.APP?.currentUid?.() && Array.isArray(tests) && tests.length
          && (!NS.fitnessOwner || NS.fitnessOwner === owner)) {
        NS.fitnessTestDefs = tests;
        if (NS.fitRunActive && NS.fitnessSignature(NS.fitRunTests) === NS.fitnessSignature(tests)) NS.fitRunTests = tests.slice();
        relocalizeFitnessControls();
      }
      if (owner && owner === window.APP?.currentUid?.()
          && Array.isArray(tests) && tests.length && fitness
          && (!('owner_uid' in fitness) || fitness.owner_uid === owner)) {
        NS.fitnessTestDefs = tests;
        if (!NS.fitnessOwner) NS.fitnessOwner = owner;
        if (NS.fitnessOwner === owner) {
          NS.fitnessLoadFailed = false;
          document.getElementById('fitness-load-status').hidden = true;
          document.getElementById('btn-fitness-load-retry').hidden = true;
          renderFitness(fitness);
        }
      } else if (owner && owner === window.APP?.currentUid?.()) showFitnessLoadError();
      const skills = skillRes?.ok ? await skillRes.json().catch(() => null) : null;
      if (skills) NS.renderSkills(skills);
      NS.loadWeekPlan();
      loadGoal();
    } catch (_) { if (version === fitnessLoadVersion && owner && owner === window.APP?.currentUid?.()) showFitnessLoadError(); }
  }

  function showFitnessLoadError() {
    NS.fitnessLoadFailed = true;
    document.getElementById('progress-fitness').hidden = false;
    document.getElementById('fitness-groups-summary').hidden = true;
    document.getElementById('fitness-tests-details').hidden = true;
    const status = document.getElementById('fitness-load-status');
    status.hidden = false;
    status.textContent = 'Could not load test results. Retry loading.';
    const retry = document.getElementById('btn-fitness-load-retry');
    retry.hidden = false;
    retry.textContent = 'Retry loading';
    retry.onclick = async () => {
      if (retry.disabled) return;
      retry.disabled = true;
      try { await loadFitnessAndSkills(); } finally { retry.disabled = false; }
    };
    NS.syncFitnessControls();
  }

  function relocalizeFitnessControls() {
    // The text changes, not the DOM of the field: the timer and input closures live on.
    NS.fitnessTestDefs.forEach(t => {
      const input = document.getElementById(`fitness-in-${t.id}`);
      const label = input?.parentElement.querySelector('label');
      if (label) label.innerHTML = `${NS.H(t.name)} <span style="color:var(--dim2);font-weight:400">(${NS.H(t.unit)})</span>`;
      if (input) input.placeholder = t.target || '';
    });
    const save = document.getElementById('btn-fitness-save');
    if (save) save.textContent = NS.fitManualSaving ? 'Saving…' : 'Save results';
    if (!NS.fitRunActive) return;
    NS.updateFitnessStepLabel();
    if (NS.fitRunIdx >= NS.fitRunTests.length) {
      document.getElementById('fitness-runner-name').textContent = 'Your results';
      NS.fitRunTests.forEach(t => {
        const label = document.querySelector(`label[for="fitrun-summary-${t.id}"]`);
        if (label) label.textContent = `${t.name} (${t.unit})`;
      });
      if (!NS.fitRunSaving) document.getElementById('btn-fitness-runner-save').textContent = 'Retry save';
      return;
    }
    const t = NS.fitRunTests[NS.fitRunIdx];
    document.getElementById('fitness-runner-name').textContent = t.name;
    document.getElementById('fitness-runner-how').innerHTML = (t.how || []).map(step => `<li style="margin-bottom:3px">${NS.H(step)}</li>`).join('');
    const input = document.getElementById(`fitrun-in-${t.id}`);
    if (input) {
      input.setAttribute('aria-label', t.name);
      input.placeholder = NS.FITNESS_TIME_TESTS.includes(t.id)
        ? 'or enter manually, ' + t.unit : t.unit;
    }
    const stopwatch = document.getElementById('fitrun-stopwatch-btn');
    if (stopwatch) stopwatch.textContent = NS.fitRunTimerRunning ? 'Stop' : 'Start';
    const unit = document.getElementById('fitrun-stopwatch-unit');
    if (unit) unit.textContent = 'seconds';
    const windowStart = document.getElementById('fitrun-window-start');
    if (windowStart) windowStart.textContent = 'Start 60s';
    const reference = document.getElementById('fitrun-reference');
    if (reference) reference.textContent = `reference: ${t.target || ''}`;
  }

  async function loadGoal() {
    /* The card always renders (lastSkillJumps is filled only when renderSkills
       sees a jump with enough_data, which is rare on the first analyses; hiding the
       card would be an empty state that lies); the form below separately
       checks lastSkillJumps and honestly says if there is nothing to choose from yet. */
    try {
      const r = await fetch(`/coach/skill_goal?lang=en`);
      renderGoal(r.ok ? await r.json() : {});
    } catch (_) { renderGoal({}); }
  }

  function renderGoal(g) {
    const card = document.getElementById('progress-goal');
    const body = document.getElementById('goal-body');
    if (!card || !body) return;
    const hasGoal = g && g.jump;
    if (hasGoal) {
      const assessed = g.clean_assessed_total ?? g.attempts;
      const hasPercentage = Number.isFinite(g.current_pct) && assessed >= NS.MIN_ATTEMPTS_FOR_PCT;
      body.innerHTML = `
        <div style="font-size:13px;color:var(--dim2)">by ${g.target_date}</div>
        <h3 style="margin:6px 0 0;font-size:20px;font-weight:700">${g.jump}, clean ${g.target_pct}%</h3>
        <div style="margin-top:10px;display:flex;align-items:baseline;gap:10px">
          <span class="mono" style="font-size:36px;font-weight:700">${hasPercentage ? g.current_pct : '—'}</span>
          <span style="font-size:14px;color:var(--dim2)">${hasPercentage
            ? `% now, goal ${g.target_pct}%`
            : 'too few execution assessments'}</span>
        </div>
        <div style="margin-top:10px;height:8px;border-radius:4px;background:var(--well);overflow:hidden">
          <div style="width:${hasPercentage ? g.progress_pct : 0}%;height:8px;background:var(--action)"></div>
        </div>
        <div style="margin-top:10px;font-size:13px;color:var(--dim2)">${`Journal: ${g.clean} clean of ${assessed} assessed executions; ${g.attempts} total attempts.`}</div>`;
    } else if (!NS.lastSkillJumps.length) {
      /* A "Set goal" button that opens only the text "nothing to choose from yet"
         would be a dead tap. While no jump has reached MIN_ATTEMPTS
         analyzed attempts (skills.py), the reason stands in the card at once,
         with the current count. */
      const counts = {};
      (Array.isArray(NS.historyData) ? NS.historyData : []).forEach(a => {
        if (!a || !a.jump || a.jump === 'None' || a.outcome === 'not_measured') return;
        if (!NS.nameIsSure(a)) return;
        counts[a.jump] = (counts[a.jump] || 0) + 1;
      });
      const top = Object.entries(counts).sort((x, y) => y[1] - x[1])[0];
      const nm = top ? ((window.APP && window.APP.jumpNameLocal && window.APP.jumpNameLocal(top[0])) || top[0]) : '';
      body.innerHTML = `<div class="rz-note" style="margin:0">${`Progress goals unlock after 3 analyses of the same jump${top ? `. ${nm}: ${top[1]} of 3` : ''}.`}</div>`;
      /* Without any analysis the "Goal" card only explained
         a rule the person cannot yet meet — an empty "Progress"
         screen had three blocks instead of one invitation. */
      if (!top) { card.hidden = true; return; }
    } else {
      /* no goal — no body at all: heading and button on one line */
      body.innerHTML = '';
    }
    card.hidden = false;

    const toggleBtn = document.getElementById('btn-goal-edit');
    if (toggleBtn) {
      toggleBtn.textContent = hasGoal ? 'Change goal' : 'Set a goal';
      toggleBtn.hidden = !hasGoal && !NS.lastSkillJumps.length;
    }
    const form = document.getElementById('goal-form');
    if (toggleBtn && form && !toggleBtn.dataset.bound) {
      toggleBtn.dataset.bound = '1';
      toggleBtn.onclick = () => {
        form.hidden = !form.hidden;
        if (!form.hidden) buildGoalForm();
      };
    }
  }

  function buildGoalForm() {
    const form = document.getElementById('goal-form');
    if (!form) return;
    if (!NS.lastSkillJumps.length) {
      form.innerHTML = `<div style="font-size:14px;color:var(--dim2);line-height:1.5">Not enough analysed jumps yet to pick a goal from. Analyse a few attempts and they will show up here.</div>`;
      return;
    }
    form.innerHTML = `
      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">Which jump</label>
      <select class="search-input" id="goal-in-jump" style="min-height:44px;margin-bottom:10px">
        ${NS.lastSkillJumps.map(j => `<option value="${j.jump}">${j.jump}</option>`).join('')}
      </select>
      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">Target % clean attempts</label>
      <input type="number" min="1" max="100" class="search-input" id="goal-in-pct" placeholder="e.g. 60" style="min-height:44px;margin-bottom:10px">
      <label style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">By what date</label>
      <input type="date" class="search-input" id="goal-in-date" style="min-height:44px;margin-bottom:12px">
      <button class="btn btn--primary" id="btn-goal-save" style="width:100%;min-height:48px">Save goal</button>`;
    const saveBtn = document.getElementById('btn-goal-save');
    if (saveBtn) saveBtn.onclick = async () => {
      const jump = document.getElementById('goal-in-jump').value;
      const pct = document.getElementById('goal-in-pct').value;
      const date = document.getElementById('goal-in-date').value;
      if (!jump || !pct || !date) return;
      try {
        const r = await fetch('/coach/skill_goal', { method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ jump, target_pct: Number(pct), target_date: date, lang: 'en' }) });
        if (r.ok) { renderGoal(await r.json()); form.hidden = true; }
      } catch (_) { }
    };
  }

  function renderFitness(data) {
    const card = document.getElementById('progress-fitness');
    if (!card || !NS.fitnessTestDefs.length) return;
    const profile = data.profile || {};
    const groups = profile.groups || {};
    const raw = profile.raw || {};
    const bands = profile.bands || {};

    const summary = document.getElementById('fitness-groups-summary');
    if (summary) {
      summary.hidden = false;
      const names = { 'leg strength': 'leg strength', flexibility: 'flexibility',
            endurance: 'endurance', balance: 'balance' };
      /* Four separate boxes, each with the word "not measured", are four
         cards that together carry one fact: no tests yet. While
         no group is measured, we show ONE line; as soon as the
         first result appears, the grid returns. */
      const _anyMeasured = Object.keys(names).some(g => groups[g]);
      if (!_anyMeasured) {
        summary.innerHTML = `<div style="font-size:13px;color:var(--dim2)">` +
          (Object.values(raw).some(v => v != null && v !== '')
            ? 'Results saved, but no reference band applies. Check the entered values in the details.'
            : 'No tests taken yet — take them to see your strong and weak areas.') +
          `</div>`;
      } else
      summary.innerHTML = Object.keys(names).map(g => {
        const gr = groups[g];
        const color = gr ? FITNESS_GRADE_COLOR[gr.grade] : 'var(--dim)';
        const label = gr ? gr.label : 'not measured';
        return `<div class="metric-box" style="flex:1;min-width:120px;padding:10px 12px">
          <div style="font-size:11px;color:var(--dim2);text-transform:capitalize">${names[g]}</div>
          <div style="font-size:13px;font-weight:600;margin-top:2px;color:${color}">${label}</div>
        </div>`;
      }).join('');
    }

    /* While NOTHING is measured, the list of all tests is 265 px of rows
       "not yet measured" (measured 27.08 at 375x812), i.e. the same
       fact already stated in one line in the summary above. We hide both
       the list and the "All test details" toggle: the empty state must
       suggest the next step, not enumerate what is missing. */
    const _anyRaw = NS.fitnessTestDefs.some(t => raw[t.id] != null);
    const details = document.getElementById('fitness-tests-details');
    if (details) details.hidden = !_anyRaw;

    const list = document.getElementById('fitness-tests-list');
    if (list && !_anyRaw) list.innerHTML = '';
    if (list && _anyRaw) {
      list.innerHTML = NS.fitnessTestDefs.map(t => {
        const v = raw[t.id];
        const band = bands[t.id];
        return `<div style="padding:10px 0;border-bottom:1px solid var(--line)">
          <div style="display:flex;justify-content:space-between;align-items:baseline">
            <span style="font-size:14px;font-weight:600">${t.name}</span>
            <span class="mono" style="font-size:16px">${v != null ? v + ' ' + t.unit : '—'}</span>
          </div>
          <div style="font-size:12px;color:var(--dim2);margin-top:2px">${v != null ? band : 'not measured yet'}</div>
        </div>`;
      }).join('');
    }
    card.hidden = false;

    const form = document.getElementById('fitness-edit-form');
    const toggleBtn = document.getElementById('btn-fitness-toggle-edit');
    if (form && toggleBtn && !form.dataset.built) {
      form.dataset.built = '1';
      form.innerHTML = NS.fitnessTestDefs.map(t => `
        <div style="margin-bottom:12px">
          <label for="fitness-in-${NS.H(t.id)}" style="font-size:13px;font-weight:600;display:block;margin-bottom:4px">${NS.H(t.name)} <span style="color:var(--dim2);font-weight:400">(${NS.H(t.unit)})</span></label>
          <input type="number" step="any" class="search-input" id="fitness-in-${t.id}" placeholder="${t.target || ''}" style="min-height:44px">
        </div>`).join('') +
        `<p id="fitness-save-status" class="rz-note" role="alert" hidden></p>` +
        `<button class="btn btn--primary" id="btn-fitness-save" style="width:100%;min-height:52px">Save results</button>`;
      toggleBtn.onclick = () => { form.hidden = !form.hidden; };
      NS.fitnessTestDefs.forEach(t => {
        const input = document.getElementById(`fitness-in-${t.id}`);
        input.oninput = () => { NS.fitManualValues[t.id] = input.value; NS.saveFitnessDraft('manual'); NS.syncFitnessControls(); };
      });
      const saveBtn = document.getElementById('btn-fitness-save');
      if (saveBtn) saveBtn.onclick = async () => {
        if (NS.fitManualSaving) return;
        const results = {};
        NS.fitnessTestDefs.forEach(t => {
          const el = document.getElementById(`fitness-in-${t.id}`);
          if (el && el.value !== '') results[t.id] = el.value;
        });
        const status = document.getElementById('fitness-save-status');
        status.hidden = false;
        if (!Object.keys(results).length) { status.textContent = 'Enter at least one result.'; return; }
        NS.fitManualSaving = true;
        const owner = NS.fitnessOwner;
        const revision = NS.saveFitnessDraft('manual');
        saveBtn.disabled = true;
        form.querySelectorAll('input').forEach(el => { el.disabled = true; });
        NS.syncFitnessControls();
        status.textContent = 'Saving results…';
        try {
          renderFitness(await NS.saveFitnessResults(results, owner));
          NS.clearFitnessDraft('manual', owner, revision);
          NS.fitManualValues = {};
          if (!NS.fitRunResume && !NS.fitRunActive) document.getElementById('fitness-draft-notice').hidden = true;
          form.hidden = true;
          status.hidden = true;
        } catch (error) { status.textContent = NS.fitnessSaveError(error); }
        finally {
          NS.fitManualSaving = false;
          saveBtn.disabled = false;
          form.querySelectorAll('input').forEach(el => { el.disabled = false; });
          NS.syncFitnessControls();
        }
      };
    }
    NS.restoreFitnessDrafts();

    const runBtn = document.getElementById('btn-fitness-start-run');
    if (runBtn && !runBtn.dataset.bound) {
      runBtn.dataset.bound = '1';
      runBtn.onclick = NS.startFitnessRun;
    }
    NS.syncFitnessControls();
  }

  Object.assign(NS, {
     renderWeekSummary, renderWeeklyTrend, SKILL_ERR_UK, loadFitnessAndSkills, renderFitness,
  });
})();
