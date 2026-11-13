/* Boot sequence: wires the record, demo and navigation controls. */
(function () {
  'use strict';
  const NS = window.JS.app;
  NS.VC_JUMPS = undefined, NS.vcJump = undefined, NS.vcTurns = undefined, NS.guessJump = undefined, NS.guessTurns = undefined;

  function boot() {
    bootPart0();
    bootPart1();
    bootPart2();
    NS.bootPart3();
    NS.bootPart4();
  }

  function bootPart0() {
    NS.initTheme();
    NS.initVideoSync();
    document.getElementById('btn-upload-video').onclick = () => document.getElementById('file-picker').click();
    document.getElementById('btn-shoot-cam').onclick = () => document.getElementById('file-camera').click();
    /* On a computer, 'Record now' (input capture) opens the same file
       dialog: two buttons for one action. Without a touchscreen one main
       remains: pick a video. */
    try {
      const desktop = window.matchMedia('(hover: hover) and (pointer: fine)').matches && !('ontouchstart' in window);
      if (desktop) {
        const shoot = document.getElementById('btn-shoot-cam');
        const up = document.getElementById('btn-upload-video');
        if (shoot) shoot.hidden = true;
        if (up) {
          up.classList.remove('btn--outline'); up.classList.add('btn--primary'); up.dataset.desktop = '1';
          const lbl = up.querySelector('[data-t="btnUpload"]');
          if (lbl) { lbl.textContent = 'Choose a video'; lbl.dataset.live = '1'; }
        }
        const hint = document.getElementById('record-file-hint');
        if (hint) { hint.textContent = 'MP4 or MOV from a phone or camera · analysis starts right away'; hint.dataset.live = '1'; }
      }
    } catch (_) { }
    const uploadArea = document.querySelector('.record-upload');
    if (uploadArea) {
      uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('is-dragover'); });
      uploadArea.addEventListener('dragleave', e => { if (!uploadArea.contains(e.relatedTarget)) uploadArea.classList.remove('is-dragover'); });
      uploadArea.addEventListener('drop', e => {
        e.preventDefault();
        uploadArea.classList.remove('is-dragover');
        if (e.dataTransfer?.files?.length > 1) {
          NS.notice('Choose one video at a time.');
          return;
        }
        const file = e.dataTransfer?.files?.[0];
        if (file) NS.handleFileUpload(file);
      });
    }
    document.addEventListener('keydown', e => {
      if (e.target.matches('[role="button"]') && (e.key === 'Enter' || e.key === ' ')) {
        if (e.target.id === 'answer-ready-banner') return;
        e.preventDefault(); e.target.click();
      }
    });
    NS.loadLastAnswer();
    /* Parent (once a week): first the audio and the log; the skill profile
       and physical tests in one row, since this is not a weekly action. */
    (() => {
      const sk = document.getElementById('progress-skills');
      const ft = document.getElementById('progress-fitness');
      if (!sk || !ft) return;
      /* via the class, not hidden: coach.js removes hidden when data loads */
      sk.classList.add('is-collapsed'); ft.classList.add('is-collapsed');
      const tg = document.createElement('button');
      tg.className = 'rz-link rz-link--btn rz-prog__more';
      /* coach.js hides the skill profile until there are fewer than 3 attempts per jump,
         otherwise the button promised 'skills' but opened only physical tests. */
      const label = on => {
        const both = !sk.hidden;
        return on ? (both ? 'Hide skills and fitness tests' : 'Hide fitness tests')
                  : (both ? 'Show skills and fitness tests' : 'Show fitness tests');
      };
      tg.textContent = label(false);
      tg.onclick = () => {
        const on = sk.classList.contains('is-collapsed');
        sk.classList.toggle('is-collapsed', !on); ft.classList.toggle('is-collapsed', !on);
        tg.textContent = label(on);
      };
      /* the caption is updated when coach.js decides about skills */
      new MutationObserver(() => { tg.textContent = label(!sk.classList.contains('is-collapsed')); })
        .observe(sk, { attributes: true, attributeFilter: ['hidden'] });
      new MutationObserver(() => { tg.textContent = label(!sk.classList.contains('is-collapsed')); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
      sk.insertAdjacentElement('beforebegin', tg);
    })();
    if (window.TEXT) window.TEXT.apply();
    NS.wireAccount();
    ['btn-shoot-cam', 'btn-upload-video'].forEach(id => {
      document.getElementById(id)?.addEventListener('pointerdown', () => NS.prewarm(), { passive: true });
    });
    /* The live recording buttons also wake the live worker, otherwise the
       first recording after idle was scanned cold (names came later) */
    ['btn-live-rec', 'btn-train-live'].forEach(id => {
      document.getElementById(id)?.addEventListener('pointerdown', () => NS.prewarm(true), { passive: true });
    });
    NS.ensureGuestSession().then(ready => {
      if (!ready) {
        NS.go('auth');
        NS.notice('Your previous profile needs sign-in or transfer from a device with an active session. A new guest is created only with the button below.');
        return;
      }
      if (window.COACH) window.COACH.init();
      NS.loadMe({ restorePending: true }).then(NS.loadCoachWord);
      NS.prewarm();
    }).catch(() => {
      NS.go('auth');
      NS.notice('Could not create a secure session. Check your connection and try again.');
    });
    /* A vertical phone video in a 16:9 box: the skater is as big as
       a finger. The box adjusts to the clip's orientation. */
    (() => {
      const v = document.getElementById('ans-video'), st = document.getElementById('ans-vid-stage');
      if (!v || !st) return;
      v.addEventListener('loadedmetadata', () => {
        const portrait = v.videoHeight > v.videoWidth;
        st.classList.toggle('is-portrait', portrait);
        /* On a phone, a 3:4 box for a 9:16 clip gave black bars on the sides,
           and the visible width of the skater did not grow from that. The box takes
           the clip's own aspect; height is CSS (max-height), width comes from it. */
        st.style.aspectRatio = portrait && v.videoWidth ? `${v.videoWidth} / ${v.videoHeight}` : '';
        v.style.objectFit = '';
        v.style.objectPosition = '';
      });
      /* A vertical clip RE-ENCODED to 16:9 with black bars (as Telegram and some
         cameras deliver it): the file is landscape, so is-portrait does not trigger,
         and on a phone the skater takes a third of the width. We read the first frame,
         find the content bounds by columns and narrow the scene to them: the bars
         go off the edge, and the whole skeleton
         stays in frame. The overlay canvas is not drawn, so the coordinate shift
         breaks nothing. */
      const cropBakedBars = () => {
        try {
          if (!v.videoWidth || v.videoHeight > v.videoWidth) return;
          const W = 96, H = 54, c = document.createElement('canvas');
          c.width = W; c.height = H;
          const g = c.getContext('2d', { willReadFrequently: true });
          g.drawImage(v, 0, 0, W, H);
          const d = g.getImageData(0, 0, W, H).data;
          const col = new Array(W).fill(0);
          for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
            const i = (y * W + x) * 4; col[x] += d[i] + d[i + 1] + d[i + 2];
          }
          const lit = col.map(s => s / (H * 3) > 18);
          let l = 0, r = W - 1;
          while (l < W && !lit[l]) l++;
          while (r > l && !lit[r]) r--;
          const frac = (r - l + 1) / W;
          if (frac > 0.85 || frac < 0.2) return;
          const lf = l / W, rf = (r + 1) / W;
          st.style.aspectRatio = `${(rf - lf) * v.videoWidth} / ${v.videoHeight}`;
          st.style.maxHeight = '62vh';
          v.style.objectFit = 'cover';
          v.style.objectPosition = `${(lf / (1 - (rf - lf))) * 100}% 50%`;
          st.classList.add('is-cropped');
        } catch (e) { }
      };
      v.addEventListener('loadeddata', cropBakedBars);
    })();
  }

  function bootPart1() {
    /* SAMPLE ANALYSIS for a first visit, so a new visitor sees an answer before filming a jump.
       The sample is a real engine task marked tools/demo_job.py;
       when the server names none, there is no button (we invent nothing). */
    (function wireDeclareChips() {
      const host = document.getElementById('declare-chips');
      if (!host) return;
      /* one register: 'Axel', 'Lutz', 'Toe loop', 'Flip' (not mixed case) */
      const OPTS = [['Axel', 'Axel'], ['Salchow', 'Salchow'], ['Toe loop', 'Toe loop'],
                    ['Loop', 'Loop'], ['Flip', 'Flip'], ['Lutz', 'Lutz']];
      const paint = () => {
        host.innerHTML = OPTS.map(([k, en]) =>
          `<button type="button" class="rz-chip${NS.declaredJump === k ? ' is-on' : ''}" data-decl="${k}" aria-pressed="${NS.declaredJump === k}">${en}</button>`).join('');
        host.querySelectorAll('[data-decl]').forEach(b => {
          b.onclick = () => {
            const k = b.getAttribute('data-decl');
            NS.declaredJump = NS.declaredJump === k ? '' : k;   /* a repeated tap clears the choice */
            try { sessionStorage.setItem('js.declared', NS.declaredJump); } catch (_) { }
            paint();
          };
        });
      };
      paint();
      /* revolutions and consent appear only after a jump is chosen: until then
         the screen is not a wall of ten buttons (a test through the eyes of a new user) */
      const reveal = () => {
        const t = document.getElementById('declare-turns');
        const c = document.getElementById('train-consent-row');
        if (t) t.hidden = !NS.declaredJump;
        if (c) c.hidden = !NS.declaredJump;
      };
      host.addEventListener('click', () => setTimeout(reveal, 0));
      reveal();
      /* how many revolutions: separate from the name, also optional */
      const th = document.getElementById('declare-turns');
      const TURNS = [['1', 'single'], ['2', 'double'], ['3', 'triple'], ['4', 'quad']];
      const paintT = () => {
        if (!th) return;
        th.innerHTML = TURNS.map(([k, en]) =>
          `<button type="button" class="rz-chip${NS.declaredTurns === k ? ' is-on' : ''}" data-turns="${k}" aria-pressed="${NS.declaredTurns === k}">${en}</button>`).join('');
        th.querySelectorAll('[data-turns]').forEach(b => {
          b.onclick = () => {
            const k = b.getAttribute('data-turns');
            NS.declaredTurns = NS.declaredTurns === k ? '' : k;
            try { sessionStorage.setItem('js.declaredTurns', NS.declaredTurns); } catch (_) { }
            paintT();
          };
        });
      };
      paintT();
      /* The declaration is NOT sticky: a declared lutz must not label the next uploaded
         axel 'before display' (the cleanest label in the pipeline). After
         sending, the declaration and consent are reset, and a single chip '↺ as last time'
         restores everything by an explicit tap. Consent is not set from memory by itself:
         a pre-checked consent is not consent; here it is in the chip's text. */
      const wrap = document.getElementById('record-declare');
      const paintRepeat = () => {
        if (!wrap) return;
        let last = null;
        try { last = JSON.parse(sessionStorage.getItem('js.lastDeclared') || 'null'); } catch (_) { last = null; }
        let chip = document.getElementById('declare-repeat');
        const show = last && last.jump && !NS.declaredJump;
        if (!show) { if (chip) chip.hidden = true; return; }
        if (!chip) {
          chip = document.createElement('button');
          chip.type = 'button'; chip.id = 'declare-repeat'; chip.className = 'rz-chip rz-chip--repeat';
          host.insertAdjacentElement('beforebegin', chip);
        }
        const opt = OPTS.find(o => o[0] === last.jump);
        const tw = TURNS.find(t => t[0] === last.turns);
        chip.textContent = '↺ same as last time: '
          + [opt ? (opt[1]) : last.jump, tw ? (tw[1]) : '', last.consent ? 'with training consent' : '']
            .filter(Boolean).join(' · ');
        chip.hidden = false;
        chip.onclick = () => {
          NS.declaredJump = last.jump; NS.declaredTurns = last.turns || '';
          try { sessionStorage.setItem('js.declared', NS.declaredJump); sessionStorage.setItem('js.declaredTurns', NS.declaredTurns); } catch (_) { }
          paint(); paintT(); reveal();
          const tc = document.getElementById('train-consent');
          if (tc) tc.checked = !!last.consent;
          paintRepeat();
        };
      };
      host.addEventListener('click', () => setTimeout(paintRepeat, 0));
      document.addEventListener('js:declare-sent', () => {
        const tc = document.getElementById('train-consent');
        try { sessionStorage.setItem('js.lastDeclared', JSON.stringify({ jump: NS.declaredJump, turns: NS.declaredTurns, consent: !!(tc && tc.checked) })); } catch (_) { }
        NS.declaredJump = ''; NS.declaredTurns = '';
        try { sessionStorage.setItem('js.declared', ''); sessionStorage.setItem('js.declaredTurns', ''); } catch (_) { }
        if (tc) tc.checked = false;
        paint(); paintT(); reveal(); paintRepeat();
      });
      paintRepeat();
    })();
    (async function wireDemoSample() {
      const box = document.getElementById('record-demo');
      const btn = document.getElementById('btn-demo-sample');
      if (!box || !btn) return;
      let list = [];
      try { const r = await fetch('/demo_jobs'); if (r.ok) list = await r.json(); } catch (_) { }
      if (!Array.isArray(list) || !list.length) return;
      list = list.filter(item => item && typeof item.job === 'string' && /^[A-Za-z0-9_-]+$/.test(item.job));
      if (!list.length) return;
      const choose = document.getElementById('demo-choose');
      const label = document.getElementById('demo-choose-label');
      if (choose && list.length > 1) {
        choose.replaceChildren(...list.map(item => {
          const option = document.createElement('option');
          option.value = item.job;
          option.dataset.labelEn = item.label_en || 'Sample analysis';
          option.textContent = option.dataset.labelEn;
          return option;
        }));
        choose.hidden = false;
        if (label) label.hidden = false;
      }
      box.hidden = false;
      btn.onclick = () => NS.openJob(choose && !choose.hidden ? choose.value : list[0].job);
    })();
    /* analysis link (/coach/s/<token> -> /?job=…) */
    try {
      const jq = new URLSearchParams(location.search).get('job');
      if (jq && /^[A-Za-z0-9_-]+$/.test(jq)) { NS.sharedJobId = jq; history.replaceState(null, '', location.pathname); setTimeout(() => NS.openJob(jq), 300); }
    } catch (_) { }
  }

  function bootPart2() {
    // Check Onboarding
    NS._booting = true;
    // Analysis is available at once; the profile is filled in separately when needed.
    NS.go('record');
    NS._booting = false;

    // Desktop-only secondary navigation (hidden on phones by CSS)
    document.querySelectorAll('.tabs__s[data-go]').forEach(b => {
      b.onclick = () => NS.go(b.getAttribute('data-go'));
    });
    // Bind Navigation Tabs
    document.querySelectorAll('.tabs__b').forEach(b => {
      b.onclick = (e) => {
        const btn = e.currentTarget || b;
        const tab = btn.getAttribute('data-tab');
        if (tab) NS.go(tab);
      };
    });

    // Multi-Jump Attempt Selector Pills
    document.querySelectorAll('.attempt-pill').forEach(p => {
      p.onclick = () => {
        const att = parseInt(p.getAttribute('data-att') || 0);
        NS.renderAttempt(att);
      };
    });

    // Readiness Selector Buttons: the choice goes to the server (feel=) and rebuilds the session
    document.querySelectorAll('.readiness-b').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('.readiness-b').forEach(b => b.classList.remove('is-on'));
        btn.classList.add('is-on');
        NS.playClickSound(600, 0.03);
        const v = btn.getAttribute('data-rpe') === 'okay' ? 'ok' : btn.getAttribute('data-rpe');
        if (window.COACH && window.COACH.setTodayFeel) {
          window.COACH.setTodayFeel(v);
          const note = document.getElementById('readiness-note');
          if (note) { note.textContent = 'Rebuilding the session…'; note.dataset.live = '1'; }
          if (window.COACH.refresh) window.COACH.refresh(true);
        }
      };
    });

    // Header Actions
    const backBtn = document.getElementById('btn-back');
    if (backBtn) backBtn.onclick = NS.goBack;
    const todayLearn = document.getElementById('btn-today-learn');
    if (todayLearn) todayLearn.onclick = () => NS.go('learn');
    const tl2 = document.getElementById('btn-today-learn2');

    const ta2 = document.getElementById('btn-today-ask2');

    const tl3 = document.getElementById('btn-today-learn3');

    const ta3 = document.getElementById('btn-today-ask3');

    const todayAsk = document.getElementById('btn-today-ask');
    if (todayAsk) todayAsk.onclick = () => NS.go('coach');

    const drillBackBtn = document.getElementById('btn-drill-back');
    if (drillBackBtn) drillBackBtn.onclick = NS.goBack;

    const accBtn = document.getElementById('btn-account');
    if (accBtn) accBtn.onclick = () => NS.go('account');

    const themeBtn = document.getElementById('btn-theme');
    if (themeBtn) themeBtn.onclick = NS.toggleTheme;

    // Theme pickers in Account
    document.querySelectorAll('.theme-b[data-theme]').forEach(b => {
      b.onclick = () => NS.setTheme(b.getAttribute('data-theme'));
    });

    // Sound toggle in Account
    const paintSound = () => {
      const on = NS.soundOn();
      document.getElementById('btn-sound-on')?.classList.toggle('is-on', on);
      document.getElementById('btn-sound-off')?.classList.toggle('is-on', !on);
    };
    const sOn = document.getElementById('btn-sound-on');
    const sOff = document.getElementById('btn-sound-off');
    if (sOn) sOn.onclick = () => { try { localStorage.setItem('js.sound', '1'); } catch (_) { } paintSound(); NS.playClickSound(600, 0.03); };
    if (sOff) sOff.onclick = () => { try { localStorage.setItem('js.sound', '0'); } catch (_) { } paintSound(); };
    paintSound();

    /* 'My assessment first' is a profile setting;
       it takes effect the next time an analysis is opened. */
    const paintGuess = () => {
      let on = false;
      try { on = localStorage.getItem('js.guessMode') === '1'; } catch (_) { }
      document.getElementById('btn-guess-on')?.classList.toggle('is-on', on);
      document.getElementById('btn-guess-off')?.classList.toggle('is-on', !on);
    };
    const gOn = document.getElementById('btn-guess-on');
    const gOff = document.getElementById('btn-guess-off');
    if (gOn) gOn.onclick = () => { try { localStorage.setItem('js.guessMode', '1'); } catch (_) { } paintGuess(); };
    if (gOff) gOff.onclick = () => { try { localStorage.setItem('js.guessMode', '0'); } catch (_) { } paintGuess(); };
    paintGuess();

    // Last answer click
    const lastAns = document.getElementById('card-last-answer');
    if (lastAns) {
      lastAns.onclick = async () => {
        /* One mapper for both entry points: the card (out_json path, restoreAttemptFromResult
           mapper, without noJump, score ranges, name pairs) is only a fallback, used when
           /summary is unavailable. */
        /* The card shows the LAST analysis, so open exactly that one, not
           whatever is loaded now (the user may have opened someone else's link
           or an older analysis from the journal), and the same attempt as on the card. */
        if (NS.lastAnswerJob && (NS.lastJobId !== NS.lastAnswerJob || !NS.activeAttempts.length)) {
          const r = await NS.openJob(NS.lastAnswerJob, NS.lastAnswerStem);
          if (r !== null) return;
          if (NS.activeAttempts.length && NS.lastJobId !== NS.lastAnswerJob) return;   // openJob already explained it
        }
        if (!NS.activeAttempts.length && NS.lastAnswerStem) {
          const subEl = document.getElementById('last-ans-sub');
          if (subEl) subEl.textContent = 'The files of this analysis were not kept on the server — it cannot be opened.';
          return;
        }
        const _i = NS.lastAnswerStem ? NS.activeAttempts.findIndex(a => a && a.stem === NS.lastAnswerStem) : -1;
        NS.renderAttempt(_i > 0 ? _i : 0);
        NS.go('answer');
      };
    }

    const btnTerm = document.getElementById('btn-verdict-term');
    if (btnTerm) btnTerm.onclick = () => {
      const ex = document.getElementById('ans-rotation-explainer');
      if (!ex) return;
      ex.hidden = !ex.hidden;
      btnTerm.setAttribute('aria-expanded', String(!ex.hidden));
    };

    const btnFrameToggle = document.getElementById('btn-frame-toggle');
    if (btnFrameToggle) {
      btnFrameToggle.onclick = () => {
        const on = document.getElementById('btn-frame-prev').style.display === 'none';
        ['btn-frame-prev', 'btn-frame-next'].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.display = on ? '' : 'none';
        });
        btnFrameToggle.classList.toggle('is-on', on);
      };
    }
  }

  Object.assign(NS, {
     boot,
  });
})();
