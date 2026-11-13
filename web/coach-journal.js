/* Journal: session summary, parent dashboard, history list and quick mode. */
(function () {
  'use strict';
  const NS = window.JS.coach;
  /* Fewer than three attempts — we do not show a share. This is not caution "just
     in case", but measured: in the evidence the same
     number jumped 100% -> 20% between the first and fifth attempt
     (two runs of /coach/progress on the same clips), and our own
     error at n=5 was ±17.9 pp. A share with that error is not a
     measurement. The same number as skills.MIN_ATTEMPTS on the server. */
  const MIN_ATTEMPTS_FOR_PCT = 3;

  function sessionSummaryErrorName(code) {
    /* ERR_UA — shown in the current language (app.js), so English also gets the name, not the code */
    const known = window.APP && window.APP.ERR_UA && window.APP.ERR_UA[code];
    return known ? known[0] : String(code || '').replace(/_/g, ' ');
  }

  /* A single upload/live job is the only reliable boundary of an attempt series in the journal.
     Do not group by "last hour" or "per day": that would create a session
     the user never started. Old records without a job give one attempt each. */
  function renderSessionSummary(items) {
    const card = document.getElementById('session-summary');
    const body = document.getElementById('session-summary-body');
    const button = document.getElementById('btn-session-next');
    const eyebrow = document.getElementById('session-summary-eyebrow');
    if (!card || !body || !button) return;
    const rows = (Array.isArray(items) ? items : []).filter(Boolean);
    const latestMeasured = rows.find(row => row.outcome !== 'not_measured' && row.jump && row.jump !== 'None');
    if (!latestMeasured) { card.hidden = true; return; }
    const series = latestMeasured.job
      ? rows.filter(row => row.job === latestMeasured.job)
      : [latestMeasured];
    const measured = series.filter(row => row.outcome !== 'not_measured' && row.jump && row.jump !== 'None');
    const degraded = series.filter(row => row.outcome === 'not_measured').length;
    /* "Best" — an attempt with no findings among the checked features
       (fully "clean" never happens: two features from one angle cannot be
       checked, and the line "Best attempt not determined" always stood). */
    const noFindings = row => (window.APP && window.APP.historyNoFindings)
      ? window.APP.historyNoFindings(row)
      : !(Array.isArray(row.errors) && row.errors.length) && Number(row.checks_run) > 0;
    const best = measured.find(row => (row.clean === true || row.clean === 'True') && Number(row.checks_run) > 0)
      || measured.find(noFindings) || null;
    const errors = new Map();
    measured.forEach(row => (Array.isArray(row.errors) ? row.errors : []).forEach(code => {
      if (!code) return;
      const v = errors.get(code) || { n: 0, sure: 0 };
      v.n++;
      if (['medium', 'high'].includes(String((row.errors_conf || {})[code] || 'low').toLowerCase())) v.sure++;
      errors.set(code, v);
    }));
    const mainEntry = [...errors.entries()].sort((a, b) => (b[1].sure - a[1].sure) || (b[1].n - a[1].n))[0] || null;
    const mainError = mainEntry ? [mainEntry[0], mainEntry[1].n, mainEntry[1].sure] : null;
    const countText = `${measured.length} measured attempt${measured.length === 1 ? '' : 's'}`;
    const degradedText = degraded ? ` · ${degraded} without enough data — excluded from the conclusion` : '';
    let bestHtml = '';
    if (best) {
      /* name from name_uncertain — not a name (the same rule as in the journal
         and on the answer screen); the score in words stays, it is not from the family */
      const _unc = best.name_uncertain === true || best.name_uncertain === 'True';
      const _cnt = best.count_named && best.count_named !== 'None'
        ? ` · ${best.count_estimated ? '≈ ' : ''}${best.count_named}` : '';
      /* "Double Lutz", as on the answer and in the journal */
      const _cw = best.count_named && best.count_named !== 'None' ? best.count_named : '';
      const name = _unc ? 'name not resolved' + _cnt
        : (_cw ? `${best.count_estimated ? '≈ ' : ''}${_cw[0].toUpperCase()}${_cw.slice(1)} ${NS.histName(best)}` : NS.histName(best));
      const rev = best.rev_usable !== false && Number.isFinite(Number(best.revolutions))
        ? ` · ${Number(best.revolutions).toFixed(2)} rev` : '';
      bestHtml = `<p class="rz-session-summary__line rz-session-summary__best"><strong>Best: ${String(name).replace(/</g, '&lt;')}</strong>${rev} · no errors found</p>`;
    }
    /* Advice carries confidence, as on the answer: a confident finding is "main",
       a low one is "check the video: maybe…". Without findings we invent no advice.
       No "shoot a few more attempts from the same angle":
       that would be a filming requirement (PRODUCT.md, hard constraint #4). */
    const m = measured.length;
    const advice = mainError
      ? (mainError[2]
        ? `Main thing next time: “${sessionSummaryErrorName(mainError[0])}” — in ${mainError[1]} of ${m} attempt${m === 1 ? '' : 's'}.`
        : `Check the video: possibly “${sessionSummaryErrorName(mainError[0])}” — in ${mainError[1]} of ${m} attempt${m === 1 ? '' : 's'}.`)
      : '';
    if (eyebrow) eyebrow.textContent = 'Latest analysis summary';
    body.innerHTML = `<p class="rz-session-summary__line${degraded ? ' rz-session-summary__degraded' : ''}">${countText}${degradedText}</p>${bestHtml}${advice ? `<p class="rz-session-summary__line"><strong>${advice}</strong></p>` : ''}`;
    const drill = NS.livePlan.find(item => item && item.title) || null;
    /* The button leads to the session and names its first block — from the server plan,
       not invented (checked by coach_summary_smoke). */
    button.textContent = drill
      ? `To the session · ${drill.title} →`
      : 'Analyse one more attempt →';
    button.onclick = () => drill ? window.APP.go('today') : window.APP.go('record');
    card.hidden = false;
  }

  function updateParentDashboard(items) {
    const dashboard = document.getElementById('parent-dashboard');
    if (!items || !items.length) {
      if (dashboard) dashboard.hidden = true;
      return;
    }
    if (dashboard) dashboard.hidden = false;
    const cleanEl = document.getElementById('parent-clean-rate');
    const cleanUnit = cleanEl && cleanEl.nextElementSibling;
    /* THE SHARE OF CLEAN ATTEMPTS COMES FROM THE SERVER TOGETHER WITH ITS OWN ERROR.
       the share is shown with the ±pp that the server
       returns in the clean_pct_se field. An aggregate must not be presented more precisely
       than the data under it. */
    /* the "by goal" card */
    fetch(`/coach/progress_goals?lang=en`).then(r => r.ok ? r.json() : null).then(pg => {
      const card = document.getElementById('progress-goals');
      const body = document.getElementById('progress-goals-body');
      if (!card || !body || !pg || !pg.goals || !pg.goals.length) return;
      /* without a single session there is nothing to say about "did the drills help" */
      if (!pg.goals.some(g => (g.sessions || 0) > 0)) { card.hidden = true; return; }
      const TREND = { better: ['↓ less often', 'var(--clean)'], worse: ['↑ more often', 'var(--short)'],
                      same: ['no change', 'var(--dim2)'], 'n/a': ['too few analyses', 'var(--dim2)'] };
      body.innerHTML = pg.goals.slice(0, 8).map(g => {
        let t = TREND[g.trend] || TREND['n/a'];
        /* the trend is computed only between two weeks separated by
           a session — the reason "n/a" comes from the server and is named here */
        if (g.trend === 'n/a' && g.trend_reason === 'no_session_between') t = ['no session on this goal between analyses', 'var(--dim2)'];
        else if (g.trend === 'n/a' && g.trend_reason === 'mixed_engines') t = ['different analysis methods', 'var(--dim2)'];
        else if (g.trend === 'n/a') t = [`too few goal assessments in ${g.window_days || 7} d`, 'var(--dim2)'];
        const rate = (g.err_rate_recent == null || g.trend === 'n/a') ? '' : ` · ${Math.round(g.err_rate_recent * 100)}%${g.err_rate_earlier == null ? '' : ` (was ${Math.round(g.err_rate_earlier * 100)}%)`}`;
        return `<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)">
          <div><div style="font-weight:600">${(g.title || g.goal).replace(/</g, '&lt;')}</div>
            <div style="font-size:12px;color:var(--dim2)">${`sessions: ${g.sessions}`}${rate}</div></div>
          <div style="font-size:12px;color:${t[1]};white-space:normal;align-self:center">${t[0]}</div></div>`;
      }).join('');
      card.hidden = false;
    }).catch(() => { });
    fetch('/coach/progress').then(r => r.ok ? r.json() : null).then(pr => {
      if (!cleanEl) return;
      const assessed = pr && Number.isFinite(pr.clean_assessed_total) ? pr.clean_assessed_total : ((pr && pr.total) || 0);
      if (!pr || !Number.isFinite(pr.clean_pct) || assessed < MIN_ATTEMPTS_FOR_PCT) {
        cleanEl.textContent = 'too few';
        cleanEl.style.fontSize = '18px';
        if (cleanUnit) cleanUnit.style.display = 'none';
        const box0 = cleanEl.closest('.metric-box');
        const sub0 = box0 && box0.querySelector('.metric-box__note');
        if (sub0) sub0.textContent = `${assessed} of ${MIN_ATTEMPTS_FOR_PCT} execution assessments needed`;
        return;
      }
      cleanEl.textContent = pr.clean_pct;
      cleanEl.style.fontSize = '';
      if (cleanUnit) cleanUnit.style.display = '';
      const box = cleanEl.closest('.metric-box');
      let note = box && box.querySelector('.metric-box__note');
      if (box && !note) {
        note = document.createElement('div');
        note.className = 'metric-box__note';
        note.style.cssText = 'font-size:11px;color:var(--dim2);margin-top:2px';
        box.appendChild(note);
      }
      if (note) note.textContent = (`±${pr.clean_pct_se} pp over ${assessed} assessed attempts`
          + (pr.not_measured ? `; ${pr.not_measured} not measured` : ''));
    }).catch(() => { });

    /* No "weekly volume" in hours: the system does not record session
       duration, so an hours figure would be invented. It is a real
       count of sessions over 7 days from /coach/sessions (ts of each
       completed session), not a time estimate we do not measure. */
    const volEl = document.getElementById('parent-vol-hours');
    if (volEl) {
      fetch('/coach/sessions').then(r => r.ok ? r.json() : []).then(sessions => {
        const weekAgo = Date.now() / 1000 - 7 * 86400;
        const n = (sessions || []).filter(s => (s.ts || 0) >= weekAgo).length;
        volEl.textContent = n;
      }).catch(() => { volEl.textContent = '—'; });
    }
  }

  function renderHistoryList(items) {
    /* RECORDS: filled from the journal heights (height_m is written by both
       the card path and jumpsight). */
    const recEl = document.getElementById('progress-records');
    const recSub = document.getElementById('progress-records-sub');
    /* An empty record ("—" plus an explanation of why it is missing) is a card
       that takes the first screen of "Progress" and says nothing. Hide the block until
       there is a height measurement; once one appears, it shows itself. */
    const recBox = recEl ? recEl.closest('.rz-stats, .grid-2') : null;
    const hasHeight = (items || []).some(a => isFinite(Number(a.height_m)) && Number(a.height_m) > 0);
    if (recBox) recBox.hidden = !hasHeight;
    /* Export of a report from an empty journal — a button that leads nowhere. */
    const exp = document.getElementById('btn-export-coach-pdf');
    if (exp) exp.parentElement.hidden = !(items && items.length);
    if (recEl && items && items.length) {
      const hs = items.map(a => Number(a.height_m)).filter(h => isFinite(h) && h > 0);
      /* "PERSONAL BESTS · up to 1.57 rotations" must not be assembled from rows
         where the uncertainty band is ±0.96, i.e. from a
         number that is not a measurement. Only attempts that pass
         the usability threshold (rev_usable, jumpsight_bridge._rev_usable) go into records;
         entries without the field are not counted, since they cannot be recomputed. */
      const rv = items.filter(a => a.rev_usable !== false)
                      .map(a => Number(a.revolutions)).filter(r => isFinite(r) && r > 0);
      if (hs.length) {
        /* record row and its ±68% band (if the journal has it) */
        const topRow = items.filter(a => isFinite(Number(a.height_m)) && Number(a.height_m) > 0)
          .reduce((m, a) => (!m || Number(a.height_m) > Number(m.height_m) ? a : m), null);
        const hb = topRow && Array.isArray(topRow.height_band_m) && topRow.height_band_m.length === 2
          ? Math.max(1, Math.round((topRow.height_band_m[1] - topRow.height_band_m[0]) * 50)) : null;
        recEl.textContent = `↑ ${(Math.max(...hs) * 100).toFixed(0)} cm${hb ? ` ±${hb}` : ''}`;
        /* "an aggregate is not presented more precisely than the data under it" applies
           to height too. Rotations are filtered by the rotation-validity threshold; for height the journal entry
           has NO uncertainty band at all — it cannot be invented, but silence about it
           is not allowed either, or "33 cm" reads as a measurement with
           known accuracy. So next to it stands where it came from and what
           is not known about it. */
        const base = `highest jump (${hs.length} measurement${hs.length === 1 ? '' : 's'})`;
        /* No "Rotations up to …" line: it would be a decimal number from
           the smallest jump (larger jumps often have no usable decimal
           measurement) and next to "highest" it would read as "no longer rotates".
           "68% band" is protocol language; the person needs only "± — measurement error". */
        void rv;
        const heightCaveat = hb ? ' · ± is the measurement error'
          : ' · height accuracy not estimated';
        if (recSub) recSub.textContent = base + heightCaveat;
      }
    }
    const container = document.getElementById('log-rows-container');
    if (!container) return;
    if (!items || !items.length) {
      NS.renderDefaultHistory();
      return;
    }
    /* History is written on every attempt, together with fragments without
       a name ("—"). The journal needs jumps; fragments stay in
       the data but not in the list (as in the answer carousel). */
    const named = items.filter(a => a && a.jump && a.jump !== 'None');
    if (named.length) items = named;
    /* JUMP FILTER: a real one, not the text "All jumps".
       Appears when the journal has ≥2 different jumps and ≥6 rows. */
    /* undetermined names do not go into the filter: "axel" must not show rows
       "Name not determined", whatever the raw field says */
    const sure = NS.nameIsSure;
    const jumpsHere = [...new Set(items.filter(sure).map(a => String(a.jump || '').toLowerCase()).filter(Boolean))];
    const fbox = document.getElementById('log-filter');
    if (fbox) {
      const show = jumpsHere.length >= 2 && items.length >= 6;
      fbox.hidden = !show;
      if (show) {
        if (NS.journalFilter && !jumpsHere.includes(NS.journalFilter)) NS.journalFilter = '';
        fbox.innerHTML = [['', 'all'], ...jumpsHere.map(j => [j, (window.APP && window.APP.jumpNameLocal && window.APP.jumpNameLocal(j)) || j])]
          .map(([k, lbl]) => `<button type="button" class="rz-chip${NS.journalFilter === k ? ' is-on' : ''}" data-k="${k}">${lbl}</button>`).join('');
        fbox.querySelectorAll('.rz-chip').forEach(b => { b.onclick = () => { NS.journalFilter = b.dataset.k; renderHistoryList(NS.historyData); }; });
        if (NS.journalFilter) items = items.filter(a => sure(a) && String(a.jump || '').toLowerCase() === NS.journalFilter);
      } else NS.journalFilter = '';
    }
    /* JOURNAL BY SESSIONS. The attempts
       of one video (same job; for older records — file_key) stand
       under one heading with the date, and the row holds what was measured in this
       attempt: name, score, errors. Time on screen runs top to bottom
       within a session, as in the video itself. */
    const keyOf = a => (a.job && a.job !== 'None') ? `job:${a.job}`
      : (a.file_key ? `file:${String(a.file_key).split('#')[0]}` : `row:${a.stem || a.ts}`);
    const groups = [];
    items.forEach(a => {
      const k = keyOf(a);
      const g = groups[groups.length - 1];
      if (g && g.key === k) g.rows.push(a); else groups.push({ key: k, rows: [a] });
    });
    const attNo = a => { const m = String(a.stem || '').match(/att(\d+)/); return m ? parseInt(m[1], 10) : null; };
    const ERR = (window.APP && window.APP.ERR_UA) || {};
    const errName = code => (ERR[code] ? ERR[code][0] : String(code).replace(/_/g, ' '));
    let rowIdx = 0;
    container.innerHTML = groups.map(g => {
      const rows = [...g.rows];
      if (rows.every(a => attNo(a) !== null)) rows.sort((x, y) => attNo(x) - attNo(y));
      const first = g.rows[0];
      /* The year — only when it is not the current one ("15 September 2026" on every
         group is noise). Two videos from the same day are told apart by time. */
      const _d = first.ts ? new Date(parseFloat(first.ts) * 1000) : null;
      const _sameDayGroups = _d ? groups.filter(o => o.rows[0] && o.rows[0].ts
        && new Date(parseFloat(o.rows[0].ts) * 1000).toDateString() === _d.toDateString()).length : 0;
      const date = _d ? (_d.toLocaleDateString(NS.LOC(), _d.getFullYear() === new Date().getFullYear()
          ? { day: 'numeric', month: 'long' } : { day: 'numeric', month: 'long', year: 'numeric' })
        + (_sameDayGroups > 1 ? ` · ${_d.toLocaleTimeString(NS.LOC(), { hour: '2-digit', minute: '2-digit' })}` : '')) : '';
      const n = rows.length;
      const head = n > 1
        ? `<div class="rz-log-group"><span>${date}</span><span>${`${n} measured attempts in one video`}</span></div>`
        : `<div class="rz-log-group"><span>${date}</span></div>`;
      const body = rows.map((a, ri) => {
        rowIdx += 1;
        const rev = a.revolutions != null && a.revolutions !== 'None' ? Number(a.revolutions) : null;
        const isClean = a.clean === 'True' || a.clean === true;
        const errs = Array.isArray(a.errors) ? a.errors
          : (typeof a.errors === 'string' && a.errors && a.errors !== 'None' ? a.errors.split(',').map(x => x.trim()) : []);
        /* a finding with low confidence — "maybe", as on the answer */
        const fnd = (window.APP && window.APP.findings) ? window.APP.findings(errs, a.errors_conf)
          : { sure: errs, maybe: [], text: errs.map(errName).join(', '), cls: errs.length ? 'is-bad' : '' };
        const vClass = isClean ? 'clean' : (fnd.sure.length ? 'bad' : (fnd.maybe.length ? 'maybe' : 'short'));
        const nameTxt = NS.histName(a);
        const countTxt = a.count_named && a.count_named !== 'None'
          ? (a.count_estimated ? '≈ ' : '') + a.count_named
          : '';
        /* rotation count — only when the engine recognized it as a measurement */
        const revTxt = (a.rev_usable !== false && rev !== null)
          ? rev.toFixed(2) + ' rev' : '';
        const status = fnd.text
          || (isClean || Number(a.checks_run) > 0 ? 'no errors found' : 'errors not measured');
        const openAttr = a.job && a.job !== 'None'
          ? ` onclick="window.APP.openJob('${String(a.job).replace(/[^A-Za-z0-9_-]/g, '')}', '${String(a.stem || '').replace(/[^A-Za-z0-9_.-]/g, '')}')"`
          : ` onclick="window.APP.openAttempt('${String(a.jump).replace(/'/g, '')}', '${rev !== null ? rev.toFixed(2) : '—'}', '${vClass}')"`;
        return `
        <div class="rz-log-row session-block-row${rowIdx > 5 ? ' quick-extra' : ''}"${openAttr}>
          <span class="rz-log-row__ic session-block-idx ${vClass === 'clean' ? 'is-done' : (vClass === 'bad' ? 'is-bad' : (vClass === 'maybe' ? 'is-maybe' : ''))}">${n > 1 ? ri + 1 : (isClean ? '✓' : '•')}</span>
          <div class="rz-log-row__main">
            <div class="rz-log-row__name">${NS.logName(nameTxt, countTxt, a)}</div>
            <div class="rz-log-row__sub">${status}</div>
          </div>
          <div class="rz-log-row__num">
            <div class="rz-log-row__rev">${revTxt}</div>
          </div>
        </div>`;
      }).join('');
      return head + body;
    }).join('');
    /* "Brief" makes sense only when there is something to shorten: a journal over 5
       rows or secondary cards under it. */
    const qbtn = document.getElementById('btn-quick-mode');
    if (qbtn) qbtn.hidden = rowIdx <= 5;
    const cnt = document.getElementById('log-count');
    if (cnt) cnt.textContent = `${rowIdx} attempt${rowIdx === 1 ? '' : 's'}`;
  }

  /* "quick" mode — state in localStorage, applied
     by a class on the section; the journal shows only the last 5, in large font. */
  function applyQuickMode() {
    const scr = document.getElementById('scr-progress');
    const btn = document.getElementById('btn-quick-mode');
    let on = false;
    try { on = localStorage.getItem('js.quick') === '1'; } catch (_) { }
    if (scr) scr.classList.toggle('quick', on);
    if (btn) {
      btn.textContent = on ? 'Full view' : 'Quick';
      btn.classList.toggle('is-on', on);
    }
    // secondary cards (goal, skills, fitness tests) — by explicit ids: after
    // the journal lives in a separate column, and the "neighbors after the journal" disappeared
    ['progress-goal', 'progress-skills', 'progress-fitness', 'fitness-runner'].forEach(id => {
      const el = document.getElementById(id); if (el) el.classList.add('quick-hide');
    });
  }
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('btn-quick-mode');
    if (btn) btn.addEventListener('click', () => {
      let on = false;
      try { on = localStorage.getItem('js.quick') === '1'; localStorage.setItem('js.quick', on ? '0' : '1'); } catch (_) { }
      applyQuickMode();
    });
    applyQuickMode();
  });

  Object.assign(NS, {
     MIN_ATTEMPTS_FOR_PCT, renderSessionSummary, updateParentDashboard, renderHistoryList,
  });
})();
