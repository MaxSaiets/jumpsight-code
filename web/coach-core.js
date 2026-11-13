/* Coach shared helpers: journal names, dosage parser, plan state, learn terms, workout draft and quick timer. */
(function () {
  'use strict';
  const NS = ((window.JS = window.JS || {}).coach = {});
  /* The name in the journal follows the same rule as the
     answer (historyJumpName from app.js): the "Lutz or flip" pair stays
     a pair. And the pair is NOT counted as "Lutz" in filters, goals, or tallies. */
  const histName = a => (window.APP && window.APP.historyJumpName)
    ? window.APP.historyJumpName(a)
    : ((window.APP && window.APP.jumpNameLocal && window.APP.jumpNameLocal(a.jump)) || a.jump);
  const nameIsSure = a => !!a && !(a.name_uncertain === true || a.name_uncertain === 'True')
    && !(typeof a.name_display === 'string' && a.name_display.includes('/'))
    && !(a.name_is_family === true || a.name_is_family === 'True');

  function logName(nameTxt, countTxt, a) {
    if (!countTxt) return nameTxt;
    const sure = !(a.name_uncertain === true || a.name_uncertain === 'True') && a.jump && a.jump !== 'None';
    if (!sure) return `${nameTxt} · ${countTxt}`;
    const est = countTxt.startsWith('≈ ');
    const c = est ? countTxt.slice(2) : countTxt;
    return `${est ? '≈ ' : ''}${c.charAt(0).toUpperCase()}${c.slice(1)} ${nameTxt}`;
  }

  const H = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[ch]);
  /* Drill name: the backend provides the English name. */
  const LOC = () => 'en-US';
  /* A readable drill code is the fallback when no name is given. */
  const NAME = (id, fallback) => (fallback || String(id || '').replace(/_/g, ' '));

  /* Dosage is PARSED from the prescribed text, not invented: "3x6" ->
     3 sets of 6; "5 from each leg" -> 2 sets of 5 (each leg =
     its own set); "5 each" -> 1x5; otherwise nothing (null), not 3x6 by
     default. The single source for the drill card (openDrill, app.js) and
     the set tracker (startSession, below). */
  /* Dosage parsed from the prescribed text (hence [^\s\d]* instead of \w). Formats in the database (51 drills):
     "3x8", "2x5 each side", "3 sets of 8-10 jumps", "3 attempts of
     1-2 rotations", "3 holds of 15-20 s", "5 series", "2 passes",
     "series of 6-8", "5 from each leg". "3 sets of 8-10"
     is 3×(8–10), and "3 holds of 15-20 s" is not counted as reps.
     reps — the counter number (top of the range), repsLabel — for the card
     ("8–10"); holds in seconds are not counted as reps (reps null). */
  function parseDosage(desc) {
    /* Merge of two rewrites: ranges "8–10" and holds + a timer for blocks without reps ("3-5 min",
       "45 s"). Contract:
       { sets, reps, repsLabel, seconds, secondsLabel }. */
    const s = String(desc || '').toLowerCase();
    const range = (a, b) => ({ reps: +(b || a), repsLabel: b ? `${+a}–${+b}` : String(+a) });
    const none = { sets: null, reps: null, repsLabel: null, seconds: null, secondsLabel: '' };
    const done = o => ({ ...none, ...o });
    let m = s.match(/(\d+)\s*[x×]\s*(\d+)(?:\s*[-–]\s*(\d+))?/);
    if (m) return done({ sets: +m[1], ...range(m[2], m[3]) });
    m = s.match(/(\d+)\s*(?:sets?|attempts?|series|passes)\s*(?:of\s*)?(\d+)?(?:\s*[-–]\s*(\d+))?/);
    if (m && m[2]) return done({ sets: +m[1], ...range(m[2], m[3]) });
    if (m) return done({ sets: +m[1] });
    m = s.match(/(\d+)\s*holds?/);
    if (m) return done({ sets: +m[1] });
    m = s.match(/(\d+)(?:\s*[-–]\s*(\d+))?\s*(?:on\s+)?each\s+(?:side|leg|foot)/);
    if (m) return done({ sets: 2, ...range(m[1], m[2]) });
    m = s.match(/(?:in sets of|sets of)\s*(\d+)(?:\s*[-–]\s*(\d+))?/);
    if (m) return done({ ...range(m[1], m[2]) });
    /* duration without reps: the lower bound of the range is the timer, the text is the caption */
    let dm = s.match(/(\d+)(?:\s*[-–]\s*(\d+))?\s*min/);
    if (dm) return done({ seconds: +dm[1] * 60, secondsLabel: dm[0].trim() });
    dm = s.match(/(\d+)(?:\s*[-–]\s*(\d+))?\s*(?:sec|s)(?![a-z])/);
    if (dm) return done({ seconds: +dm[1], secondsLabel: dm[0].trim() });
    return none;
  }

  NS.mascotAvailable = [];
  NS.warmupIndex = -1;
  NS.livePlan = [];
  NS.todayData = null;
  NS.historyData = [];
  NS.journalFilter = '';
  NS.currentLearnCat = 'all';
  NS.currentLearnSearch = '';

  /* Drill content comes only from the backend. */

  const LEARN_TERMS_DATA = {
    under: {
      title: 'Under-rotation (q and <)',
      /* no unverified rule numbers or percentages */
      rule: 'How the ISU technical panel marks rotation: <strong>“q”</strong> — landed about a quarter short (≈90°), full base value, GOE reduced. <strong>“&lt;”</strong> — short by more than 90° and less than 180°, reduced base value. <strong>“&lt;&lt;”</strong> — 180° or more, scored as the jump with one revolution less.',
      desc: 'Most common causes: a loose or late air position, or too little height and air time (causes base, strong evidence).',
      cat: 'isu',
      drillIdx: 2
    },
    edge: {
      title: 'Wrong or unclear edge (e and !)',
      rule: 'The <strong>“e”</strong> sign means a wrong take-off edge — an inside edge on a Lutz or an outside edge on a flip: reduced base value and GOE. The <strong>“!”</strong> sign marks an unclear edge: no base-value cut, GOE may drop.',
      desc: 'The edge is a tilt of a few degrees that one phone camera cannot see reliably, so the app never makes edge calls and shows “Lutz or flip” when unsure.',
      cat: 'isu',
      drillIdx: 1
    },
    stability: {
      title: 'Skating stability',
      rule: 'Judges reward a steady landing with good flow out of the jump on the GOE scale (-5 to +5). The app checks each landing for faults it can see: a fall, a step-out, a free-foot touch-down, a two-foot landing, a tilted axis.',
      desc: 'Determines how reliable the landing is and prevents falls and step-outs.',
      cat: 'bio',
      drillIdx: 3
    },
    takeoff: {
      title: 'Rotation speed in the air',
      rule: 'How fast the body turns during the flight — the app measures it in °/s. Published norms (Bruening 2018): about 1273°/s (≈3.5 rev/s) for doubles and 1465°/s (≈4.1 rev/s) for triples.',
      desc: 'Angular momentum at take-off is about the same in all six jumps; faster rotation comes from a tighter, quicker pull-in (Yamaguchi & Sakurai 2025).',
      cat: 'bio',
      drillIdx: 2
    },
    ofp: {
      title: 'Off-ice conditioning and plyometrics',
      rule: 'An off-ice programme to raise jump height and rotation speed, built on published strength and conditioning norms.',
      desc: 'Includes springy calf raises, 180/360° jump turns and static axis holds.',
      cat: 'ofp',
      drillIdx: 0
    }
  };

  /* ── 2-Metre Session Player State ── */
  NS.sessionState = {
    completed: new Set(),
    drill: null,
    blockIdx: 0,
    set: 1,
    rep: 0,
    totalSets: 3,
    targetReps: 6,
    holdSec: 3,
    restSec: 90,
    restRemainingSec: 0,
    holdTimer: null,
    restTimer: null,
    rpe: '',
    outcomes: {},
    sessionId: ''
  };

  // The draft is bound to the server-side user and the current plan.
  // Timers are stopped after a reload; time in the background is not drill execution.
  const draftKey = () => {
    const uid = window.APP && window.APP.currentUid && window.APP.currentUid();
    return uid ? `js.workout.${uid}` : null;
  };
  const planSignature = () => JSON.stringify({
    focus: NS.todayData && (NS.todayData.focus_goal || NS.todayData.focus || ''),
    blocks: NS.livePlan.map(b => [b.id, b.dosageDesc, b.steps, b.gate, b.rest])
  });
  function saveWorkoutDraft() {
    const key = draftKey();
    if (!key || !NS.sessionState.sessionId) return;
    try {
      localStorage.setItem(key, JSON.stringify({
        version: 1, updated: Date.now(), signature: NS.sessionState.signature,
        sessionId: NS.sessionState.sessionId, blockIdx: NS.sessionState.blockIdx,
        set: NS.sessionState.set, rep: NS.sessionState.rep,
        timedLeft: NS.sessionState.timedLeft, rpe: NS.sessionState.rpe,
        resting: NS.sessionState.resting || false, restRemainingSec: NS.sessionState.restRemainingSec,
        completed: [...NS.sessionState.completed], outcomes: NS.sessionState.outcomes,
        feedback: NS.sessionState.feedback || false
      }));
    } catch (_) {
      const note = document.getElementById('player-save-error');
      if (note) { note.textContent = 'Could not save the draft on this device.'; note.hidden = false; }
    }
  }
  function clearWorkoutDraft() {
    try { const key = draftKey(); if (key) localStorage.removeItem(key); } catch (_) { }
  }
  function discardedDraftNotice() {
    const start = document.getElementById('btn-start-session');
    if (!start || document.getElementById('workout-draft-notice')) return;
    const note = document.createElement('p');
    note.id = 'workout-draft-notice';
    note.className = 'sub-dim';
    note.setAttribute('role', 'status');
    note.textContent = 'The previous draft could not be restored: the plan changed or more than a day passed. Start a new session.';
    start.insertAdjacentElement('afterend', note);
  }
  function restoreWorkoutDraft() {
    if (!NS.livePlan.length) return;
    const showResume = () => {
      const label = document.getElementById('btn-start-session-label');
      if (label) {
        label.dataset.live = '1';
        label.textContent = 'Resume session';
      }
    };
    if (NS.sessionState.sessionId) { showResume(); return; }
    try {
      const key = draftKey();
      const saved = key && JSON.parse(localStorage.getItem(key) || 'null');
      if (!saved) return;
      if (saved.version !== 1 || saved.signature !== planSignature() ||
          !Number.isFinite(saved.updated) || Date.now() - saved.updated > 86400000 || saved.updated > Date.now() ||
          !/^workout-[A-Za-z0-9_-]+$/.test(saved.sessionId || '') ||
          !Number.isInteger(saved.blockIdx) || saved.blockIdx < 0 || saved.blockIdx >= NS.livePlan.length ||
          !Array.isArray(saved.completed)) {
        clearWorkoutDraft();
        discardedDraftNotice();
        return;
      }
      NS.sessionState.sessionId = saved.sessionId;
      NS.sessionState.signature = saved.signature;
      NS.sessionState.blockIdx = saved.blockIdx;
      NS.sessionState.completed = new Set(saved.completed.filter(id => NS.livePlan.some(b => b.id === id)));
      NS.sessionState.outcomes = Object.fromEntries(Object.entries(saved.outcomes || {}).filter(
        ([id, outcome]) => NS.sessionState.completed.has(id) && ['ok', 'partial', 'fail'].includes(outcome)));
      NS.sessionState.rpe = ['easy', 'right', 'much'].includes(saved.rpe) ? saved.rpe : '';
      NS.sessionState.resume = saved;
      showResume();
    } catch (_) { clearWorkoutDraft(); discardedDraftNotice(); }
  }

  /* ── Coach Quick Timer ── */
  let quickTimerState = {
    totalSec: 45,
    remainSec: 45,
    timer: null,
    running: false
  };

  function playTone(freq, duration) {
    try {
      if (window.APP && window.APP.soundOn && !window.APP.soundOn()) return;
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch (e) { }
  }

  function toggleQuickTimer() {
    if (quickTimerState.running) {
      clearInterval(quickTimerState.timer);
      quickTimerState.running = false;
      document.getElementById('btn-coach-timer-start').textContent = 'Start';
    } else {
      quickTimerState.running = true;
      document.getElementById('btn-coach-timer-start').textContent = 'Pause';
      quickTimerState.timer = setInterval(() => {
        quickTimerState.remainSec--;
        updateQuickTimerUI();
        if (quickTimerState.remainSec <= 0) {
          clearInterval(quickTimerState.timer);
          quickTimerState.running = false;
          quickTimerState.remainSec = quickTimerState.totalSec;
          document.getElementById('btn-coach-timer-start').textContent = 'Start';
          playTone(880, 0.4);
          updateQuickTimerUI();
        }
      }, 1000);
    }
  }

  function resetQuickTimer() {
    clearInterval(quickTimerState.timer);
    quickTimerState.running = false;
    quickTimerState.remainSec = quickTimerState.totalSec;
    const btn = document.getElementById('btn-coach-timer-start');
    if (btn) btn.textContent = 'Start';
    updateQuickTimerUI();
  }

  function setQuickTimerPreset(sec) {
    quickTimerState.totalSec = sec;
    quickTimerState.remainSec = sec;
    resetQuickTimer();
    document.querySelectorAll('.coach-timer-preset').forEach(b => {
      if (parseInt(b.getAttribute('data-sec')) === sec) {
        b.classList.add('is-on');
      } else {
        b.classList.remove('is-on');
      }
    });
  }

  function updateQuickTimerUI() {
    const clock = document.getElementById('coach-quick-timer-clock');
    if (!clock) return;
    const m = Math.floor(quickTimerState.remainSec / 60);
    const s = quickTimerState.remainSec % 60;
    clock.textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  Object.assign(NS, {
     histName, nameIsSure, logName, H, LOC, NAME, parseDosage, LEARN_TERMS_DATA, planSignature,
     saveWorkoutDraft, clearWorkoutDraft, restoreWorkoutDraft, playTone, toggleQuickTimer, resetQuickTimer,
     setQuickTimerPreset, updateQuickTimerUI,
  });
})();
