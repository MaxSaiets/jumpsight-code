/* Guest session, account screen, student sheet and comment drafts. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* The log opens ITS OWN job: an attempt drawn from page memory alone would be empty after a reload. */
  /* ── PASSWORDLESS ACCOUNT, TEAM, COMMENTS ─────────────────── */
  NS.activeJobIdShown = null;
  NS.ME = null;
  NS.meRequestEpoch = 0;
  NS.readyMeEpoch = 0, NS.readyMeUid = null;
  /* Drafts live only in the tab's memory: one student's text does not move
     to another analysis and does not survive a reload. */
  const commentDrafts = new Map();
  NS.commentDraftJob = null, NS.commentDraftOwner = null;
  const LOC = () => 'en-US';
  const _json = (u, body) => fetch(u, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
    .then(async r => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.detail || r.status); return d; });

  async function ensureGuestSession() {
    const response = await fetch('/coach/auth/guest', { method: 'POST' });
    if (response.ok) {
      NS.ME = await response.json();
      return true;
    }
    throw new Error(`guest session HTTP ${response.status}`);
  }

  async function loadMe({ restorePending = false } = {}) {
    const epoch = ++NS.meRequestEpoch;
    let next = null;
    try { next = await _json('/coach/me'); } catch (_) { }
    if (epoch !== NS.meRequestEpoch) return NS.ME;
    NS.ME = next;
    NS.readyMeEpoch = next && next.uid ? epoch : 0;
    NS.readyMeUid = next && next.uid;
    renderAccount();
    if (restorePending && next && next.uid) NS.restorePendingJob(next.uid);
    return NS.ME;
  }

  /* What 'accept' means: the state before the press, not after it */
  const H = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function coachRequestText(p) {
    const who = p.name || p.code;
    return `Coach ${who} wants to follow your analyses. If you accept, they see your jumps and errors and can set your session focus. You can remove them any time in Profile.`;
  }

  function renderAccount() {
    const uid = NS.ME && NS.ME.uid;
    if (uid && uid !== NS.commentDraftOwner) {
      if (NS.commentDraftOwner !== null) {
        /* Old GETs and events belonged to the previous confirmed UID.
           Null after a network failure, and the same UID, do not get here. */
        ++NS.commentsRequestEpoch;
        ++NS.resultRequestEpoch;
        ++NS.identityGeneration;
        ++NS.uploadRequestEpoch;
        NS.uploadInFlight = false;
        if (NS.LIVE.starting) {
          ++NS.LIVE.startEpoch; NS.LIVE.starting = false;
          // An already active recorder keeps the final blob for the separate delivery contract.
          if (!NS.LIVE.rec) NS.stopStartingStream(NS.LIVE.stream);
        }
        NS.lastUploadFile = null;
        NS.retryJobId = null; NS.retryJobOwner = null;
        NS.pendingOpenEpoch = null;
        NS.stopWatching();
        commentDrafts.clear();
        NS.commentDraftJob = NS.demoShown ? null : NS.activeJobIdShown;
        ++NS.commentsContextEpoch;
        const input = document.getElementById('comment-text');
        if (input) input.value = '';
      }
      NS.commentDraftOwner = uid;
    }
    const codeEl = document.getElementById('acc-code');
    if (!codeEl) return;
    if (!NS.ME) {
      codeEl.textContent = '——————';
      const ttl = document.getElementById('acc-title');
      const sub = document.getElementById('acc-subtitle');
      if (ttl) ttl.textContent = 'Sign in required';
      if (sub) sub.textContent = 'Sign in to open your history and sessions.';
      return;
    }
    codeEl.textContent = NS.ME.code;
    const nm = document.getElementById('acc-name'); if (nm && document.activeElement !== nm) nm.value = NS.ME.name || '';
    /* A guest gets a person silhouette: a '?' in the header reads as 'help', not 'profile'. */
    const USER_ICON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
    const avatarContent = NS.ME.picture
      ? `<img class="rz-avatar__img" src="${NS.ME.picture}" alt="" referrerpolicy="no-referrer">`
      : (NS.ME.name ? NS.ME.name.trim()[0].toUpperCase() : USER_ICON);
    const av = document.getElementById('acc-avatar');
    if (av) av.innerHTML = avatarContent;
    const barAv = document.getElementById('bar-account-avatar');
    if (barAv) barAv.innerHTML = avatarContent;
    const ttl = document.getElementById('acc-title'); if (ttl) ttl.textContent = NS.ME.name || 'Guest';
    const sub = document.getElementById('acc-subtitle');
    /* role is a separate row in the list below; here only how they signed in */
    /* Without a name the header already says 'Guest'; the subtitle covers only where the data lives */
    if (sub) sub.textContent = NS.ME.email || (NS.ME.google ? 'Google' : NS.ME.apple ? 'Apple'
      : (NS.ME.name ? 'guest · this phone only' : 'data on this phone only'));
    const signed = !!(NS.ME.signed_in || NS.ME.google || NS.ME.apple);
    const transferBox = document.getElementById('acc-transfer-box');
    if (transferBox) transferBox.hidden = signed;
    const gw = document.getElementById('g-signin-wrap'); if (gw) gw.hidden = signed;
    const lo = document.getElementById('btn-acc-logout'); if (lo) lo.hidden = !signed;
    const isCoach = NS.ME.role === 'coach';
    /* For a coach this is not a 'convenience' but a risk of losing the LINK WITH
       ALL STUDENTS: a guest without sign-in lives only in this browser. */
    const authWhyEl = document.getElementById('auth-why-note');
    if (authWhyEl) {
      const T = k => (window.TEXT ? window.TEXT.t(k) : '');
      /* data-live: applyLang() (the language switch) must not revert the role-specific
         text to the generic authWhy from the glossary. */
      authWhyEl.textContent = isCoach ? T('authWhyCoach') : T('authWhy');
      authWhyEl.dataset.live = '1';
      authWhyEl.classList.toggle('rz-note--warn', isCoach);
    }
    /* The name field is shown only while there is no name, or the person has tapped
       the pencil; the role is a row in the list with its current value. */
    const nameRow = document.getElementById('acc-name-row');
    const editBtn = document.getElementById('btn-acc-edit-name');
    if (nameRow && editBtn) {
      if (!editBtn.dataset.bound) {
        editBtn.dataset.bound = '1';
        editBtn.onclick = () => {
          const open = nameRow.hidden;
          nameRow.hidden = !open;
          editBtn.setAttribute('aria-expanded', String(open));
          if (open) document.getElementById('acc-name')?.focus();
        };
      }
      const hasName = !!(NS.ME.name && NS.ME.name.trim());
      if (document.activeElement?.id !== 'acc-name') nameRow.hidden = hasName;
      editBtn.hidden = !hasName;
      editBtn.setAttribute('aria-expanded', String(!nameRow.hidden));
    }
    const inv = document.getElementById('btn-acc-invite');
    if (inv) inv.hidden = isCoach;   // a coach adds students by THEIR code
    const roleLine = document.getElementById('acc-role-line');
    if (roleLine) roleLine.textContent = isCoach ? 'Coach' : 'Skater';
    renderAccountStats();
    const rs = document.getElementById('btn-acc-role-skater'), rc = document.getElementById('btn-acc-role-coach');
    if (rs) rs.classList.toggle('is-on', !isCoach);
    if (rc) rc.classList.toggle('is-on', isCoach);
    const sb = document.getElementById('acc-skater-box'), cb = document.getElementById('acc-coach-box');
    if (sb) sb.hidden = isCoach;
    if (cb) cb.hidden = !isCoach;
    /* 'About me': an experience / injury / training-frequency survey that
       sets the LEVEL AND SAFE STEPS of sessions. A coach has no own
       session, so the row is not shown to a coach. */
    const svBox = document.getElementById('acc-survey-box');
    if (svBox) svBox.hidden = isCoach;
    const cl = document.getElementById('acc-coach-line');
    if (cl) cl.textContent = NS.ME.coach
      ? `Your coach: ${NS.ME.coach.name || NS.ME.coach.code}`
      : 'No coach yet — enter their code.';
    const lv = document.getElementById('btn-acc-leave'); if (lv) lv.hidden = !NS.ME.coach;
    const pending = document.getElementById('acc-pending-coach');
    if (pending) {
      const p = NS.ME.pending_coach;
      pending.hidden = !p;
      pending.innerHTML = p ? `${H(coachRequestText(p))} <button class="btn btn--outline btn--sm" id="btn-acc-accept">Accept</button> <button class="btn btn--outline btn--sm" id="btn-acc-reject">Decline</button>` : '';
      pending.dataset.code = p ? p.code : '';
      /* the request is not hidden in the collapsed profile row */
      if (p) { const box = document.getElementById('acc-skater-box'); if (box) box.open = true; }
    }
    const banner = document.getElementById('coach-request-banner');
    if (banner) {
      const p = !isCoach && NS.ME && NS.ME.pending_coach;
      banner.hidden = !p;
      if (p) {
        document.getElementById('coach-request-text').textContent = coachRequestText(p);
        banner.dataset.code = p.code;
      }
    }
    if (isCoach) renderTeam();
    NS.applyCoachTabs();
  }

  /* PROFILE SUMMARY: from the own log, measured values only.
     Analyzed jumps, clean ones (checked and without errors), the highest jump
     and the most frequent jump with a specific name. */
  let accStatsEpoch = 0;
  async function renderAccountStats() {
    const box = document.getElementById('acc-stats');
    if (!box) return;
    const epoch = ++accStatsEpoch;
    if (!NS.ME || NS.ME.role === 'coach') { box.hidden = true; return; }
    let rows = [];
    try { const h = await window.__jsHistory(); rows = h.ok && Array.isArray(h.data) ? h.data : []; } catch (_) { rows = []; }
    if (epoch !== accStatsEpoch) return;
    const measured = rows.filter(r => r && r.outcome !== 'not_measured');
    if (!measured.length) { box.hidden = true; box.innerHTML = ''; return; }
    /* 'no findings' rather than 'clean' (the engine never checks two signs; see historyNoFindings) */
    const clean = measured.filter(NS.historyNoFindings).length;
    const heights = measured.map(r => Number(r.height_m)).filter(v => Number.isFinite(v) && v > 0);
    const best = heights.length ? Math.round(Math.max(...heights) * 100) : null;
    const counts = {};
    measured.forEach(r => {
      if (!r.jump || r.jump === 'None' || r.name_uncertain === true || r.name_uncertain === 'True') return;
      if ((typeof r.name_display === 'string' && r.name_display.includes('/'))
          || [true, 'true', 'True'].includes(r.name_is_family)) return;   // a pair is not 'lutz' (jobs.jump_is_resolved)
      counts[r.jump] = (counts[r.jump] || 0) + 1;
    });
    const top = Object.entries(counts).sort((x, y) => y[1] - x[1])[0];
    const topName = top ? (NS.jumpNameLocal(top[0]) || top[0]) : '';
    const tile = (v, l) => `<div class="rz-me__stat"><div class="rz-me__stat-v mono">${v}</div><div class="rz-me__stat-l">${l}</div></div>`;
    box.innerHTML = tile(measured.length, (measured.length === 1 ? 'jump analysed' : 'jumps analysed'))
      + tile(clean, 'no errors found')
      + (best != null ? tile(`${best}<small> cm</small>`, 'highest') : '')
      + (topName ? `<div class="rz-me__fav">Most often: <b>${String(topName).replace(/</g, '&lt;')}</b> · ${`${top[1]} attempt${top[1] === 1 ? '' : 's'}`}</div>` : '');
    box.hidden = false;
  }

  /* The profile hosts no student list (that is the 'Team' screen, renderTeamScreen). The profile's
     'My team' row is needed only for PAIRING (entering a student's code); the roster itself
     lives in one place, the 'Team' tab.
     Here is a short summary with a link to it. */
  async function renderTeam() {
    const box = document.getElementById('acc-team');
    if (!box) return;
    let team = [], pending = [];
    try { [team, pending] = await Promise.all([_json(`/coach/team?lang=en`), _json('/coach/team/pending')]); } catch (_) { }
    if (!team.length) {
      box.innerHTML = `<p class="sub-dim">${pending.length ? `Awaiting consent: ${H(pending.map(s => s.name || s.code).join(', '))}.` : "No students yet — enter a student's code above."}</p>`;
      return;
    }
    const newN = team.reduce((n, s) => n + (s.new || 0), 0);
    box.innerHTML = `<button class="lib-row" id="acc-team-open">
        <div class="lib-row__main"><div class="lib-row__name">${`${team.length} student${team.length === 1 ? '' : 's'}`}</div>
        <div class="lib-row__sub">Analyses, days without video, focus assignment</div></div>
        ${newN ? `<span class="lib-chip lib-chip--ok">new ${newN}</span>` : ''}<span class="lib-row__arr">›</span></button>`;
    const open = document.getElementById('acc-team-open');
    if (open) open.onclick = () => NS.go('team');
  }

  /* Student log sheet: analyses per video (job), newest first; each row shows the date,
     the attempt count, the names and the main error; a tap opens the analysis. */
  NS.studentSheetOwner = '', NS.studentReturnFocus = null, NS.studentBodyOverflow = '', NS.studentHistoryRequest = 0, NS.studentHistoryRows = [];
  async function loadStudentHistory(student, trigger) {
    const request = ++NS.studentHistoryRequest;
    const rows = document.getElementById('sheet-student-rows');
    rows.textContent = 'Loading history…';
    rows.setAttribute('aria-busy', 'true');
    try {
      const historyRows = await _json(`/coach/team/${encodeURIComponent(student.uid)}/history?lang=en`);
      if (request !== NS.studentHistoryRequest || NS.studentSheetOwner !== student.uid || document.getElementById('sheet-student').hidden) return;
      if (!Array.isArray(historyRows)) throw new Error('invalid history');
      openStudentSheet(student.name || student.code, historyRows, trigger);
    } catch (_) {
      if (request !== NS.studentHistoryRequest || NS.studentSheetOwner !== student.uid || document.getElementById('sheet-student').hidden) return;
      rows.replaceChildren();
      const p = document.createElement('p'); p.className = 'rz-note';
      p.textContent = 'History could not be loaded. Try again.';
      const retry = document.createElement('button'); retry.className = 'btn btn--outline';
      retry.textContent = 'Retry'; retry.onclick = () => loadStudentHistory(student, trigger);
      rows.append(p, retry);
    } finally {
      if (request === NS.studentHistoryRequest && NS.studentSheetOwner === student.uid) rows.setAttribute('aria-busy', 'false');
    }
  }
  const labelledStems = new Set();
  function openStudentSheet(name, hist, trigger = null) {
    NS.studentHistoryRows = hist;
    const sheet = document.getElementById('sheet-student');
    const rows = document.getElementById('sheet-student-rows');
    const ttl = document.getElementById('sheet-student-title');
    if (!sheet || !rows) return;
    const opening = sheet.hidden;
    if (opening) {
      NS.studentReturnFocus = trigger || document.activeElement;
      NS.studentBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    if (ttl) ttl.textContent = name || 'Skater';
    const groups = [];
    const stemGroup = new Map();
    hist.filter(r => r && (r.job || (r.jump && r.jump !== 'None'))).forEach(r => {
      const k = r.job && r.job !== 'None' ? `job:${r.job}` : `row:${r.stem || r.ts}`;
        const g = groups[groups.length - 1];
      if (g && g.key === k) g.rows.push(r); else groups.push({ key: k, job: r.job && r.job !== 'None' ? r.job : null, rows: [r] });
    });
    rows.innerHTML = groups.slice(0, 30).map(g => {
      const first = g.rows[0];
      const date = first.ts ? new Date(parseFloat(first.ts) * 1000).toLocaleDateString(LOC(), { day: 'numeric', month: 'short' }) : '';
      /* the name follows the same rule as the student log (historyJumpName):
         the 'lutz or flip' pair stays a pair. */
      const names = [...new Set(g.rows.map(r => NS.jumpWithCount(r)))];
      /* A low-confidence finding is 'possibly', as in the answer;
         'clean' is not used (the engine does not check two signs); 'no findings'
         has the same meaning as 'no errors found'. */
      const errs = new Map();
      g.rows.forEach(r => (Array.isArray(r.errors) ? r.errors : []).forEach(e => {
        const v = errs.get(e) || { n: 0, sure: 0 };
        v.n++; if (['medium', 'high'].includes(String((r.errors_conf || {})[e] || 'low').toLowerCase())) v.sure++;
        errs.set(e, v);
      }));
      const top = [...errs.entries()].sort((a, b) => (b[1].sure - a[1].sure) || (b[1].n - a[1].n))[0];
      const noFind = g.rows.filter(NS.historyNoFindings).length;
      const topName = top ? (NS.ERR_UA[top[0]] ? NS.ERR_UA[top[0]][0] : top[0]) : '';
      const sub = [top ? (top[1].sure ? `${topName} ×${top[1].n}` : `possibly: ${topName.toLowerCase()}` + ` ×${top[1].n}`) : '',
        noFind ? `no errors found: ${noFind}` : ''].filter(Boolean).join(' · ');
      const reviewed = first.review_status === 'reviewed';
      /* COACH LABEL IN THE ROW. 'Yes' confirms the system's name and count
         (the server marks it source=coach itself); 'No' is the analysis
         that has the full correction form. */
      const labelRows = g.job ? g.rows.filter(r => r.stem && r.jump && r.jump !== 'None') : [];
      /* 'Yes' on all labels of an analysis marks it reviewed at once:
         14 attempts = 14 taps, not 28. Opening a row
         does NOT confirm the review (coach_review_smoke). */
      labelRows.slice(0, 4).forEach(r => stemGroup.set(r.stem, {
        job: g.job, version: first.review_version, reviewed: first.review_status === 'reviewed',
        stems: labelRows.slice(0, 4).map(x => x.stem) }));
      const single = labelRows.length === 1;
      const labelHtml = labelRows.slice(0, 4).map(r => {
        const done = labelledStems.has(r.stem);
        return `<div class="rz-student-label${single ? ' is-single' : ''}">
          <span class="rz-student-label__t">${single ? '' : NS.teamHtml(NS.jumpWithCount(r))}</span>
          ${done ? `<span class="rz-note rz-student-label__ok">label saved</span>`
            : `<span class="rz-student-label__q">Right?</span>
          <button class="btn btn--outline btn--sm" data-label-yes="${NS.teamHtml(r.stem)}">Yes</button>
          <button class="btn btn--outline btn--sm" data-label-no="${NS.teamHtml(g.job)}">No</button>`}
        </div>`;
      }).join('');
      return `<div class="rz-student-review-block"><div class="rz-log-row${g.job ? '' : ' is-static'}"${g.job ? ' role="button" tabindex="0"' : ''} data-job="${NS.teamHtml(g.job || '')}">
        <span class="rz-log-row__ic ${noFind && noFind === g.rows.length ? 'is-done' : (top ? (top[1].sure ? 'is-bad' : 'is-maybe') : '')}">${g.rows.length}</span>
        <div class="rz-log-row__main">
          <div class="rz-log-row__name">${NS.teamHtml(names.slice(0, 2).join(', '))}${names.length > 2 ? ' …' : ''}</div>
          <div class="rz-log-row__sub">${NS.teamHtml([date, sub].filter(Boolean).join(' · '))}</div>
        </div>
        <span class="rz-chev" aria-hidden="true">›</span>
      </div>${labelHtml ? `<div class="rz-student-labels">${labelHtml}</div>` : ''}${g.job && first.review_version ? `<div class="rz-student-review-actions">
        <span class="rz-note">${reviewed ? '✓ reviewed' : 'awaiting review'}</span>
        <button class="btn btn--outline btn--sm" data-review-job="${NS.teamHtml(g.job)}" data-version="${NS.teamHtml(first.review_version)}" data-reviewed="${reviewed}">${reviewed ? 'Mark as pending' : 'Mark as reviewed'}</button>
      </div>` : ''}</div>`;
    }).join('') || `<p class="rz-note">No analyses with jumps yet.</p>`;
    /* SUMMARY ABOVE THE LIST: what repeats, with confidence, and
       'mark all reviewed' in one tap instead of N. */
    const pendingGroups = groups.slice(0, 30).filter(g => g.job && g.rows[0].review_version && g.rows[0].review_status !== 'reviewed');
    const errAll = new Map();
    let withErrs = 0;
    hist.forEach(r => {
      const list = Array.isArray(r.errors) ? r.errors : [];
      if (list.length) withErrs++;
      list.forEach(e => {
        const c = String(((r.errors_conf || {})[e]) || 'low').toLowerCase();
        const v = errAll.get(e) || { n: 0, sure: 0 };
        v.n++; if (c === 'medium' || c === 'high') v.sure++;
        errAll.set(e, v);
      });
    });
    const measuredN = hist.filter(r => r && r.outcome !== 'not_measured' && r.jump && r.jump !== 'None').length;
    const rep0 = [...errAll.entries()].sort((a, b) => b[1].n - a[1].n)[0];
    const repLine = rep0 && rep0[1].n >= 2
      ? `Recurring: <b>${NS.teamHtml((NS.ERR_UA[rep0[0]] || [rep0[0]])[0].toLowerCase())}</b> — in ${rep0[1].n} of ${measuredN} jump${measuredN === 1 ? '' : 's'}${rep0[1].sure === 0 ? '; check those moments in the videos' : rep0[1].sure < rep0[1].n ? ` (certain in ${rep0[1].sure})` : ''}`
      : (measuredN ? `Jumps analysed: ${measuredN}. No recurring error found.` : '');
    void withErrs;
    if (repLine || pendingGroups.length > 1) {
      rows.insertAdjacentHTML('afterbegin', `<div class="rz-student-sum">
        ${repLine ? `<p class="rz-student-sum__t">${repLine}</p>` : ''}
        ${pendingGroups.length > 1 ? `<button class="btn btn--outline btn--sm" id="btn-review-all">${`Mark all ${pendingGroups.length} as reviewed`}</button>` : ''}
      </div>`);
    }
    const close = () => {
      const owner = NS.studentSheetOwner;
      NS.studentHistoryRequest++;
      sheet.hidden = true; sheet.style.display = 'none'; NS.studentSheetOwner = '';
      document.body.style.overflow = NS.studentBodyOverflow;
      const target = NS.studentReturnFocus?.isConnected ? NS.studentReturnFocus :
        [...document.querySelectorAll('.rz-team__row')].find(b => b.dataset.uid === owner);
      (target || document.getElementById('team-search'))?.focus({ preventScroll: true });
    };
    rows.querySelectorAll('[data-job]').forEach(r => {
      const open = () => { const j = r.getAttribute('data-job'); if (!j) return; close(); NS.openJob(j); };
      r.onclick = open;
      r.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
    });
    rows.querySelectorAll('[data-label-yes]').forEach(button => {
      button.onclick = async e => {
        e.stopPropagation();
        if (button.disabled) return;
        button.disabled = true;
        const stem = button.dataset.labelYes;
        try {
          const r = await fetch('/coach/verdict_feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stem, correct: true }) });
          const d = r.ok ? await r.json() : null;
          if (!d || d.ok === false) throw new Error('label');
          labelledStems.add(stem);
          const grp = stemGroup.get(stem);
          if (grp && grp.job && grp.version && !grp.reviewed && grp.stems.every(s => labelledStems.has(s))) {
            const owner = NS.studentSheetOwner;
            try {
              const result = await _json(`/coach/team/${encodeURIComponent(owner)}/review`, { job: grp.job, version: grp.version, reviewed: true });
              const student = NS.teamRows.find(s => s.uid === owner);
              if (student) { student.new = result.new; student.review_pending = result.review_pending; }
              NS.renderTeamCards();
              NS.studentHistoryRows = NS.studentHistoryRows.map(x => x.job === grp.job ? { ...x, review_status: result.status } : x);
            } catch (_) { /* label saved; review stays a manual button */ }
            if (NS.studentSheetOwner !== owner) return;
          }
          openStudentSheet(name, NS.studentHistoryRows, NS.studentReturnFocus);
        } catch (_) {
          NS.notice('Label was not saved. Try again.');
          button.disabled = false;
        }
      };
    });
    rows.querySelectorAll('[data-label-no]').forEach(button => {
      button.onclick = e => { e.stopPropagation(); const j = button.dataset.labelNo; close(); NS.openJob(j); };
    });
    const allBtn = document.getElementById('btn-review-all');
    if (allBtn) allBtn.onclick = async () => {
      allBtn.disabled = true;
      const owner = NS.studentSheetOwner;
      const todo = groups.slice(0, 30).filter(g => g.job && g.rows[0].review_version && g.rows[0].review_status !== 'reviewed');
      let updated = NS.studentHistoryRows, failed = 0, last = null;
      for (const g of todo) {
        try {
          last = await _json(`/coach/team/${encodeURIComponent(owner)}/review`, { job: g.job, version: g.rows[0].review_version, reviewed: true });
          updated = updated.map(r => r.job === g.job ? { ...r, review_status: last.status } : r);
        } catch (_) { failed++; }
        if (NS.studentSheetOwner !== owner) return;
      }
      const student = NS.teamRows.find(s => s.uid === owner);
      if (student && last) { student.new = last.new; student.review_pending = last.review_pending; }
      NS.renderTeamCards();
      if (failed) NS.notice(`Not saved: ${failed}. Reload and retry.`);
      if (NS.studentSheetOwner === owner && !sheet.hidden) openStudentSheet(name, updated, NS.studentReturnFocus);
    };
    rows.querySelectorAll('[data-review-job]').forEach(button => {
      button.onclick = async () => {
        if (button.disabled) return;
        button.disabled = true;
        const owner = NS.studentSheetOwner, job = button.dataset.reviewJob;
        const reviewed = button.dataset.reviewed !== 'true';
        try {
          const result = await _json(`/coach/team/${encodeURIComponent(owner)}/review`, {
            job, version: button.dataset.version, reviewed
          });
          const student = NS.teamRows.find(s => s.uid === owner);
          if (student) { student.new = result.new; student.review_pending = result.review_pending; }
          NS.renderTeamCards();
          if (NS.studentSheetOwner !== owner || sheet.hidden) return;
          const updated = NS.studentHistoryRows.map(r => r.job === job ? { ...r, review_status: result.status } : r);
          openStudentSheet(name, updated, NS.studentReturnFocus);
          [...rows.querySelectorAll('[data-review-job]')].find(b => b.dataset.reviewJob === job)?.focus();
        } catch (error) {
          NS.notice(String(error.message).includes('409')
            ? 'The analysis changed. Reload history before marking it reviewed.'
            : 'Review status was not saved. Try again.');
          if (String(error.message).includes('409') && NS.studentSheetOwner === owner && !sheet.hidden) {
            const student = NS.teamRows.find(s => s.uid === owner);
            if (student) await loadStudentHistory(student, NS.studentReturnFocus);
          }
        } finally { button.disabled = false; }
      };
    });
    const btnClose = document.getElementById('btn-close-student-sheet');
    if (btnClose) btnClose.onclick = close;
    sheet.onclick = e => { if (e.target === sheet) close(); };
    sheet.onkeydown = e => {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      if (e.key === 'Tab') {
        const focusable = [...sheet.querySelectorAll('button, select, input, [tabindex="0"]')]
          .filter(el => !el.disabled && el.getClientRects().length);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    sheet.hidden = false; sheet.style.display = 'flex';
    if (btnClose && opening) btnClose.focus();
  }

  function switchCommentDraft(jobId) {
    if (NS.commentDraftJob === jobId) return;
    const input = document.getElementById('comment-text');
    if (input && NS.commentDraftJob !== null) {
      if (input.value) commentDrafts.set(NS.commentDraftJob, input.value);
      else commentDrafts.delete(NS.commentDraftJob);
    }
    NS.commentDraftJob = jobId;
    if (input) input.value = jobId === null ? '' : (commentDrafts.get(jobId) || '');
  }

  Object.assign(NS, {
     commentDrafts, LOC, _json, ensureGuestSession, loadMe, renderAccount, loadStudentHistory,
     openStudentSheet, switchCommentDraft,
  });
})();
