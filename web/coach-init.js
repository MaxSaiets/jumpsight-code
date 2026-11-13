/* Coach screen refresh and init, knowledge-base search, live stats and the window.COACH export. */
(function () {
  'use strict';
  const NS = window.JS.coach;
  /* Coach data is read on page load (init) AND after each successful analysis, so
     "Today" and "Progress" do not stay as they were when the tab was opened
     (empty, reading "Upload video" right after a full answer). */
  let _refreshing = false;
  let _refreshedAt = 0;
  /* Every switch between the Today and Progress tabs would re-pull all 9
     coach requests (today, history, fitness, skill_profile,
     sessions, plan, skill_goal, mascot_list, progress_goals — 100–200 ms each),
     so a refresh without
     force is skipped if the previous one finished less than
     10 s ago; after completing an analysis it is called with force=true. */
  const REFRESH_TTL_MS = 10000;
  async function refresh(force) {
    if (_refreshing) return;
    if (!force && Date.now() - _refreshedAt < REFRESH_TTL_MS) return;
    _refreshing = true;
    try {
      await Promise.all([NS.loadToday(), NS.loadHistory(), NS.loadFitnessAndSkills(),
                          NS.syncReadinessVisibility()]);
      _refreshedAt = Date.now();
    } catch (e) { /* individual loaders draw their own failure state */ }
    _refreshing = false;
  }

  function init() {
    if (NS.fitRunActive) NS.updateFitnessStepLabel();
    _refreshedAt = Date.now();
    NS.loadToday();
    NS.loadHistory();
    NS.loadFitnessAndSkills();
    NS.syncReadinessVisibility();
    NS.renderLearnTerms();
    NS.updateQuickTimerUI();

    // Start Session on Today Screen
    const btnStart = document.getElementById('btn-start-session');
    if (btnStart) btnStart.onclick = () => NS.startSession(null, NS.sessionState.sessionId ? NS.sessionState.blockIdx : 0);

    const btnWaitWarm = document.getElementById('btn-wait-warmup');
    if (btnWaitWarm) btnWaitWarm.onclick = () => { if (NS.warmupIndex >= 0) NS.startSession(null, NS.warmupIndex); };

    // Player Events
    const btnRep = document.getElementById('btn-rep-done');
    if (btnRep) btnRep.onclick = NS.onRepDone;

    const btnSet = document.getElementById('btn-set-done');
    if (btnSet) btnSet.onclick = NS.onSetDone;

    const btnTimed = document.getElementById('btn-timed-start');
    if (btnTimed) btnTimed.onclick = NS.toggleTimedBlock;

    /* "About me" — a row in the grouped profile list that
       expands by itself (details/summary), without a separate button
       "Fill in"; the form is built once, on first expansion. */
    const surveyDetails = document.getElementById('acc-survey-box');
    if (surveyDetails) surveyDetails.ontoggle = () => {
      if (surveyDetails.open) NS.renderSurveyForm();
    };
    NS.loadSurveyStatus();

    const btnTooHard = document.getElementById('btn-too-hard');
    if (btnTooHard) btnTooHard.onclick = () => {
      NS.sessionState.rpe = 'much';
      document.querySelectorAll('[data-post-rpe]').forEach(button => {
        button.classList.toggle('is-on', button.dataset.postRpe === 'much');
      });
      NS.finishWorkout();
    };

    const btnPlus30 = document.getElementById('btn-rest-plus30');
    if (btnPlus30) btnPlus30.onclick = NS.addRest30;

    const btnSkipRest = document.getElementById('btn-skip-rest');
    if (btnSkipRest) btnSkipRest.onclick = NS.skipRest;

    // RPE Selector
    document.querySelectorAll('[data-post-rpe]').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('[data-post-rpe]').forEach(b => {
          b.classList.remove('is-on');
          b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('is-on');
        btn.setAttribute('aria-pressed', 'true');
        NS.sessionState.rpe = btn.getAttribute('data-post-rpe');
        NS.saveWorkoutDraft();
      };
    });

    const btnSaveRpe = document.getElementById('btn-save-session-feedback');
    if (btnSaveRpe) btnSaveRpe.onclick = NS.saveFeedbackAndExit;

    const btnPause = document.getElementById('btn-player-pause');
    if (btnPause) btnPause.onclick = () => {
      NS.saveWorkoutDraft();
      clearInterval(NS.sessionState.timedTimer); NS.sessionState.timedTimer = null;
      clearInterval(NS.sessionState.restTimer); NS.sessionState.restTimer = null;
      clearInterval(NS.sessionState.holdTimer); NS.sessionState.holdTimer = null;
      document.getElementById('scr-player').hidden = true;
      document.getElementById('scr-player').style.display = 'none';
    };

    const btnCloseSheet = document.getElementById('btn-close-term-sheet');
    if (btnCloseSheet) btnCloseSheet.onclick = NS.closeTermSheet;

    // Coach Hub Events
    const btnResumeCoach = document.getElementById('btn-coach-resume-session');
    if (btnResumeCoach) btnResumeCoach.onclick = () => NS.startSession(null, NS.sessionState.blockIdx);

    const btnViewDrill = document.getElementById('btn-coach-view-drill');
    if (btnViewDrill) btnViewDrill.onclick = () => { if (NS.livePlan.length) openDrill(NS.livePlan[NS.sessionState.blockIdx % NS.livePlan.length]); };

    // Quick Timer Events
    const btnTimerStart = document.getElementById('btn-coach-timer-start');
    if (btnTimerStart) btnTimerStart.onclick = NS.toggleQuickTimer;

    const btnTimerReset = document.getElementById('btn-coach-timer-reset');
    if (btnTimerReset) btnTimerReset.onclick = NS.resetQuickTimer;

    document.querySelectorAll('.coach-timer-preset').forEach(b => {
      b.onclick = () => NS.setQuickTimerPreset(parseInt(b.getAttribute('data-sec') || 45));
    });

    // Chat Events
    const btnSend = document.getElementById('btn-coach-chat-send');
    const input = document.getElementById('coach-chat-input');
    if (btnSend && input) {
      btnSend.onclick = () => {
        const q = input.value;
        if (q) {
          NS.askCoach(q);
        }
      };
      input.onkeydown = (e) => {
        if (e.key === 'Enter') {
          const q = input.value;
          if (q) {
            NS.askCoach(q);
          }
        }
      };
    }

    // Prompt Chips
    document.querySelectorAll('.chat-chip').forEach(chip => {
      chip.onclick = () => {
        /* A chip sends its English question (data-ask-en) when present. */
        const q = chip.getAttribute('data-ask-en') || chip.getAttribute('data-ask');
        if (q) NS.askCoach(q);
      };
    });

    // Learn Filters & Search
    document.querySelectorAll('.filter-chip').forEach(chip => {
      chip.onclick = () => {
        document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('is-on'));
        chip.classList.add('is-on');
        NS.currentLearnCat = chip.getAttribute('data-cat') || 'all';
        NS.renderLearnTerms(NS.currentLearnCat, NS.currentLearnSearch);
      };
    });

    const searchInput = document.getElementById('learn-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        NS.currentLearnSearch = e.target.value;
        NS.renderLearnTerms(NS.currentLearnCat, NS.currentLearnSearch);
      };
      /* Enter = a real question to the knowledge base, not just a filter of the local
         dictionary. The answer is two-stage (measured: retrieval ~0.1 s, summary
         ~2 s): first the found excerpts with sources, then a short answer. */
      searchInput.onkeydown = (e) => {
        if (e.key !== 'Enter' || !searchInput.value.trim()) return;
        runKbSearch(searchInput.value.trim());
      };
    }

    /* The card leads
       to the same real search of the knowledge base as Enter in the field —
       not an invented "article view" but a real query. */
    NS.renderLearnFeatured(NS.historyData);
  }

  async function runKbSearch(q) {
    const box = document.getElementById('learn-terms-list');
    if (!box) return;
    box.textContent = 'Searching the knowledge base…';
    let rows = [];
    try {
      const sr = await fetch('/api/ask_sources?lang=en&q=' + encodeURIComponent(q));
      if (sr.ok) {
        const sd = await sr.json();
        rows = (sd.hits || sd.sources || []).slice(0, 4);
      }
    } catch (_) { }
    box.replaceChildren();
    const heading = document.createElement('div');
    heading.className = 'eyebrow';
    heading.textContent = 'FROM THE KNOWLEDGE BASE';
    box.appendChild(heading);
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No matching passages were found.';
      box.appendChild(empty);
    }
    rows.forEach(x => {
      const row = document.createElement('div');
      row.className = 'session-block-row';
      const excerpt = document.createElement('div');
      excerpt.textContent = String(x.text || x.passage || '').slice(0, 160) + '…';
      row.appendChild(excerpt);
      const source = document.createElement('small');
      source.textContent = x.source || x.title || '';
      row.appendChild(source);
      box.appendChild(row);
    });
    const ansBox = document.createElement('div');
    ansBox.id = 'learn-ask-answer';
    ansBox.textContent = 'Putting together a short answer…';
    box.appendChild(ansBox);
    try {
      const ar = await fetch('/coach/ask', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, lang: 'en' }) });
      const ad = ar.ok ? await ar.json() : null;
      ansBox.textContent = ad && ad.answer
        ? ad.answer
        : 'Could not assemble an answer — see the sources above.';
    } catch (_) {
      ansBox.textContent = 'No connection to the knowledge base.';
    }
  }

  /* Rule: no data — the block is EMPTY with a reason, not a mockup number. ── */
  async function fillLiveStats() {
    const dateEl = document.getElementById('today-date');
    if (dateEl) dateEl.textContent = new Date().toLocaleDateString(NS.LOC(),
      { weekday: 'long', day: 'numeric', month: 'long' });
    let hist = [];
    try {
      const _h = await window.__jsHistory();
      if (_h.ok) hist = _h.data;
    } catch (_) { }
    const streak = document.getElementById('today-streak');
    /* We count JUMPS, not rows: a row exists in an excerpt without a jump too, so
       "4 analyses" with three videos and three jumps did not add up anywhere.
       The same number as in the report below ("Jumps in the journal"). */
    const _namedN = hist.filter(h => h && h.jump && h.jump !== 'None').length;
    if (streak && _namedN) {
      streak.hidden = false;
      streak.textContent = `${_namedN} jump${_namedN === 1 ? '' : 's'} in the journal`;
    }
    /* The real streak of sessions and the week summary, not
       just a counter of analyses. */
    try {
      const pg = await fetch(`/coach/progress_goals?lang=en`).then(r => r.ok ? r.json() : null);
      if (pg && streak && (pg.streak_days > 0 || pg.sessions_7d > 0)) {
        streak.hidden = false;
        streak.textContent = (pg.streak_days > 0
          ? `🔥 ${pg.streak_days} day${pg.streak_days === 1 ? '' : 's'} in a row` + ' · ' : '')
          + `${pg.sessions_7d} session${pg.sessions_7d === 1 ? '' : 's'} in 7 days`;
      }
      window.__jsProgressGoals = pg;
    } catch (_) { }
    /* Only attempts with a jump go into the report: fragments without a name produced
       rows "— / —" that say nothing to the coach. */
    const named = hist.filter(h => h && h.jump && h.jump !== 'None');
    const frag = hist.length - named.length;
    const rl = document.getElementById('report-live');
    if (rl && hist.length) {
      const _cleanN = named.filter(h => h.clean === 'True' || h.clean === true).length;
      /* The table sits right under this line — "numbers in the Progress tab"
         sent the person far from the report they had just opened. */
      rl.textContent = (`Jumps in the journal: ${named.length} · without errors: ${_cleanN}`
                           + (frag ? ` · ${frag} fragment${frag === 1 ? '' : 's'} without a jump not shown` : ''));
      rl.dataset.live = '1';   // real data — the language dictionary does not overwrite it
    }
    /* The share of clean attempts is written ONLY by updateParentDashboard: from the server, with
       a threshold of 3 attempts and its error. A second writer here overwrote "too few attempts"
       with a bare percentage and no error. */
    const rb = document.getElementById('report-body');
    if (rb) {
      /* The report holds a table of attempts from the journal (the same fields as on the
         "Progress" screen), and only that is printed. */
      const ERR = (window.APP && window.APP.ERR_UA) || {};
      const rows = named.slice(0, 40).map(a => {
        const d = a.ts ? new Date(parseFloat(a.ts) * 1000).toLocaleDateString(NS.LOC()) : '';
        const nm = (a.name_uncertain === true || a.name_uncertain === 'True')
          ? 'name not resolved'
          : (a.jump && a.jump !== 'None'
              ? NS.histName(a)
              : 'jump not confirmed');
        const cn = a.count_named && a.count_named !== 'None'
          ? (a.count_estimated ? '≈ ' : '') + a.count_named : '';
        const rev = a.rev_usable !== false && a.revolutions != null && a.revolutions !== 'None'
          ? Number(a.revolutions).toFixed(2) : '—';
        const errs = Array.isArray(a.errors) ? a.errors : (typeof a.errors === 'string' && a.errors && a.errors !== 'None' ? a.errors.split(',').map(x => x.trim()) : []);
        const st = (a.clean === true || a.clean === 'True')
          ? 'clean'
          : (errs.length ? errs.map(e => (ERR[e] ? ERR[e][0] : String(e).replace(/_/g, ' '))).join(', ') : '—');
        return `<tr><td>${d}</td><td>${nm}${cn ? ' · ' + cn : ''}</td><td class="mono rz-report-table__num">${rev}</td><td>${st}</td></tr>`;
      }).join('');
      rb.innerHTML = hist.length ? `
        <table class="report-table"><thead><tr>
          <th>Date</th><th>Jump</th><th class="rz-report-table__num">Rev.</th><th>Execution</th>
        </tr></thead><tbody>${rows}</tbody></table>
        <div class="rz-report__foot">“—” in rotations: the count could not be measured reliably on that video — the attempt’s analysis says why.</div>`
        : `<div class="rz-empty">No analyses in the journal yet — the report is empty.</div>`;
    }
    const pat = document.getElementById('report-athlete');
    if (pat) {
      pat.textContent = `Jumps analysed: ${named.length}`;
      pat.dataset.live = '1';
    }
    const rp = document.getElementById('report-period');
    if (rp) rp.textContent = 'Generated: ' + new Date().toLocaleDateString(NS.LOC());
  }
  try { fillLiveStats(); } catch (_) { }

  window.COACH = {
    fillLiveStats,
    openPlanDay: NS.openPlanDay,
    init, refresh, LEARN_TERMS_DATA: NS.LEARN_TERMS_DATA, setTodayFeel: NS.setTodayFeel, todayFeel: NS.todayFeel, loadSurveyStatus: NS.loadSurveyStatus,
    get livePlan() { return NS.livePlan; },
    startSession: NS.startSession, onRepDone: NS.onRepDone, onSetDone: NS.onSetDone,
    openTermSheet: NS.openTermSheet, askCoach: NS.askCoach, parseDosage: NS.parseDosage,
    toggleQuickTimer: NS.toggleQuickTimer, resetQuickTimer: NS.resetQuickTimer
  };

  Object.assign(NS, {
     refresh, fillLiveStats,
  });
})();
