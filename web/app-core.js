/* Error text tables, shared screen state, screen navigation and click sound. */
(function () {
  'use strict';
  const NS = ((window.JS = window.JS || {}).app = {});
  const ERR_I18N = {
    two_foot_landing: {
      en: ['Two-foot landing', 'Both blades took the ice as the weight came down — the free leg should stay held out.'] },
    touch_down: {
      en: ['Free-foot touch down', 'The free foot brushed the ice after landing — balance lagged behind the rotation.'] },
    fall: { en: ['Fall', 'The centre of mass went down to the ice after contact.'] },
    step_out: { en: ['Step-out', 'The supporting foot changed on the exit — the edge was not held.'] },
    hand_down: { en: ['Hand down', 'The hand touched the ice to steady the landing.'] },
    stiff_landing_knee: { en: ['Stiff landing knee', 'The knee did not absorb the contact.'] },
    tilted_axis: { en: ['Tilted air axis', 'Torso lean in flight makes a vertical landing harder.'] },
  };
  /* ERR_UA is a dynamic view in the current language; the rest of the code
     (and the coach scripts via window.APP.ERR_UA) reads it. */
  const ERR_UA = new Proxy({}, {
    get: (_, k) => { const e = ERR_I18N[k]; return e ? e.en : undefined; },
    has: (_, k) => k in ERR_I18N,
    ownKeys: () => Reflect.ownKeys(ERR_I18N),
    getOwnPropertyDescriptor: () => ({ enumerable: true, configurable: true }),
  });
  /* ONE FINDINGS LANGUAGE FOR ALL LISTS. The answer wrote
     'Possibly: ice contact'; the attempt list, log and coach sheet use the
     same wording and colour rule. Confident
     (medium/high) — shown by name; low — 'possibly: …'; red only for confident. */
  function findings(codes, conf) {
    const tiers = conf || {};
    const list = (Array.isArray(codes) ? codes : []).filter(Boolean);
    const sure = list.filter(c => ['medium', 'high'].includes(String(tiers[c] || 'low').toLowerCase()));
    const maybe = list.filter(c => !sure.includes(c));
    const name = c => (ERR_UA[c] ? ERR_UA[c][0] : String(c).replace(/_/g, ' '));
    const parts = [];
    if (sure.length) parts.push(sure.map(name).join(', '));
    if (maybe.length) parts.push('possibly: ' + maybe.map(name).join(', ').toLowerCase());
    return { sure, maybe, text: parts.join(' · '), cls: sure.length ? 'is-bad' : (maybe.length ? 'is-maybe' : '') };
  }
  const errorReasons = () => ({
    SCALE_DRIFT_DURING_WINDOW: 'the skater changed size in frame too much during the check — the measurement is not trusted',
    SPARSE_ANKLES: 'the ankles are not visible for enough frames to check',
    BLADE_CONTACT_NOT_OBSERVED: 'the leg positions in this view do not confirm both blades contacting the ice',
    SPARSE_WRISTS: 'the wrists are not visible for enough frames to check',
    PROJECTED_2D_ANGLE: 'this angle cannot be measured precisely from a single view',
    /* Without these explanations the 'not determined' line had no reason.
       The wording comes from where the engine sets the code (jumpsight/errors.py). */
    BASELINE_UNAVAILABLE: 'the ice level before landing could not be found — nothing to compare the feet against',
    SUPPORT_FOOT_UNKNOWN: 'the landing foot is not visible — the check needs it',
    WRISTS_NOISY: 'the wrists are too blurry at this resolution',
    LR_SWAP_RISK: 'the left and right leg are easy to mix up in these frames',
    LANDING_OUTSIDE_POSE_WINDOW: 'the landing falls outside the analysed frames',
    LANDING_FRAME_UNAVAILABLE: 'the landing moment was not found',
    TAKEOFF_FRAME_UNAVAILABLE: 'the take-off moment was not found',
    WINDOW_TRUNCATED: 'the video ends too soon after the landing',
    WIDE_BBOX_WITHOUT_HIP_KPTS: 'the silhouette widened but the hips are not visible — a fall is not confirmed',
    SPARSE_POSE_POST_LANDING: 'too few frames after the landing show the pose',
    SPARSE_KNEE_KPTS: 'the knees are not visible for enough frames',
    SPARSE_FLIGHT_POSE: 'too few frames in the air show the pose',
    /* no 'shoot closer' advice: PRODUCT.md item 4 — the system describes its own limit, it does not require filming */
    SKATER_BELOW_MIN_PX: 'the skater is too small in frame for this check',
    FAR_FOOT_OCCLUDED: 'the far foot is hidden behind the body',
    PARTIAL_FAR_FOOT_OCCLUSION: 'the far foot is partly hidden behind the body',
    IMAGE_PLANE_ONLY: 'the tilt is only visible in the image plane, so one view is imprecise',
  });
  const SCREENS = ['today', 'record', 'coach', 'answer', 'progress', 'learn', 'account', 'auth', 'team', 'onboard', 'drill'];
  NS.currentScreen = 'record';
  NS.currentAttemptIdx = 0;
  NS._booting = false;
  NS.activeAttempts = [];
  NS.realResults = false;
  NS.demoShown = false;
  /* declared jump for the next load */
  NS.declaredJump = (() => { try { return sessionStorage.getItem('js.declared') || ''; } catch (_) { return ''; } })();
  NS.declaredTurns = (() => { try { return sessionStorage.getItem('js.declaredTurns') || ''; } catch (_) { return ''; } })();
  NS.activeDrill = null;
  let pollInterval = null;
  NS.eventSource = null, NS.watcherTimer = null, NS.statusRequest = null;
  NS.watcherEpoch = 0, NS.activeJobId = null, NS.retryJobId = null;
  NS.activeJobOwner = null, NS.retryJobOwner = null;
  NS.uploadInFlight = false, NS.lastUploadFile = null, NS.previewUrl = null, NS.previewJobId = null;
  NS.uploadRequestEpoch = 0, NS.identityGeneration = 0;
  NS.resultRequestEpoch = 0, NS.pendingOpenEpoch = null;
  NS.commentsRequestEpoch = 0;
  NS.commentsContextEpoch = 0, NS.commentSubmitPending = false;
  let _slowShown = false;
  NS.videoSpeed = 1.0;
  NS.videoFps = 30;
  /* stem of the last analysis: after a page reload
     activeAttempts is empty after a reload, so 'Open analysis' restores the
     analysis from disk instead of showing an EMPTY 'Upload jump video' screen. */
  const JOB_CONSENT = new Map();
  /* One explicit consent question for training after a label, shown to the owner only when
     consent is not yet given; nothing is pre-checked. Shared by
     the label after display (vcSend) and the reply on the wait screen. */
  function trainConsentBox(job, jc) {
    const box = document.createElement('div');
    box.className = 'rz-check__consent';
    box.innerHTML = `<span>May we use this video and your label to train the system? Without consent the video is deleted after a week.</span>
      <span class="rz-check__consent-btns"><button type="button" class="btn btn--outline btn--sm" data-consent="1">I agree</button>
      <button type="button" class="btn btn--outline btn--sm" data-consent="0">No</button></span>`;
    box.querySelectorAll('[data-consent]').forEach(b => {
      b.onclick = async () => {
        if (b.dataset.consent !== '1') { box.remove(); return; }
        b.disabled = true;
        try {
          const r = await fetch(`/train_consent/${encodeURIComponent(job)}`, { method: 'POST',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ consent: true }) });
          const res = r.ok ? await r.json() : null;
          if (!res || !res.train_consent) throw new Error('consent');
          JOB_CONSENT.set(job, { ...jc, consent: true });
          box.textContent = 'Thank you — this video will help train the system.';
        } catch (_) {
          b.disabled = false;
          NS.notice('Consent was not saved. Try again.');
        }
      };
    });
    return box;
  }
  NS.ANS_WIN = null;
  NS.ANS_PH = null;
  NS.scrubAll = false;
  NS.lastAnswerStem = null;
  NS.lastAnswerJob = null;
  /* Verdict texts are built during analysis and baked into
     activeAttempts; the job id is kept so they can be rebuilt after a language change. */
  NS.lastJobId = null;
  NS.sharedJobId = null;

  const emptyAttempt = () => ({ num: '—',
    name: 'No analyses yet', verdictClass: 'none',
    verdictTitle: 'Upload a jump video',
    verdictSub: 'Record tab → choose a file',
    airTime: '—', height: '—', errors: null, hasDisambig: false });


  /* ── Sound Synthesizer (Web Audio API) ── */
  /* one switch for all app sounds (clicks here, timer signals in coach.js) */
  const soundOn = () => { try { return localStorage.getItem('js.sound') !== '0'; } catch (_) { return true; } };
  function playClickSound(freq = 600, duration = 0.04) {
    if (!navigator.userActivation?.hasBeenActive) return;
    if (!soundOn()) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.start();
      osc.onended = () => ctx.close().catch(() => {});
      osc.stop(ctx.currentTime + duration);
    } catch (e) { }
  }

  /* ── Navigation Engine ── */
  function go(screen, { historyMode = 'push', scrollY = 0 } = {}) {
    if (!SCREENS.includes(screen)) return;
    if (NS.ME?.role === 'coach' && ['record', 'progress', 'today'].includes(screen)) screen = 'team';
    else if (NS.ME && NS.ME.role !== 'coach' && screen === 'team') screen = 'record';
    const changed = NS.currentScreen !== screen;
    if (historyMode !== 'none') {
      const previous = history.state || {};
      history.replaceState({ ...previous, jsScreen: NS.currentScreen, scrollY: window.scrollY }, '');
      const state = { jsScreen: screen, scrollY: 0, jsDepth: previous.jsDepth || 0 };
      if (changed && !NS._booting && historyMode === 'push') {
        state.jsDepth++;
        history.pushState(state, '');
      } else history.replaceState(state, '');
    }
    NS.currentScreen = screen;
    if (screen === 'answer') document.getElementById('answer-ready-banner').hidden = true;
    const main = document.getElementById('main');
    if (main) main.dataset.screen = screen;

    // Toggle Screen Visibility
    SCREENS.forEach(s => {
      const el = document.getElementById('scr-' + s);
      if (el) el.hidden = (s !== screen);
    });
    /* Screen transitions were instant show/hide, so the app 'clicked' instead of moving.
       'clicked' instead of moving. One short (180 ms) entrance
       ONLY for the screen actually navigated to (not for boot() and not
       for returning to the same screen) — not loading choreography,
       but a standard SPA transition. Respects reduced-motion via the CSS itself. */
    if (changed && !NS._booting) {
      const activeEl = document.getElementById('scr-' + screen);
      if (activeEl) {
        activeEl.classList.remove('rz-screen-enter');
        void activeEl.offsetWidth;
        activeEl.classList.add('rz-screen-enter');
      }
    }

    /* Onboarding always opens from the FIRST step (capability overview),
       even if it was already paged through in this session. */
    if (screen === 'onboard') {
      const intro = document.getElementById('onboard-step-intro');
      const pick = document.getElementById('onboard-step-pick');
      if (intro && pick) { intro.hidden = false; pick.hidden = true; }
    }

    /* The avatar iframe must not live off-screen: it stayed
       mounted (display:block) after navigation and kept rendering
       in the background. */
    if (screen !== 'answer') {
      const af = document.getElementById('ans-avatar-frame');
      if (af && af.style.display === 'block') {
        af.src = 'about:blank';
        af.style.display = 'none';
        const v = document.getElementById('ans-video');
        if (v) v.style.display = 'block';
        const b = document.getElementById('btn-toggle-avatar3d');
        if (b) b.style.color = '';
      }
    }

    /* Coach screens read the server on entry, not once at page start,
       otherwise a fresh analysis does not appear until the tab is reloaded
       (see the comment on COACH.refresh). NOT during boot(): that one has just
       called COACH.init(), which already loaded the same data, so every
       today/history/fitness/plan/skill_goal/sessions request would fire twice. */
    if (!NS._booting && screen === 'today') NS.loadCoachWord();
    if (!NS._booting && screen === 'account') NS.loadMe();
    if (screen === 'team') NS.renderTeamScreen();
    if (!NS._booting && (screen === 'today' || screen === 'progress') && window.COACH && window.COACH.refresh) {
      window.COACH.refresh();
    }

    document.querySelectorAll('.tabs__s[data-go]').forEach(b => b.classList.toggle('is-on', b.getAttribute('data-go') === screen));
    // Update Bottom Tabs
    document.querySelectorAll('.tabs__b').forEach(b => {
      const tab = b.getAttribute('data-tab');
      if (tab === screen) {
        b.classList.add('is-on');
        b.setAttribute('aria-current', 'page');
      } else {
        b.classList.remove('is-on');
        b.removeAttribute('aria-current');
      }
    });

    // Update Header Bar
    const titleEl = document.getElementById('bar-title');
    const subEl = document.getElementById('bar-sub');
    const backBtn = document.getElementById('btn-back');

    /* The subtitle must say WHAT is on this screen; it is the main navigation hint.
       'Support and chat' promised support that is not here:
       the session lives in 'Today', and here are questions and the timer. */
    const TITLES = {
      today: { t: 'Training', s: 'What to do today' },
      record: { t: 'Analyse', s: 'Jump video' },
      coach: { t: 'Ask', s: 'Technique and rules' },
      answer: { t: 'Answer', s: 'Attempt analysis' },
      progress: { t: 'Progress', s: 'Journal and measurements' },
      learn: { t: 'Learn', s: 'Terms and rules' },
      account: { t: 'Profile', s: 'Settings' },
      auth: { t: 'Account', s: 'Sign in or create' },
      team: { t: 'Coach', s: 'Your team' },
      onboard: { t: 'Working jump', s: 'Training focus' },
      drill: { t: 'Drill', s: 'How to do it' }
    };

    if (TITLES[screen]) {
      if (titleEl) titleEl.textContent = TITLES[screen].t;
      if (subEl) subEl.textContent = TITLES[screen].s;
    }

    if (backBtn) {
      backBtn.hidden = ['today', 'record', 'progress', 'team'].includes(screen);
    }

    window.scrollTo({ top: scrollY, behavior: 'instant' });
    if (changed && !NS._booting) {
      titleEl?.setAttribute('tabindex', '-1');
      titleEl?.focus({ preventScroll: true });
    }
    if (screen !== 'answer') document.getElementById('ans-video')?.pause();
    if (screen !== 'record') document.getElementById('wait-live-video')?.pause();
    else {
      /* return to the wait screen: the preview plays again */
      const wv = document.getElementById('wait-live-video');
      const ww = document.getElementById('rec-waiting');
      if (wv && ww && !ww.hidden && wv.getAttribute('src') && wv.paused) wv.play()?.catch?.(() => { });
    }
  }

  function goBack() {
    if (history.state?.jsDepth > 0) history.back();
    else go('record', { historyMode: 'replace' });
  }
  window.addEventListener('popstate', e => {
    if (SCREENS.includes(e.state?.jsScreen)) {
      go(e.state.jsScreen, { historyMode: 'none', scrollY: e.state.scrollY || 0 });
    }
  });

  Object.assign(NS, {
     ERR_UA, findings, errorReasons, JOB_CONSENT, trainConsentBox, emptyAttempt, soundOn, playClickSound, go,
     goBack,
  });
})();
