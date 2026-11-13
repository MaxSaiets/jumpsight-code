/* Shared-link banner, personal record, comments, and Google / email sign-in. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* VIRAL LOOP, the other side: whoever opened someone else's analysis by link
     sees an invitation to analyze THEIR OWN jump. Their own analysis
     (in their own log) has no banner. */
  async function syncSharedBanner() {
    const bn = document.getElementById('ans-shared-banner');
    if (!bn) return;
    const job = NS.lastJobId;
    if (!NS.sharedJobId || job !== NS.sharedJobId || NS.demoShown) { bn.hidden = true; return; }
    let own = false;
    try { const h = await window.__jsHistory(); own = h.ok && Array.isArray(h.data) && h.data.some(r => r && r.job === job); } catch (_) { }
    if (NS.lastJobId !== job) return;
    bn.hidden = own;
  }

  /* PERSONAL RECORD: this attempt's height exceeds the best in the OWN log
     by more than the error of both measurements. The first
     measured jump is not a record; an excess within the error is not one either. */
  async function checkPersonalRecord(a) {
    const box = document.getElementById('ans-record');
    if (!box) return;
    box.hidden = true; a.record = null;
    if (!NS.realResults || NS.demoShown || a.noJump || !a.height || a.height === '—' || typeof a.heightHalfCm !== 'number') return;
    const myJob = NS.lastJobId;
    if (!myJob) return;
    let hist = [];
    try { const h = await window.__jsHistory(); hist = h.ok && Array.isArray(h.data) ? h.data : []; } catch (_) { return; }
    if (!hist.some(r => r && r.job === myJob)) return;   // someone else's analysis is not my record
    const prev = hist.filter(r => r && r.job && r.job !== myJob && Number.isFinite(Number(r.height_m)) && Number(r.height_m) > 0
      && Array.isArray(r.height_band_m) && r.height_band_m.length === 2);
    if (!prev.length) return;
    const best = prev.reduce((m, r) => Number(r.height_m) > Number(m.height_m) ? r : m);
    const bestCm = Number(best.height_m) * 100, bestHalf = (Number(best.height_band_m[1]) - Number(best.height_band_m[0])) * 50;
    const cur = Number(a.height);
    if (NS.activeAttempts[NS.currentAttemptIdx] !== a) return;
    if (!(cur - a.heightHalfCm > bestCm + bestHalf)) return;
    a.record = { kind: 'height', cm: cur, prev: Math.round(bestCm),
                 label: `Personal best height · ${cur} cm` };
    box.innerHTML = `<span>${`Personal best height: ${cur} cm — was ${Math.round(bestCm)} cm, beyond measurement error`}</span>
      <button type="button" class="rz-link rz-link--btn" id="btn-record-share">Share the record →</button>`;
    document.getElementById('btn-record-share').onclick = () => NS.openShareSheet();
    box.hidden = false;
  }

  async function loadComments(jobId) {
    const epoch = ++NS.commentsRequestEpoch;
    const draftJob = NS.demoShown ? null : jobId;
    if (NS.activeJobIdShown !== jobId || NS.commentDraftJob !== draftJob) ++NS.commentsContextEpoch;
    NS.switchCommentDraft(draftJob);
    NS.activeJobIdShown = jobId;
    const card = document.getElementById('card-comments');
    const list = document.getElementById('comments-list');
    const form = document.getElementById('comments-form');
    if (!card || !list) return;
    /* sample analysis is not the user's: comments are closed, the request would only return 404 */
    if (NS.demoShown) { card.hidden = true; return; }
    list.textContent = 'Loading comments…';
    card.hidden = false;
    card.setAttribute('aria-busy', 'true');
    if (form) form.hidden = true;
    let rows = [];
    let failed = false;
    try { rows = await NS._json(`/coach/comments/${encodeURIComponent(jobId)}`); } catch (_) { failed = true; }
    if (epoch !== NS.commentsRequestEpoch || NS.activeJobIdShown !== jobId) return;
    if (!NS.ME) await NS.loadMe();
    if (epoch !== NS.commentsRequestEpoch || NS.activeJobIdShown !== jobId) return;
    const isCoach = NS.ME && NS.ME.role === 'coach';
    const escapeText = value => String(value ?? '').replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
    list.innerHTML = rows.map(r => `<div style="padding:8px 0;border-bottom:1px solid var(--line)">
      <div style="font-size:15px">${escapeText(r.text)}</div>
      <div class="sub-dim" style="font-size:12px;margin-top:2px">${escapeText(r.name || (r.role === 'coach' ? 'coach' : 'skater'))} · ${new Date(r.ts * 1000).toLocaleDateString(NS.LOC())}</div></div>`).join('')
      || (isCoach ? '' : `<p class="sub-dim" style="margin:0">No coach comments yet.</p>`);
    if (failed) list.textContent = 'Could not load comments. Open the analysis again.';
    card.setAttribute('aria-busy', 'false');
    if (form) form.hidden = !isCoach;
    const eb = document.getElementById('comments-eyebrow');
    if (eb) eb.textContent = isCoach ? 'COMMENT FOR THE SKATER' : 'FROM THE COACH';
    /* student without a coach and without comments: the card is not shown */
    card.hidden = !failed && !isCoach && !rows.length && !(NS.ME && NS.ME.coach);
    /* For a student, a failure in an optional block gives nothing:
       'Could not load comments' appeared on every guest analysis.
       A coach who writes a comment does see the failure. */
    if (failed && !isCoach) card.hidden = true;
    /* sample analysis is not the user's: comments are closed for it, and 'could not load'
       there would read as a failure, not as an access limit */
    if (NS.demoShown) card.hidden = true;
  }

  async function loadCoachWord() {
    const card = document.getElementById('card-coach-word');
    if (!card) return;
    let c = null;
    try { c = (await NS._json('/coach/coach_comment')).comment; } catch (_) { }
    card.hidden = !c;
    if (!c) return;
    document.getElementById('coach-word-text').textContent = c.text;
    document.getElementById('coach-word-meta').textContent = `${c.name || 'coach'} · ${new Date(c.ts * 1000).toLocaleDateString(NS.LOC())}`;
    card.onclick = () => NS.openJob(c.job);
    card.style.cursor = 'pointer';
  }

  /* Google Identity allows initialization only once per document. The profile and
     the sign-in screen both call initGoogle(), so without this state the SDK
     logged a warning and could replace its callback with the last call. */
  const GSI = { clientId: '', rendered: false, poll: null };

  function showGoogleNote(note, text, href, linkText) {
    if (!note) return;
    note.hidden = false;
    note.replaceChildren(document.createTextNode(text));
    if (href && linkText) {
      const link = document.createElement('a');
      link.href = href;
      link.textContent = linkText;
      link.className = 'quiet-link';
      note.append(' ', link);
    }
  }

  async function initGoogle() {
    const host = document.getElementById('g-signin');
    const note = document.getElementById('g-signin-note');
    if (!host) return;
    let cid = '', aid = '';
    try { const cfg = await NS._json('/coach/auth/config'); cid = cfg.google_client_id || ''; aid = cfg.apple_client_id || ''; } catch (_) { }
    /* Apple: popup; id_token is verified on the server; Apple gives the name only
       on first sign-in, so we pass it together with the token. */
    const ab = document.getElementById('btn-apple-signin');
    if (ab) {
      ab.hidden = !aid;
      if (aid) ab.onclick = async () => {
        try {
          if (!window.AppleID) throw new Error('apple sdk');
          AppleID.auth.init({ clientId: aid, scope: 'name email', redirectURI: location.origin + '/', usePopup: true });
          const r = await AppleID.auth.signIn();
          const u = r && r.user && r.user.name ? [r.user.name.firstName, r.user.name.lastName].filter(Boolean).join(' ') : '';
          const res = await NS._json('/coach/auth/apple', { id_token: r.authorization.id_token, name: u });
          if (res.switched && res.uid) { location.reload(); return; }
          await NS.loadMe();
          NS.notice('Signed in with Apple.');
        } catch (e) { NS.notice('Apple did not confirm the sign-in — try again.'); }
      };
    }
    if (!cid) {
      /* No provider, no block. A technical 'not yet connected on this server' on an
         investor demo read as an unfinished product;
         email sign-in works without it. */
      if (!aid) {
        if (note) note.hidden = true;
        document.querySelector('#scr-auth .rz-auth__providers')?.setAttribute('hidden', '');
        document.querySelector('#scr-auth .rz-auth__or')?.setAttribute('hidden', '');
      }
      return;
    }
    document.querySelector('#scr-auth .rz-auth__providers')?.removeAttribute('hidden');
    document.querySelector('#scr-auth .rz-auth__or')?.removeAttribute('hidden');
    /* Google Identity accepts only origins from the 'Authorized
       JavaScript origins' list of the OAuth client, and a private
       IP address (192.168.x.x, 10.x, 172.16-31.x) or http outside localhost CANNOT be added there,
       and Google answers 'Error 400: origin_mismatch' only after the click.
       We do not show the button at such an address; we say directly where sign-in works
       and that the profile carries the code over. */
    const h = location.hostname;
    const privateIp = /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)/.test(h) || /^\d+\.\d+\.\d+\.\d+$/.test(h);
    const localhost = h === 'localhost';
    /* This OAuth client was verified on localhost, but Google requires an exact
       origin: 127.0.0.1 is a different address. We do not render a button that is guaranteed to
       give 403; the link does not lose the sign-in path in the local demo. */
    if (h === '127.0.0.1') {
      host.replaceChildren();
      const local = `${location.protocol}//localhost${location.port ? ':' + location.port : ''}${location.pathname}${location.search}${location.hash}`;
      showGoogleNote(note,
        'Google is configured for localhost in this demo, not 127.0.0.1.',
        local, 'Open localhost');
      return;
    }
    if ((privateIp && !localhost) || (location.protocol !== 'https:' && !localhost)) {
      host.replaceChildren();
      showGoogleNote(note,
        `Google does not allow sign-in from ${h} (origin_mismatch): use a public HTTPS address added to OAuth.`);
      return;
    }
    if (GSI.clientId === cid && GSI.rendered) return;
    if (GSI.clientId && GSI.clientId !== cid) {
      showGoogleNote(note,
        'Google configuration changed. Refresh this page to sign in safely.');
      return;
    }
    GSI.clientId = cid;
    const render = () => {
      if (!window.google || !google.accounts || !google.accounts.id) return false;
      google.accounts.id.initialize({
        client_id: cid,
        /* It is visible at once that sign-in is in progress; after success the
           profile and fresh data show (as after email sign-in), not the same sign-in screen. */
        callback: async (resp) => {
          if (GSI.busy) return;
          GSI.busy = true;
          host.style.pointerEvents = 'none'; host.style.opacity = '0.5';
          NS.notice('Signing in with Google…', 15000);
          try {
            const r = await NS._json('/coach/auth/google', { credential: resp.credential });
            if (r.switched && r.uid) {
              NS.notice('Signed in. Opening your profile…', 15000);
              location.reload(); return;
            }
            await NS.loadMe();
            try { if (window.COACH && window.COACH.refresh) window.COACH.refresh(true); } catch (_) { }
            NS.notice('Signed in with Google.');
            NS.go('account');
          } catch (e) { NS.notice('Google did not confirm the sign-in — try again.'); }
          finally { GSI.busy = false; host.style.pointerEvents = ''; host.style.opacity = ''; }
        },
      });
      /* The button is drawn at startup, while the sign-in screen is hidden (clientWidth = 0):
         the 320 px fallback gave a 340 px iframe and a page
         wider than the 320 px screen (scrollWidth 347). The margin comes from the window width. */
      const gw = host.clientWidth || (document.documentElement.clientWidth - 64);
      google.accounts.id.renderButton(host, { theme: 'outline', size: 'large', width: Math.max(200, Math.min(360, gw)), text: 'continue_with', locale: 'en' });
      GSI.rendered = true;
      return true;
    };
    if (!render() && !GSI.poll) {
      let n = 0;
      GSI.poll = setInterval(() => {
        if (render() || ++n > 40) { clearInterval(GSI.poll); GSI.poll = null; }
      }, 250);
    }
  }

  /* SIGN-IN / REGISTRATION SCREEN. Google and Apple are providers (where the origin allows);
     email and password are always there. Registration turns a GUEST profile into an account:
     the log and sessions are not lost. Signing in on another phone switches the uid to
     the owner's (switched) and
     reloads the page. */
  let AUTH_MODE = 'in';
  function setAuthMode(mode) {
    AUTH_MODE = mode;
    const create = mode === 'up';
    const t = document.getElementById('auth-title'), sub = document.getElementById('auth-sub');
    if (t) t.textContent = create ? 'Create account' : 'Sign in';
    if (sub) sub.textContent = create
      ? 'Your attempts and sessions follow you to any phone.'
      : 'The same journal and sessions — from any phone.';
    const nw = document.getElementById('auth-name-wrap'); if (nw) nw.hidden = !create;
    const hint = document.getElementById('auth-pw-hint'); if (hint) hint.hidden = !create;
    const pw = document.getElementById('auth-password'); if (pw) pw.autocomplete = create ? 'new-password' : 'current-password';
    const sb = document.getElementById('auth-submit'); if (sb) sb.textContent = create ? 'Create account' : 'Sign in';
    const q = document.getElementById('auth-switch-q'); if (q) q.textContent = create ? 'Already have an account?' : 'No account yet?';
    const sw = document.getElementById('auth-switch'); if (sw) sw.textContent = create ? 'Sign in' : 'Create one';
    const err = document.getElementById('auth-err'); if (err) err.hidden = true;
  }
  function authError(msg) {
    const err = document.getElementById('auth-err');
    if (!err) return;
    err.textContent = msg; err.hidden = false;
  }
  function wireAuthScreen() {
    const open = document.getElementById('btn-open-auth');
    if (open) open.onclick = () => { setAuthMode('in'); NS.go('auth'); initGoogle(); };
    const sw = document.getElementById('auth-switch');
    if (sw) sw.onclick = () => setAuthMode(AUTH_MODE === 'in' ? 'up' : 'in');
    const eye = document.getElementById('auth-eye'), pw = document.getElementById('auth-password');
    if (eye && pw) eye.onclick = () => { pw.type = pw.type === 'password' ? 'text' : 'password'; };
    const guest = document.getElementById('auth-guest');
    if (guest) guest.onclick = async () => {
      try {
        const r = await NS._json('/coach/auth/guest', {});
        if (r.uid) { location.reload(); }
      } catch (e) { fail(e); }
    };
    const form = document.getElementById('auth-form');
    if (form) form.onsubmit = async (ev) => {
      ev.preventDefault();
      const email = String((document.getElementById('auth-email') || {}).value || '').trim();
      const password = String((pw || {}).value || '');
      const name = String((document.getElementById('auth-name') || {}).value || '').trim();
      if (!email || !email.includes('@')) return authError('Enter your email.');
      if (password.length < 8) return authError('Password must be at least 8 characters.');
      const btn = document.getElementById('auth-submit');
      if (btn) btn.classList.add('is-busy');
      try {
        const r = await NS._json(AUTH_MODE === 'up' ? '/coach/auth/register' : '/coach/auth/login', { email, password, name });
        if (r && r.uid && r.switched) { location.reload(); return; }
        await NS.loadMe();
        NS.notice(AUTH_MODE === 'up' ? 'Account created.' : 'Signed in.');
        NS.go('account');
      } catch (e) {
        const m = String(e && e.message || '');
        authError(m.includes('HTTPS') ? 'Open the app over HTTPS or localhost to sign in.'
          : m.includes('429') || m.includes('too many attempts')
          ? 'Too many attempts. Wait 10 minutes.'
          : (m.includes('401') || m.includes('wrong')) ? 'Wrong email or password.'
          : m.includes('already') ? 'This email is already registered — sign in.'
          : m.includes('bad email') ? 'That email does not look right.'
          : 'Failed — try again.');
      } finally { if (btn) btn.classList.remove('is-busy'); }
    };
  }

  Object.assign(NS, {
     syncSharedBanner, checkPersonalRecord, loadComments, loadCoachWord, initGoogle, wireAuthScreen,
  });
})();
