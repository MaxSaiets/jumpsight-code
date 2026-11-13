/* Coach and team screens, goals cache, account wiring and notices. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* ── COACH 'TEAM' SCREEN ───────────────────────────────────────────
     The coach needs signals about each student, not settings: how many
     days they have been silent, what holds, whether something new is there, and one action: assign
     a focus. Data comes from /coach/team; nothing is computed on the client except
     color. For the 'coach' role the third tab becomes 'Team'. */
  const GOALS_CACHE = {};
  async function goalsList(strict = false) {
    const lang = 'en';
    if (GOALS_CACHE[lang]) return GOALS_CACHE[lang];
    try {
      const goals = await NS._json(`/coach/goals?lang=${lang}`);
      if (!Array.isArray(goals) || (strict && !goals.length)) throw new Error('goals unavailable');
      GOALS_CACHE[lang] = goals;
      return goals;
    } catch (error) { if (strict) throw error; return []; }
  }
  /* Coach and skater see DIFFERENT navigation, not the same set with a renamed third button.
     'Analyze' (upload your own video) and 'Progress' (your revolution curve) make no sense
     for an account that does not jump; the coach saw three tabs and had to
     guess which were real. Two button sets live in one markup
     (rz-tabs__btn--skater / --coach)
     and are switched here. */
  function applyCoachTabs() {
    const isCoach = !!(NS.ME && NS.ME.role === 'coach');
    document.querySelectorAll('.rz-tabs__btn--skater, .tabs__s--skater').forEach(b => { b.hidden = isCoach; });
    document.querySelectorAll('.rz-tabs__btn--coach, .tabs__s--coach').forEach(b => { b.hidden = !isCoach; });
    document.getElementById('app-tabs')?.classList.toggle('rz-tabs--2col', isCoach);
    /* active tab: if the current screen belongs to the hidden tab set,
       switch to this role's home screen instead of leaving an empty header */
    const skaterOnly = new Set(['record', 'progress', 'today']);
    const coachOnly = new Set(['team']);
    if (isCoach && skaterOnly.has(NS.currentScreen)) NS.go('team', { historyMode: 'replace' });
    else if (!isCoach && coachOnly.has(NS.currentScreen)) NS.go('record', { historyMode: 'replace' });
  }
  /* The empty 'Team' state shows the coach's OWN code (instead of making them go to Profile for it)
     and the same add-student field as Profile: one logic form in two places
     from which it can be called (the same /team/add request).
     */
  let _teamEmptyWired = false;
  function wireTeamEmpty() {
    const codeEl = document.getElementById('team-empty-code');
    if (codeEl) codeEl.textContent = (NS.ME && NS.ME.code) || '——————';
    if (_teamEmptyWired) return;
    _teamEmptyWired = true;
    const copyBtn = document.getElementById('btn-team-empty-copy');
    if (copyBtn) copyBtn.onclick = async () => {
      try { await navigator.clipboard.writeText((NS.ME && NS.ME.code) || ''); notice('Code copied.'); }
      catch (_) { notice('Could not copy. Share the code shown here.'); }
    };
    const addBtn = document.getElementById('btn-team-empty-add');
    const input = document.getElementById('team-empty-student-code');
    if (addBtn) addBtn.onclick = async () => {
      const code = String((input && input.value) || '').trim();
      if (!code || addBtn.disabled) return;
      addBtn.disabled = true;
      try {
        await NS._json('/coach/team/add', { code });
        if (input) input.value = '';
        notice('Invitation sent. The student must confirm the connection in their profile.');
        renderTeamScreen();
      } catch (e) {
        const m = String(e && e.message || '');
        notice(m.includes('404') || m.includes('not found')
          ? 'No such code — check the characters.'
          : 'Failed — try again.');
      } finally { addBtn.disabled = false; }
    };
  }
  const teamHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  NS.teamRows = [], NS.teamGoals = [], NS.teamFilter = 'all', NS.teamRequest = 0;
  function teamState(text, retry) {
    const state = document.getElementById('team-state');
    state.replaceChildren(); state.hidden = !text;
    if (!text) return;
    const p = document.createElement('p'); p.textContent = text; state.append(p);
    if (retry) {
      const button = document.createElement('button'); button.className = 'btn btn--outline';
      button.textContent = 'Retry'; button.onclick = retry; state.append(button);
    }
  }
  async function renderTeamScreen() {
    const box = document.getElementById('team-list');
    const empty = document.getElementById('team-empty');
    if (!box) return;
    const request = ++NS.teamRequest;
    box.setAttribute('aria-busy', 'true');
    empty.hidden = true;
    teamState('Loading students…');
    wireTeamEmpty();
    const pendingNote = document.getElementById('team-pending');
    pendingNote.hidden = true;
    NS._json('/coach/team/pending').then(pending => {
      if (request !== NS.teamRequest) return;
      pendingNote.textContent = pending.length
        ? `Awaiting confirmation: ${pending.map(s => s.name || s.code).join(', ')}. Student data stays private until consent.`
          /* Without a name, the student sees the request from 'Coach BRDS5C' */
          + (NS.ME && !NS.ME.name ? ' ' + 'Add your name in Profile — otherwise the student sees the request with a code only.' : '')
        : '';
      pendingNote.hidden = !pending.length;
    }).catch(() => {
      if (request !== NS.teamRequest) return;
      pendingNote.textContent = 'Could not check invitations. Refresh your team.';
      pendingNote.hidden = false;
    });
    let team;
    try {
      team = await NS._json(`/coach/team?lang=en`);
      if (!Array.isArray(team)) throw new Error('invalid team');
    } catch (_) {
      if (request !== NS.teamRequest) return;
      box.replaceChildren(); box.setAttribute('aria-busy', 'false');
      document.getElementById('team-tools').hidden = true;
      document.getElementById('team-summary').hidden = true;
      teamState('Could not load your team. Check the connection and retry.', renderTeamScreen);
      return;
    }
    if (request !== NS.teamRequest) return;
    NS.teamRows = team;
    if (empty) empty.hidden = team.length > 0;
    document.getElementById('team-invite').open = !team.length;
    document.getElementById('team-tools').hidden = !team.length;
    const summary = document.getElementById('team-summary'); summary.hidden = !team.length;
    summary.innerHTML = [[team.length, 'Students'],
      [team.filter(s => Number(s.new) > 0).length, 'With new analyses'],
      [team.filter(s => s.coach_focus?.goal).length, 'With focus']]
      .map(([n, label]) => `<div><strong>${n}</strong><span>${label}</span></div>`).join('');
    NS.teamGoals = await goalsList();
    if (request !== NS.teamRequest) return;
    box.setAttribute('aria-busy', 'false');
    document.getElementById('team-search').oninput = renderTeamCards;
    document.querySelectorAll('[data-team-filter]').forEach(b => { b.onclick = () => { NS.teamFilter = b.dataset.teamFilter; renderTeamCards(); }; });
    renderTeamCards();
  }
  function renderTeamCards() {
    const box = document.getElementById('team-list');
    const values = document.querySelectorAll('#team-summary strong');
    if (values.length === 3) {
      values[1].textContent = NS.teamRows.filter(s => Number(s.new) > 0).length;
      values[2].textContent = NS.teamRows.filter(s => s.coach_focus?.goal).length;
    }
    const search = document.getElementById('team-search').value.trim().toLocaleLowerCase();
    const team = NS.teamRows.filter(s => `${s.name || ''} ${s.code || ''}`.toLocaleLowerCase().includes(search)
      && (NS.teamFilter !== 'new' || Number(s.new) > 0) && (NS.teamFilter !== 'focus' || s.coach_focus?.goal));
    document.querySelectorAll('[data-team-filter]').forEach(b => {
      const on = b.dataset.teamFilter === NS.teamFilter;
      b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', String(on));
    });
    document.getElementById('team-result-count').textContent = `Showing ${team.length} of ${NS.teamRows.length}`;
    teamState(team.length || !NS.teamRows.length ? '' : 'No students match this search or filter.');
    const gl = c => teamHtml((NS.teamGoals.find(g => g.code === c) || {}).label || c);
    box.innerHTML = team.map(s => {
      const l = s.last || {};
      const nm = l.jump && l.jump !== 'None' ? NS.historyJumpName(l) : (l.job ? 'name not resolved' : '');
      /* 'name not resolved · name — confidence unknown': a record without a name is not counted as named;
         a name exists only when the jump itself does */
      const named = nm && l.jump && l.jump !== 'None'
        && ![true, 'true', 'True'].includes(l.name_uncertain) && ![true, 'true', 'True'].includes(l.name_is_family);
      const nameTrust = named ? ' · ' + NS.historyConfidenceLabel(l.name_confidence, 'name') : '';
      const cn = l.jump && l.jump !== 'None' && l.count_named && l.count_named !== 'None'
        ? ' · ' + NS.historyConfidenceLabel(l.count_confidence, 'count') : '';
      /* a confident finding comes first; 'possibly' only when there is no confident one */
      const errCode = NS.findings(l.errors, l.errors_conf).sure[0] || (Array.isArray(l.errors) ? l.errors[0] : null);
      const err = errCode ? NS.historyErrorSignalLabel(l, errCode) : NS.historyExecutionLabel(l);
      const d = s.days_since;
      const silent = d == null ? 'No video yet' : d === 0 ? 'Video today' : `Last video: ${d} d ago`;
      const chips = [
        Number(s.new) > 0 ? `<span class="rz-team__chip rz-team__chip--new">new attempts: ${Number(s.new)}</span>` : '',
        ...(s.stuck || []).slice(0, 2).map(g => `<span class="rz-team__chip rz-team__chip--stuck">not improving: ${gl(g)}</span>`),
        s.coach_focus && s.coach_focus.goal ? `<span class="rz-team__chip rz-team__chip--focus">focus: ${gl(s.coach_focus.goal)}</span>` : ''
      ].filter(Boolean).join('');
      return `<button class="rz-team__row" data-uid="${teamHtml(s.uid)}">
        <div class="rz-team__ava" aria-hidden="true">${teamHtml((s.name || s.code || '?').trim()[0]?.toUpperCase() || '?')}</div>
        <div class="rz-team__main">
          <div class="rz-team__name">${teamHtml(s.name || s.code || 'Student')}</div>
          <div class="rz-team__last">${l.job ? teamHtml(`Last attempt: ${NS.jumpWithCount(l, nm)}${nameTrust}${cn}${err ? ' · ' + err : ''}`) : 'No analyses yet'}</div>
          <div class="rz-team__chips">${chips}</div>
          <div class="rz-team__silent">${teamHtml(silent)}</div>
        </div>
        <span class="rz-chev" aria-hidden="true">›</span>
      </button>`;
    }).join('');
    box.querySelectorAll('.rz-team__row').forEach(b => {
      b.onclick = async () => {
        const s = team.find(x => x.uid === b.dataset.uid) || {};
        NS.studentSheetOwner = s.uid;
        document.getElementById('sheet-student-focus').replaceChildren();
        NS.openStudentSheet(s.name || s.code || '', [], b);
        NS.loadStudentHistory(s, b);
        wireStudentFocus(s);
      };
    });
  }
  async function wireStudentFocus(s) {
    const box = document.getElementById('sheet-student-focus');
    if (!box) return;
    let goals;
    try {
      goals = await goalsList(true);
      if (!goals.length) throw new Error('goals unavailable');
    } catch (_) {
      if (NS.studentSheetOwner !== s.uid || document.getElementById('sheet-student').hidden) return;
      box.innerHTML = `<p class="rz-note" role="alert">Could not load goals. Your assigned focus remains unchanged.</p>
        <button id="student-focus-retry" class="btn btn--outline">Retry</button>
        <button id="student-focus-save" class="btn btn--primary" disabled>Assign</button>`;
      document.getElementById('student-focus-retry').onclick = () => wireStudentFocus(s);
      return;
    }
    if (NS.studentSheetOwner !== s.uid || document.getElementById('sheet-student').hidden) return;
    const cur = (s.coach_focus && s.coach_focus.goal) || '';
    const unavailable = cur && !goals.some(g => g.code === cur);
    box.innerHTML = `<label class="rz-label" for="student-focus-sel">Student session focus</label>
      <div class="rz-field row-field">
        <select class="rz-input" id="student-focus-sel">
          <option value="">automatic (from analyses)</option>
          ${unavailable ? `<option value="${teamHtml(cur)}" selected disabled>Previously assigned focus</option>` : ''}
          ${goals.map(g => `<option value="${teamHtml(g.code)}" ${g.code === cur ? 'selected' : ''}>${teamHtml(g.label)}</option>`).join('')}
        </select>
        <button class="btn btn--primary" id="student-focus-save">Assign</button>
      </div>
      <p class="rz-note rz-note--flush">The student sees this in sessions for 14 days; then automatic focus resumes.</p>`;
    document.getElementById('student-focus-save').onclick = async () => {
      const button = document.getElementById('student-focus-save');
      if (button.disabled) return;
      button.disabled = true;
      const goal = document.getElementById('student-focus-sel').value;
      try {
        await NS._json(`/coach/team/${encodeURIComponent(s.uid)}/focus`, { goal: goal || null });
        notice(goal ? 'Focus assigned.' : 'Focus cleared — automatic again.');
        s.coach_focus = goal ? { goal } : null;
        renderTeamCards();
      } catch (e) { notice('Failed — try again.'); }
      finally { button.disabled = false; }
    };
    const save = document.getElementById('student-focus-save');
    save.disabled = Boolean(unavailable);
    document.getElementById('student-focus-sel').onchange = () => { save.disabled = false; };
  }

  function wireAccount() {
    NS.initGoogle();
    const lo = document.getElementById('btn-acc-logout');
    if (lo) lo.onclick = async () => {
      try {
        const r = await NS._json('/coach/auth/logout', {});
        /* Sign-out gives a new guest uid on this phone; the account stays intact */
        if (r && r.uid) { location.reload(); return; }
        NS.ME = await NS._json('/coach/me'); NS.renderAccount();
      } catch (_) { }
    };
    NS.wireAuthScreen();
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
    const val = id => String((document.getElementById(id) || {}).value || '').trim();
    const fail = e => {
      const msg = String(e && e.message);
      notice(msg.includes('too many attempts') || msg.includes('429')
        ? 'Too many attempts. Wait 10 minutes.'
        : msg.includes('this account requires sign-in')
        ? 'This profile has an account. Sign in with email, Google, or Apple.'
        : (msg.includes('404') || msg.includes('not found'))
          ? 'No such code — check the characters.'
          : 'Failed — try again.');
    };
    on('btn-acc-copy', async () => {
      try { await navigator.clipboard.writeText(NS.ME ? NS.ME.code : ''); notice('Code copied.'); } catch (_) { }
    });
    on('btn-acc-transfer', async () => {
      try {
        const r = await NS._json('/coach/auth/transfer', {});
        const out = document.getElementById('acc-transfer-token');
        if (out && r.token) { out.value = r.token; out.hidden = false; await navigator.clipboard.writeText(r.token); }
        notice('Transfer token created and copied. It works once for 10 minutes.');
      } catch (e) { fail(e); }
    });
    on('btn-acc-name-save', async () => { try { NS.ME = await NS._json('/coach/me', { name: val('acc-name') }); NS.renderAccount(); notice('Saved.'); } catch (e) { fail(e); } });
    on('btn-acc-role-skater', async () => { try { NS.ME = await NS._json('/coach/me', { role: 'skater' }); NS.renderAccount(); } catch (e) { fail(e); } });
    on('btn-acc-role-coach', async () => { try { NS.ME = await NS._json('/coach/me', { role: 'coach' }); NS.renderAccount(); } catch (e) { fail(e); } });
    on('btn-acc-join', async () => { try { NS.ME = await NS._json('/coach/coach/join', { code: val('acc-coach-code') }); NS.renderAccount(); notice('Request sent to the coach.'); } catch (e) { fail(e); } });
    on('btn-acc-accept', async () => { try { NS.ME = await NS._json('/coach/link/accept', { code: document.getElementById('acc-pending-coach').dataset.code }); NS.renderAccount(); } catch (e) { fail(e); } });
    const reqAnswer = path => async () => {
      const code = document.getElementById('coach-request-banner').dataset.code;
      try { NS.ME = await NS._json(path, { code }); NS.renderAccount(); notice(path.endsWith('accept') ? 'Coach added.' : 'Request declined.'); } catch (e) { fail(e); }
    };
    on('btn-req-accept', reqAnswer('/coach/link/accept'));
    on('btn-req-reject', reqAnswer('/coach/link/reject'));
    on('btn-acc-reject', async () => { try { NS.ME = await NS._json('/coach/link/reject', { code: document.getElementById('acc-pending-coach').dataset.code }); NS.renderAccount(); } catch (e) { fail(e); } });
    on('btn-acc-leave', async () => { try { NS.ME = await NS._json('/coach/coach/leave', {}); NS.renderAccount(); } catch (e) { fail(e); } });
    on('btn-acc-add-student', async () => { try { NS.ME = await NS._json('/coach/team/add', { code: val('acc-student-code') }); document.getElementById('acc-student-code').value = ''; NS.renderAccount(); notice('Request sent to the student.'); } catch (e) { fail(e); } });
    on('btn-acc-claim', async () => {
      try {
        const r = await NS._json('/coach/claim', { token: val('acc-claim-code') });
        if (r.uid) { location.reload(); }
      } catch (e) { fail(e); }
    });
    on('btn-comment-send', async () => {
      const input = document.getElementById('comment-text');
      const raw = input?.value || '', t = raw.trim();
      if (!t || !NS.activeJobIdShown || NS.commentSubmitPending || NS.demoShown) return;
      const job = NS.activeJobIdShown, context = NS.commentsContextEpoch;
      const button = document.getElementById('btn-comment-send');
      NS.commentSubmitPending = true;
      if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
      try {
        await NS._json('/coach/comment', { job, text: t });
        if (NS.activeJobIdShown === job && NS.commentsContextEpoch === context) {
          if (input.value === raw) { input.value = ''; NS.commentDrafts.delete(job); }
          NS.loadComments(job);
        }
      }
      catch (e) { fail(e); }
      finally {
        NS.commentSubmitPending = false;
        if (button) { button.disabled = false; button.setAttribute('aria-busy', 'false'); }
      }
    });
  }

  /* Unobtrusive message at the bottom of the screen (instead of an alert, which blocks
     the page and looks like a system error). */
  function notice(text, ms = 5000) {
    let el = document.getElementById('js-notice');
    if (!el) {
      el = document.createElement('div');
      el.id = 'js-notice';
      el.setAttribute('role', 'status');
      const noMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      el.style.cssText = 'position:fixed;left:16px;right:16px;bottom:calc(84px + env(safe-area-inset-bottom));'
        + 'z-index:9999;padding:12px 14px;border-radius:12px;background:var(--ink,#222);color:var(--bg,#fff);'
        + 'font-size:14px;line-height:1.35;box-shadow:0 6px 24px rgba(0,0,0,.35);pointer-events:none;opacity:0;'
        + (noMotion ? '' : 'transform:translateY(10px);transition:opacity .2s var(--ease,cubic-bezier(.2,.7,.2,1)),transform .2s var(--ease,cubic-bezier(.2,.7,.2,1))');
      document.body.appendChild(el);
    }
    /* Slide and fade instead of an instant hidden/unhidden: the same motion
       already defined in --ease, only on an element that did not have it. */
    el.textContent = text;
    el.hidden = false;
    clearTimeout(el._t); clearTimeout(el._t2);
    void el.offsetWidth;
    el.style.opacity = '1'; el.style.transform = 'translateY(0)';
    el._t = setTimeout(() => {
      el.style.opacity = '0'; el.style.transform = 'translateY(10px)';
      el._t2 = setTimeout(() => { el.hidden = true; }, 220);
    }, ms);
  }

  Object.assign(NS, {
     applyCoachTabs, teamHtml, renderTeamScreen, renderTeamCards, wireAccount, notice,
  });
})();
