/* Week plan and Today screen rendering, readiness survey and goals. */
(function () {
  'use strict';
  const NS = window.JS.coach;
  /* ── WEEKLY PLAN ────────────────────────────────────────────────
     The backend (/coach/plan) builds it with the SAME engine as the day, and honestly
     marks it `provisional` — a forecast assuming "everything goes to plan". Here that
     assumption is visible, not hidden: forecast days are labeled and dimmer.
     An empty state is not shown at all (card hidden). */
  let weekPlan = null;

  async function loadWeekPlan() {
    const card = document.getElementById('card-week-plan');
    if (!card) return;
    try {
      const r = await fetch(`/coach/plan?lang=en&days=7`);
      if (!r.ok) { card.hidden = true; return; }
      const d = await r.json();
      if (!d || d.empty || !(d.days || []).length) { card.hidden = true; return; }
      weekPlan = d;
      renderWeekPlan(d);
      card.hidden = false;
    } catch (_) { card.hidden = true; }
  }

  function renderWeekPlan(d) {
    const rows = document.getElementById('week-plan-rows');
    const meta = document.getElementById('week-plan-meta');
    const note = document.getElementById('week-plan-note');
    if (meta) meta.textContent = `${d.training_days} training day${d.training_days === 1 ? '' : 's'} · ${d.rest_days ?? 0} rest`;
    /* The focus is shared across all days, so it is written ONCE under
       the heading, not repeated in every row. */
    const firstTr = (d.days || []).find(x => x.focus && x.focus !== 'rest');
    const sub = document.getElementById('week-plan-focus');
    if (sub && firstTr) sub.textContent = `Shared focus: ${String(firstTr.focus_text || firstTr.focus).split(' — common cause:')[0]}`;
    if (note) note.textContent = d.note || '';
    if (!rows) return;
    rows.innerHTML = (d.days || []).map((day, i) => {
      const rest = day.focus === 'rest';
      const prov = !!day.provisional;
      const dl = (day.blocks || []).filter(b => b.drill_id);
      const drills = dl.length;
      /* THE ROW SHOWS WHAT DIFFERS. The focus holds for several
         sessions in a row (correct coaching practice), so it is identical in all
         rows; the drills themselves differ, so they are shown, and the focus appears once in the card header. */
      const names = dl.slice(0, 2).map(b => NS.NAME(b.drill_id, b.name) || b.drill_id);
      const more = drills > 2 ? ` +${drills - 2}` : '';
      /* focus_text also carries a "typical cause" — appropriate in the large
         day header, but it makes a mess in a list row. Take only
         the focus name (before the cause separator). */
      const shortFocus = String(day.focus_text || day.focus || '')
        .split(/\s+—\s+common cause:/)[0];
      const label = rest ? 'Rest'
                         : (names.join(', ') + more) || shortFocus;
      const right = rest ? '' : `${day.duration_min || ''} min · ${drills} drill${drills === 1 ? '' : 's'}`;
      return `<div class="session-block-row"${rest ? '' : ` role="button" tabindex="0" data-plan-day="${i}"`}
                   style="${rest ? '' : 'cursor:pointer;'}${prov ? 'opacity:.62' : ''}">
          <span class="session-block-idx">${rest ? '·' : (day.day ?? i + 1)}</span>
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;font-size:15px">${NS.H(label)}</div>
            <div style="font-size:12px;color:var(--dim2)">${right}${
              (prov && !rest) ? `${right ? ' · ' : ''}forecast` : ''}</div>
          </div>
          ${rest ? '' : '<span class="mono" style="color:var(--dim);font-size:18px">›</span>'}
        </div>`;
    }).join('');
    rows.querySelectorAll('[data-plan-day]').forEach(row => {
      const open = () => openPlanDay(Number(row.dataset.planDay));
      row.addEventListener('click', open);
      row.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
      });
    });
  }

  function openPlanDay(i) {
    /* A plan day opens in the same player as today's
       session — but ONLY for viewing drills: starting a future
       day as a workout would be a promise the system cannot keep. */
    const day = weekPlan && (weekPlan.days || [])[i];
    if (!day) return;
    const mapped = (day.blocks || []).filter(b => b.drill_id).map((b, k) => ({
      id: b.drill_id, title: NS.NAME(b.drill_id, b.name) || '',
      category: `DAY ${day.day} · ${k + 1} OF ${(day.blocks || []).filter(x => x.drill_id).length}`,
      videoUrl: null, sets: null, reps: null, rest: b.rest || null, holdSec: null,
      dosageDesc: b.dosage || '', cue: (b.cues && b.cues[0]) || '',
      steps: b.steps || [], mistakes: b.mistakes || [],
      gate: b.success || '', source: b.url || ''
    }));
    if (mapped.length) window.APP.openDrill(mapped[0]);
  }

  /* ── Backend Today API ── */
  function _todayHead(title, desc) {
    const t = document.getElementById('today-focus-title');
    const d = document.getElementById('today-focus-desc');
    if (t && title != null) { t.textContent = title; t.dataset.live = '1'; }
    if (d && desc != null) { d.textContent = desc; d.dataset.live = '1'; }
  }

  /* today's wellbeing: {d: 'YYYY-MM-DD', v: 'fresh'|'ok'|'tired'} */
  function todayFeel() {
    try {
      const raw = JSON.parse(localStorage.getItem('js.feel') || 'null');
      if (raw && raw.d === new Date().toISOString().slice(0, 10)) return raw.v || '';
    } catch (_) { }
    return '';
  }
  function setTodayFeel(v) {
    try { localStorage.setItem('js.feel', JSON.stringify({ d: new Date().toISOString().slice(0, 10), v })); } catch (_) { }
  }
  function paintFeel() {
    const cur = todayFeel() || 'ok';
    document.querySelectorAll('.readiness-b').forEach(b => {
      const v = b.getAttribute('data-rpe') === 'okay' ? 'ok' : b.getAttribute('data-rpe');
      b.classList.toggle('is-on', v === cur);
    });
    const note = document.getElementById('readiness-note');
    if (note) {
      /* the note says what the server did, or honestly that no choice has been made yet */
      const srv = (NS.todayData && Array.isArray(NS.todayData.personalisation))
        ? NS.todayData.personalisation.find(n => /tired|sore/i.test(String(n))) : null;
      note.textContent = srv ? String(srv)
        : (todayFeel() ? 'The session accounts for how you feel today.'
                       : 'Default is “Okay”. Change it and the session adapts.');
      note.dataset.live = '1';
    }
  }

  let todayLoadVersion = 0;
  async function loadToday() {
    // A late response does not replace a newer plan or a session already started.
    const version = ++todayLoadVersion;
    const owner = window.APP?.currentUid?.();
    const lang = 'en', feel = todayFeel(), goal = todayGoal();
    const isCurrent = () => version === todayLoadVersion
      && owner === window.APP?.currentUid?.() && !NS.sessionState.sessionId;
    // A started session keeps its plan; a new one applies after saving.
    if (NS.sessionState.sessionId && NS.todayData && NS.livePlan.length) {
      renderTodayFromApi(NS.todayData);
      return;
    }
    /* While the plan loads, show an honest loading state rather than a dictionary placeholder
       ("the session is built from your analyses"). */
    _todayHead('Preparing your session…',
               'A few seconds: reading your latest analyses.');
    const t0 = document.getElementById('today-focus-title'); if (t0) t0.classList.add('is-loading');
    try {
      const mRes = await fetch('/coach/mascot_list');
      if (mRes.ok) {
        const mascots = await mRes.json();
        if (isCurrent()) NS.mascotAvailable = mascots;
      }
    } catch (e) { /* mascot list optional */ }
    if (!isCurrent()) return;
    try {
      /* WELLBEING GOES IN THE REQUEST. /coach/today accepts feel=
         (fresh | ok | tired) and really changes the difficulty step — while the card
         "Today's wellbeing" only toggled button highlights and wrote
         "volume adjusted". The choice lives one day in localStorage. */
      const res = await fetch(`/coach/today?lang=${lang}${feel ? `&feel=${encodeURIComponent(feel)}` : ''}`);
      if (!isCurrent()) return;
      if (res.ok) {
        let data = await res.json();
        if (!isCurrent()) return;
        /* session without video analysis, built from the chosen goal (same engine);
           the video, once it appears, takes priority, because the goal is not passed,
           until the server says empty */
        if (data && data.empty && goal) {
          try {
            const r2 = await fetch(`/coach/today?lang=${lang}&goal=${encodeURIComponent(goal)}${feel ? `&feel=${encodeURIComponent(feel)}` : ''}`);
            if (!isCurrent()) return;
            if (r2.ok) data = await r2.json();
          } catch (_) { }
        }
        if (!isCurrent()) return;
        NS.todayData = data;
        /* empty:true is NOT a server failure, but "no data yet". */
        if (NS.todayData && NS.todayData.empty) renderEmptyToday(NS.todayData.message);
        else renderTodayFromApi(NS.todayData);
        paintFeel();
      } else {
        renderDefaultToday();
      }
    } catch (e) {
      if (isCurrent()) renderDefaultToday();
    }
    if (isCurrent()) {
      const t1 = document.getElementById('today-focus-title'); if (t1) t1.classList.remove('is-loading');
    }
  }

  let todayRenderVersion = 0;
  function renderTodayFromApi(data) {
    const renderVersion = ++todayRenderVersion;
    const loadVersion = todayLoadVersion, lang = 'en', owner = window.APP?.currentUid?.();
    const focusT = document.getElementById('today-focus-title');
    /* The server joins "name — common cause: explanation" into one
       line (coach/session.py), and the whole line became a 5-line heading.
       The heading is the name only; the explanation goes into the subtitle. */
    let focusHead = data.focus_text || '';
    let focusTail = '';
    for (const sep of [' — common cause: ']) {
      const k = focusHead.indexOf(sep);
      if (k > 0) { focusTail = focusHead.slice(k + sep.length); focusHead = focusHead.slice(0, k); break; }
    }
    if (focusT && focusHead) {
      focusT.textContent = focusHead;
      focusT.dataset.live = '1';        // do not overwrite with the dictionary language
    } else {
      _todayHead("Today's session",
                 'The focus appears after your next video analysis.');
    }

    /* The greeting shows the real focus_text from /coach/today when there is a real
       analysis; otherwise an honest greeting with no invented "analysis". */
    const aiWelcome = document.getElementById('ai-welcome-text');
    if (aiWelcome) {
      aiWelcome.dataset.live = '1';
      /* only the goal name: the "— common cause: …" tail is planner jargon
        ; in the chat greeting it read as a diagnosis */
      aiWelcome.textContent = data.from_goal && data.focus_text
        ? `Session goal — ${focusHead || data.focus_text}. Ask me anything about technique, ISU rules or drills.`
        : 'Ask me anything about technique, ISU rules or drills.';
    }

    const focusDesc = document.getElementById('today-focus-desc');
    if (focusDesc && (data.based_on || focusTail)) {
      /* One thing per line; the basis for personalization
         lives in the expansion below (today-why-details). */
      focusDesc.textContent = focusTail || '';
      focusDesc.dataset.live = '1';
    }

    /* "Why this is for you": where the day's focus came from. The backend
       returns focus_source: persistent (held across most attempts)
       or latest_analysis (an error from a specific analysis, with its date).
       This line makes the link "your video → this plan" visible. */
    const whyEl = document.getElementById('today-focus-why');
    if (whyEl) {
      const fs = data.focus_source;
      /* The line "Why this is for you: 'Step-out' repeats…" stood right under
         the heading "exit without step-out" and above the same text in personalization —
         one fact three times, plus an error code under two different names.
         The basis stays in the expansion below. */
      if (false && fs && fs.error_code) {
        const errIt = (window.APP && window.APP.ERR_UA && window.APP.ERR_UA[fs.error_code]) || null;
        const errName = errIt ? errIt[0] : fs.error_code.replace(/_/g, ' ');
        whyEl.textContent = fs.kind === 'persistent'
          ? `Why this is for you: “${errName}” shows up in most of your attempts`
          : `Why this is for you: “${errName}” — from your video analysis${fs.date ? ` of ${fs.date}` : ''}`;
        whyEl.hidden = false;
      } else {
        whyEl.hidden = true;
      }
    }

    /* Full list of personalization reasons from the backend (level, survey,
       fitness tests, safety without a coach). Collapsed by
       default so as not to flood the plan. */
    const whyDet = document.getElementById('today-why-details');
    const fitnessWarning = document.getElementById('today-fitness-warning');
    if (fitnessWarning) {
      fitnessWarning.hidden = data.fitness_state !== 'unavailable';
      fitnessWarning.textContent = fitnessWarning.hidden ? '' : 'Fitness test results are unavailable — this plan does not use them. Retry loading in fitness tests.';
    }
    const whyList = document.getElementById('today-why-list');
    if (whyDet && whyList) {
      const notes = Array.isArray(data.personalisation) ? data.personalisation.filter(Boolean) : [];
      if (notes.length) {
        whyList.innerHTML = notes.map(n => `<li>${String(n).replace(/</g, '&lt;')}</li>`).join('');
        whyDet.hidden = false;
      } else {
        whyDet.hidden = true;
      }
    }

    /* An honest subtitle for the session card (no static "Adapted
       from video analysis" without an analysis). */
    const sessSub = document.getElementById('today-session-sub');
    if (sessSub) {
      /* The day's focus goes in the session card subtitle, on one line: a separate
         no separate "overlay" under the hero; the focus itself (why
         this session) the person must see, not only "all drills are new". */
      sessSub.textContent = [focusHead ? `focus: ${focusHead}` : '', data.history_note || '']
        .filter(Boolean).join(' · ');
      if (data.from_goal) {
        const paint = (goals = []) => {
          if (renderVersion !== todayRenderVersion || loadVersion !== todayLoadVersion
            || owner !== window.APP?.currentUid?.()) return;
          const g = goals.find(x => x.code === data.from_goal);
          sessSub.textContent = `goal: ${g ? g.label : data.from_goal} · no video`;
          const ch = document.createElement('button');
          ch.type = 'button'; ch.className = 'quiet-link'; ch.style.padding = '0 6px';
          ch.textContent = 'change';
          ch.onclick = () => { setTodayGoal(''); goalLists.delete('en'); loadToday(); };
          /* without " · ": the 44 px touch target wraps "change" onto its own line,
             and the dot hung at the end of the first one */
          sessSub.append(' ', ch);
        };
        paint();
        ensureGoals(lang).then(paint);   /* after reload — the name, not the code */
      }
    }

    const meta = document.getElementById('today-session-meta');
    if (meta) {
      const bCount = (data.blocks && data.blocks.length) || 0;
      meta.textContent = (data.duration_min
        ? `${data.duration_min} min · ` : '')
        + `${bCount} block${bCount===1?'':'s'}`;
    }
    const startBtnEl = document.getElementById('btn-start-session');
    if (startBtnEl) startBtnEl.hidden = false;
    const startLbl = document.getElementById('btn-start-session-label');
    if (startLbl) {
      const n = (data.blocks && data.blocks.length) || 0;
      /* The block count is already in the card header; it is not repeated on the button. */
      startLbl.textContent = 'Start session';
    }
    /* warm-up on the waiting screen — from the live plan, not from a mockup */
    const wwName = document.getElementById('wait-warmup-name');
    const wwDos = document.getElementById('wait-warmup-dosage');
    NS.warmupIndex = (data.blocks || []).findIndex(b => /warmup/.test(b.block || b.phase || '') || /warm/i.test(b.name || ''));
    document.getElementById('wait-warmup-card').hidden = NS.warmupIndex < 0;
    if (wwName && NS.warmupIndex >= 0) {
      const wu = data.blocks[NS.warmupIndex];
      wwName.textContent = NS.NAME(wu.drill_id, wu.name) || 'Warm-up';
      wwName.dataset.live = '1';
      if (wwDos) wwDos.textContent = wu.dosage || wu.detail || '';
    }

    if (data.blocks && data.blocks.length) {
      /* Only what arrived from the backend (drill_id/dosage/steps/cues): no merged
         hardcoded drill, no invented sets, steps or sources. No value → "—", and the video is
         decided by /api/drill_media (own · mascot · related with label · none
         with a reason). */
      const roleUA = { warmup: 'WARM-UP', warmup_specific: 'SPECIFIC WARM-UP', main: 'MAIN',
            volume: 'VOLUME', control: 'CHECK', cooldown: 'COOL-DOWN' };
      const mapped = data.blocks.map((b, i) => ({
        id: b.drill_id || b.id || '',
        title: NS.NAME(b.drill_id, b.name) || '',
        /* On ice or on the floor — without this, "Single turn on both
           legs" after a double read as a step backward on the ice */
        category: `${roleUA[b.block] || 'BLOCK'}${b.where === 'off_ice' ? ' · OFF-ICE' : ''} · ${i + 1} OF ${data.blocks.length}`,
        videoUrl: null,                  /* resolved by drill_media on open */
        sets: null, reps: null, rest: b.rest || null, holdSec: null,
        dosageDesc: b.dosage || '',
        cue: (b.cues && b.cues[0]) || '',
        steps: b.steps || [],
        mistakes: b.mistakes || [],
        gate: b.success || '',
        source: b.url || '',
        where: b.where || ''
      }));
      NS.livePlan = mapped;
      renderTodayBlocks(mapped);
      NS.renderSessionSummary(NS.historyData);
      NS.restoreWorkoutDraft();
    } else {
      renderDefaultToday();
    }
  }

  async function markAllDone() {
    const ids = (NS.livePlan || []).map(b => b.id).filter(Boolean);
    if (!ids.length) return;
    const btn = document.getElementById('btn-mark-done');
    if (btn) btn.disabled = true;
    try {
      const focus = (NS.todayData && (NS.todayData.focus_goal || NS.todayData.focus || '')) || '';
      const day = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const r = await fetch('/coach/today/complete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: ids, focus, note: 'one-tap',
                               session_id: `one-tap-${day}-${focus.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 35)}`,
                               outcomes: Object.fromEntries(ids.map(i => [i, 'done'])) }) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      if (btn) btn.textContent = '✓ Completion saved';
      await NS.refresh(true);
      try { await NS.fillLiveStats(); } catch (_) { }   /* streak updates without a reload */
    } catch (_) {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Not saved · retry';
      }
    }
  }
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('btn-mark-done');
    if (b) b.addEventListener('click', markAllDone);
  });

  function renderTodayBlocks(blocks) {
    try { const b = document.getElementById('btn-mark-done'); if (b) b.hidden = !(blocks && blocks.length); } catch (_) { }
    const container = document.getElementById('today-blocks-list');
    if (!container) return;
    container.innerHTML = blocks.map((b, i) => {
      /* The check appears only for blocks actually completed in the player. */
      const isDone = NS.sessionState.completed.has(b.id);
      const isActive = !isDone && blocks.findIndex(x => !NS.sessionState.completed.has(x.id)) === i;
      return `
        <div class="session-block-row" role="button" tabindex="0" data-block-index="${i}">
          <span class="session-block-idx ${isDone ? 'is-done' : isActive ? 'is-active' : ''}">${isDone ? '✓' : i + 1}</span>
          ${NS.mascotAvailable.includes(b.id)
            ? `<img class="rz-log-row__thumb" src="/coach/kb/poster/${encodeURIComponent(b.id)}.jpg" alt="" loading="lazy" onerror="this.remove()">`
            : ''}
          <div class="rz-log-row__main">
            <div class="rz-log-row__name">${NS.H(b.title)}</div>
            <div class="rz-log-row__sub">${b.where === 'off_ice' ? 'off-ice · ' : ''}${NS.H(b.dosageDesc || '—')}${NS.mascotAvailable.includes(b.id) ? ' · 3D demo' : ''}</div>
          </div>
          <span class="rz-chev">›</span>
        </div>
      `;
    }).join('');
    container.querySelectorAll('[data-block-index]').forEach(row => {
      const open = () => window.APP.openDrillBlock(Number(row.dataset.blockIndex));
      row.addEventListener('click', open);
      row.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
      });
    });

    /* Eight blocks with dosage are expanded on "Today" — this is content that
       repeats what the player shows step by step and makes the first
       screen of the app the longest (measured: 271 words, 2.4 screens
       of scrolling, about 200 of those words are this list). We show the FIRST block
       ("where we start") and collapse the rest behind a line that honestly says
       how many there are. Nothing is hidden entirely — one tap. */
    const PREVIEW = 1;
    const rows = Array.from(container.children);
    if (rows.length > PREVIEW + 1) {
      rows.slice(PREVIEW).forEach(r => { r.style.display = 'none'; });
      const more = document.createElement('div');
      more.className = 'session-block-row rz-more-row';
      more.setAttribute('role', 'button');
      more.tabIndex = 0;
      const n = rows.length - PREVIEW;
      more.textContent = `Show the other ${n} blocks →`;
      more.onclick = (e) => {
        e.stopPropagation();
        rows.slice(PREVIEW).forEach(r => { r.style.display = ''; });
        more.remove();
      };
      more.onkeydown = e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); more.click(); }
      };
      container.appendChild(more);
    }
  }

  function resetCoachWelcome() {
    const welcome = document.getElementById('ai-welcome-text');
    if (welcome) {
      welcome.dataset.live = '1';
      welcome.textContent = 'Ask me anything about technique, ISU rules or drills.';
    }
  }

  function renderEmptyToday(msg) {
    ++todayRenderVersion;
    resetCoachWelcome();
    document.getElementById('today-fitness-warning').hidden = true;
    /* First launch: explain WHAT to do instead of showing an error. */
    _todayHead('Your first analysis is ahead',
               'Record one jump — the session is built from it.');
    const c = document.getElementById('today-blocks-list');
    if (c) c.innerHTML = `<div style="padding:22px 16px;text-align:center">
        <div style="font-size:15px;color:var(--dim2);line-height:1.5">${
          (msg || 'Upload a jump video — the session is built from it').replace(/</g,'&lt;')}</div>
        <button class="btn btn--primary" style="margin-top:14px;min-height:48px"
                onclick="window.APP.go('record')">Record or choose a video</button>
        <div id="today-goal-pick"></div>
      </div>`;
    renderGoalChips(document.getElementById('today-goal-pick'));
    const meta = document.getElementById('today-session-meta');
    if (meta) meta.textContent = '';
    const startBtn = document.getElementById('btn-start-session');
    if (startBtn) startBtn.hidden = true;      // nothing to launch
    const why = document.getElementById('today-focus-why');
    if (why) why.hidden = true;
    const det = document.getElementById('today-why-details');
    if (det) det.hidden = true;
    const sub = document.getElementById('today-session-sub');
    if (sub) sub.textContent = '';
    NS.livePlan = [];
    NS.warmupIndex = -1;
    document.getElementById('wait-warmup-card').hidden = true;
  }

  function renderDefaultToday() {
    ++todayRenderVersion;
    resetCoachWelcome();
    document.getElementById('today-fitness-warning').hidden = true;
    for (const id of ['today-session-sub', 'today-session-meta']) {
      const el = document.getElementById(id); if (el) el.textContent = '';
    }
    for (const id of ['today-focus-why', 'today-why-details']) {
      const el = document.getElementById(id); if (el) el.hidden = true;
    }
    NS.livePlan = []; NS.warmupIndex = -1;
    document.getElementById('wait-warmup-card').hidden = true;
    document.getElementById('btn-start-session').hidden = true;
    /* An honest state with a reason and a retry. */
    _todayHead('The plan did not load',
               navigator.onLine ? 'The server did not respond. Try again below.'
                                : 'No network.');
    const c = document.getElementById('today-blocks-list');
    if (c) c.innerHTML = `<div style="padding:20px;text-align:center;color:var(--dim2);font-size:14px">
        ${"Today's plan did not load"}${
          navigator.onLine ? ' — the server did not respond'
                           : ' — no network'}.<br>
        <button class="btn btn--outline" style="margin-top:10px;min-height:44px" onclick="window.COACH.init()">${
          'Try again'}</button>
      </div>`;
  }

  /* The self-assessment card appears only when there is something to ask about —
     i.e. after the FIRST completed session (see the comment in
     index.html). New users are not asked about a past
     that does not exist. */
  async function syncReadinessVisibility() {
    const card = document.getElementById('card-readiness');
    if (!card) return;
    try {
      const r = await fetch('/coach/sessions');
      const arr = r.ok ? (await r.json()) : [];
      card.hidden = !(Array.isArray(arr) && arr.length > 0);
    } catch (_) { card.hidden = true; }
  }

  /* Term for the "Learn" card — taken from the LAST analysis, not fixed:
     landing errors → "resilience", lutz/flip pair → "edge", otherwise
     neutral undercurve rules without a "from your answer" claim. */
  function renderLearnFeatured(items) {
    const eye = document.getElementById('learn-feat-eyebrow');
    const ttl = document.getElementById('learn-feat-title');
    const dsc = document.getElementById('learn-feat-desc');
    const card = document.getElementById('card-learn-featured');
    if (!eye || !ttl || !dsc || !card) return;
    const last = (items || []).find(a => a && a.jump && a.jump !== 'None');
    let key = 'under', fromAnswer = false;
    if (last) {
      const errs = Array.isArray(last.errors) ? last.errors : [];
      const nm = String(last.jump || '').toLowerCase();
      if (errs.some(e => /step_out|touch_down|fall|hand_down|two_foot|stiff_landing/.test(e))) { key = 'stability'; fromAnswer = true; }
      else if (/lutz|flip/.test(nm)) { key = 'edge'; fromAnswer = true; }
      else if (errs.some(e => /tilted_axis/.test(e))) { key = 'takeoff'; fromAnswer = true; }
    }
    const t = NS.LEARN_TERMS_DATA[key] || NS.LEARN_TERMS_DATA.under;
    const T = k => (window.TEXT ? window.TEXT.t(k) : '');
    eye.textContent = fromAnswer ? T('learnFeaturedEyebrow') : T('learnFeaturedNeutral');
    ttl.textContent = t.title;
    dsc.textContent = t.desc;
    [eye, ttl, dsc].forEach(el => { el.dataset.live = '1'; });
    card.onclick = () => NS.openTermSheet(key);
    card.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); NS.openTermSheet(key); } };
  }

  /* ── SELF-REPORT SURVEY ─────────────────────────────────
     /coach/survey sets the level and the session safety gates. Card in the profile: status (level and
     basis from /coach/skill_goal or the save response), expansion —
     7 questions as chips, "Save" → POST and rebuild the session. */
  let surveyQs = [], surveyAns = {};
  async function loadSurveyStatus() {
    const st = document.getElementById('acc-survey-status');
    const btn = document.getElementById('btn-acc-survey');
    if (!st) return;
    try {
      const r = await fetch(`/coach/survey?lang=en`);
      const d = r.ok ? await r.json() : [];
      surveyQs = Array.isArray(d) ? d : [];
    } catch (_) { surveyQs = []; }
    const done = surveyQs.filter(q => q.answered).length;
    surveyAns = {};
    surveyQs.forEach(q => { if (q.answered) surveyAns[q.id] = q.value; });
    const T = k => (window.TEXT ? window.TEXT.t(k) : '');
    if (!surveyQs.length) { st.textContent = 'the survey is unavailable on this server'; if (btn) btn.hidden = true; return; }
    if (btn) { btn.hidden = false; btn.textContent = done === surveyQs.length ? T('surveyEdit') : T('surveyOpen'); }
    st.textContent = done === surveyQs.length
      ? `Filled in · ${done} of ${surveyQs.length}`
      : (done ? `${done} of ${surveyQs.length} answered` : T('surveyIntro'));
    st.dataset.live = '1';
  }
  function renderSurveyForm() {
    const box = document.getElementById('acc-survey-form');
    if (!box) return;
    const T = k => (window.TEXT ? window.TEXT.t(k) : '');
    box.innerHTML = surveyQs.map(q => `
      <div class="rz-survey__q">
        <div class="rz-survey__t">${String(q.q).replace(/</g, '&lt;')}</div>
        <div class="rz-chips">${(q.options || []).map(o =>
          `<button type="button" class="btn btn--outline btn--sm rz-survey__opt${surveyAns[q.id] === o.value ? ' is-on' : ''}" data-q="${q.id}" data-v="${o.value}">${String(o.label).replace(/</g, '&lt;')}</button>`).join('')}</div>
      </div>`).join('')
      + `<button type="button" class="btn btn--primary" id="btn-acc-survey-save">${T('surveySave')}</button>
         <p class="rz-note" id="acc-survey-note"></p>`;
    box.querySelectorAll('.rz-survey__opt').forEach(b => {
      b.onclick = () => {
        surveyAns[b.dataset.q] = parseInt(b.dataset.v, 10);
        box.querySelectorAll(`.rz-survey__opt[data-q="${b.dataset.q}"]`).forEach(x => x.classList.toggle('is-on', x === b));
        const n = document.getElementById('acc-survey-note'); if (n) n.textContent = '';
      };
    });
    const save = document.getElementById('btn-acc-survey-save');
    if (save) save.onclick = async () => {
      const note = document.getElementById('acc-survey-note');
      const missing = surveyQs.filter(q => surveyAns[q.id] === undefined).length;
      if (missing) { if (note) note.textContent = `${missing} still unanswered.`; return; }
      save.disabled = true;
      try {
        const r = await fetch('/coach/survey', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers: surveyAns, lang: 'en' }) });
        const prof = r.ok ? await r.json() : null;
        if (note) note.textContent = prof && prof.level_name
          ? `Saved. Level: ${prof.level_name} (${prof.basis || ''}).`
          : 'Saved.';
        /* the form lives inside <details id="acc-survey-box"> —
           we close the section itself, not something else inside it */
        const details = document.getElementById('acc-survey-box');
        if (details) setTimeout(() => { details.open = false; }, 900);
        loadSurveyStatus();
        NS.refresh(true);          /* the session depends on the answers */
      } catch (_) { if (note) note.textContent = 'The server did not respond.'; }
      save.disabled = false;
    };
  }

  /* ── GOAL WITHOUT VIDEO ───────────────────────────────────────────────────
     /coach/today?goal= builds the session from the same base without an analysis. The empty
     state promised "choose a goal below", but the button led to the working-jump picker,
     which gives no session. The goal lives one day in localStorage. */
  function todayGoal() {
    try {
      const raw = JSON.parse(localStorage.getItem('js.goal') || 'null');
      if (raw && raw.d === new Date().toISOString().slice(0, 10)) return raw.v || '';
    } catch (_) { }
    return '';
  }
  function setTodayGoal(v) {
    try {
      if (v) localStorage.setItem('js.goal', JSON.stringify({ d: new Date().toISOString().slice(0, 10), v }));
      else localStorage.removeItem('js.goal');
    } catch (_) { }
  }
  const goalLists = new Map();
  function ensureGoals(lang = 'en') {
    if (!goalLists.has(lang)) {
      const pending = fetch(`/coach/goals?lang=${lang}`).then(async r => {
        if (!r.ok) throw new Error('goals unavailable');
        const data = await r.json();
        if (!Array.isArray(data)) throw new Error('invalid goals');
        return data;
      }).catch(() => {
        if (goalLists.get(lang) === pending) goalLists.delete(lang);
        return [];
      });
      goalLists.set(lang, pending);
    }
    return goalLists.get(lang);
  }
  async function renderGoalChips(host) {
    if (!host) return;
    const renderVersion = todayRenderVersion, loadVersion = todayLoadVersion;
    const lang = 'en', owner = window.APP?.currentUid?.();
    const T = k => (window.TEXT ? window.TEXT.t(k) : '');
    const goalList = await ensureGoals(lang);
    if (!host.isConnected || renderVersion !== todayRenderVersion
      || loadVersion !== todayLoadVersion
      || owner !== window.APP?.currentUid?.()) return;
    if (!goalList.length) { host.innerHTML = ''; return; }
    /* 15 goals = 9 rows of chips on a phone. The first six are visible at once,
       the rest — behind "N more". The list order is the server's. */
    const SHOW = 4;   // 6 chips took half a phone screen
    const chip = g => `<button type="button" class="btn btn--outline btn--sm rz-goal-chip" data-goal="${g.code}">${String(g.label).replace(/^./, c => c.toUpperCase()).replace(/</g, '&lt;')}</button>`;
    const rest = goalList.length - SHOW;
    host.innerHTML = `<div class="rz-note" style="margin:16px 0 8px">${T('goalPickTitle')}</div>
      <div class="rz-chips">${goalList.slice(0, SHOW).map(chip).join('')}${
        rest > 0 ? `<button type="button" class="btn btn--sm rz-goal-chip rz-goal-chip--more" id="btn-goal-more">${`${rest} more →`}</button>` : ''}</div>
      <div class="rz-chips" id="goal-chips-more" hidden>${goalList.slice(SHOW).map(chip).join('')}</div>`;
    const more = host.querySelector('#btn-goal-more');
    if (more) more.onclick = () => { more.hidden = true; const m = host.querySelector('#goal-chips-more'); if (m) { m.hidden = false; m.style.marginTop = '8px'; } };
    host.querySelectorAll('.rz-goal-chip[data-goal]').forEach(b => {
      b.onclick = () => { setTodayGoal(b.dataset.goal); loadToday(); };
    });
  }

  async function loadHistory() {
    try {
      const _h = await window.__jsHistory();
      if (_h.ok) {
        NS.historyData = _h.data;
        renderLearnFeatured(NS.historyData);
        NS.renderHistoryList(NS.historyData);
        NS.renderSessionSummary(NS.historyData);
        NS.renderWeekSummary(NS.historyData);
        NS.renderWeeklyTrend(NS.historyData);
        NS.updateParentDashboard(NS.historyData);
      } else {
        NS.renderDefaultHistory();
      }
    } catch (e) {
      NS.renderDefaultHistory();
    }
  }

  Object.assign(NS, {
     loadWeekPlan, openPlanDay, todayFeel, setTodayFeel, loadToday, renderEmptyToday, syncReadinessVisibility,
     renderLearnFeatured, loadSurveyStatus, renderSurveyForm, loadHistory,
  });
})();
