/* ══════════════════════════════════════════════════════════════════════
   JUMPSIGHT — INTERFACE TEXT (EN)
   Matches exact copy from design/*.dc.html
   ══════════════════════════════════════════════════════════════════════ */

/* SHARED JOURNAL CACHE. /coach/history was queried by THREE different
   functions from two files on every page load: loadHistory
   (coach.js), fillLiveStats (coach.js, starts at module level), and
   loadLastAnswer (app.js). They could not share data, because they run in a
   different order and in different closures. Now they share through this
   short-lived cache; the failure semantics are preserved ({ok:false}), otherwise
   "server did not respond" would become indistinguishable from "journal is empty". */
window.__jsHistory = (function () {
  let pending = null, at = 0;
  return function (force) {
    const now = Date.now();
    if (!force && pending && (now - at) < 3000) return pending;
    at = now;
    /* English only */
    const _lang = 'en';
    pending = fetch('/coach/history?lang=' + encodeURIComponent(_lang))
      .then(r => r.ok ? r.json().then(d => ({ ok: true, data: d || [] }))
                      : { ok: false, data: [] })
      .catch(() => ({ ok: false, data: [] }));
    return pending;
  };
})();

(function () {
  'use strict';

  const DICT = {
      close: "Close",
      accountName: "Name",
      accountSave: "Save",
      accountRole: "Role",
      accountEditName: "Edit name",
      accountInvite: "Send to my coach",
      accountCodeSub: "So your coach can see your analyses",
      accountSkater: "I am a skater",
      accountCoach: "I am a coach",
      accountMyCoach: "My coach",
      accountMyTeam: "My team",
      accountStudents: "My skaters",
      accountAdd: "Add",
      accountCode: "Code for your coach",
      accountCopy: "Copy",
      accountSignOut: "Sign out",
      accountApple: "Continue with Apple",
      accountCodeHelp: "Give this code to your coach: they will see your analyses and can leave comments.",
      accountCodeLogin: "Transfer a profile to this phone",
      accountLogin: "Sign in",
      accountNamePh: "Your name",
      accountCoachCode: "Coach code",
      accountStudentCode: "Skater code",
      accountProfileCode: "Profile code",
      videoControls: "Video controls",
      playPause: "Pause / play",
      previousFrame: "Previous frame",
      nextFrame: "Next frame",

      /* Tabs & General */
      tabToday: 'Training',
      tabTeam: 'Team',
      tabRecord: 'Analyse',
      tabProgress: 'Progress',
      tabLearn: 'Terms and rules',
      openCard: 'Open analysis',
      share: 'Share',
      ariaTheme: 'Theme',
      titleToggleTheme: 'Toggle theme',
      ariaProfile: 'Profile',

      /* Today (3.3) */
      focusEyebrow: 'Focus of the day',
      tabAsk: 'Ask',
      weekPlanTitle: 'Plan for the week',
      unitSec: ' s',
      errCardTitle: 'Execution errors',
      fatigueEyebrow: 'FATIGUE AND PAIN MONITORING',
      v000: "just now",
      teamTitle: "Coach workspace",
      teamSub: "Student analyses and the next session focus",
      teamSearch: "Find a student",
      teamSearchPlaceholder: "Student name or code",
      teamFilters: "Student filters",
      teamAll: "All",
      teamNew: "New analyses",
      teamFocus: "With focus",
      teamInvite: "Invite a student",
      teamEmptyLede: "What a team gives you:",
      teamEmptyP1: "a student's jump analyses and how many days since they last filmed",
      teamEmptyP2: "which error persists: not a one-off miss, but something that has not moved in several attempts",
      teamEmptyP3: "you can set a 14-day session focus, and the student sees it came from you",
      teamEmptyCodeHelp: "Give a student this code to enter under “Profile → My coach”, or enter their code below.",
      authOpen: "Sign in or create account",
      authWhy: "With an account your journal and sessions are available from any phone and to your coach.",
      authWhyCoach: "Without an account, your students exist only in this browser. Clearing this phone’s data removes the link to your whole team.",
      authTitleIn: "Sign in",
      authSubIn: "Your attempts and sessions follow you to any phone.",
      authOr: "or with email",
      authPassword: "Password",
      authShowPw: "Show password",
      authPwHint: "At least 8 characters.",
      authNoAcc: "No account yet?",
      authCreate: "Create one",
      authGuest: "Continue without an account",
      v001: "Wellbeing data appears once you mark drills in sessions.",
      v002: "📄 Coach report: print or save as PDF",
      drillSrc: "Source: JumpSight knowledge base · Biomechanics, King et al. (1994)",
      u001: "Ukrainian",
      u002: "English",
      u003: "Sounds",
      guessSetting: "Guess the jump before the result",
      nextStepEyebrow: "Next step",
      shareTitle: "Share your jump",
      sharedTitle: "Someone shared a jump analysis with you",
      sharedSub: "Want the same for your jump? One phone video, an answer in about a minute.",
      sharedCta: "Analyse my jump",
      shareMaking: "Making the card…",
      shareImage: "Share image",
      shareLink: "Send a link to the analysis",
      shareNote: "The card carries only measured numbers, each with how sure the system is.",
      cmpOpen: "⇆ Compare",
      cmpTitle: "Compare attempts",
      cmpWith: "Compare with",
      cmpNote: "Both videos are aligned on the measured take-off moment. Each number is a separate measurement of its attempt; a difference within ± is not a difference.",
      frameBack: "frame",
      frameFwd: "frame",
      scrubAria: "Seek the video",
      scrubAll: "whole video",
      watchJump: "▶ watch the jump",
      heroShare: "↗ share",
      nextStepBtn: "Open the session",
      u004: "On",
      soundOn: "On",
      soundOff: "Off",
      u005: "Parent view / Training volume",
      u006: "SESSIONS THIS WEEK",
      u007: "CLEAN ATTEMPTS, %",
      u008: "Start the set",
      u009: "How do I fix under-rotation?",
      u010: "Why do the arms open?",
      u011: "Rest between sets",
      chipLzF: "Lutz vs Flip",
      sec30: '30 s',
      sec45: '45 s',
      sec60: '60 s',
      sec90: '90 s',
      sec120: '120 s',
      t000: "Chat with the AI coach",
      t001: "Answers cite their sources",
      t002: "Step by step",
      t003: "COMMON MISTAKES",
      t004: "PROGRESSION GATE",
      t005: "3 sets of 6 clean reps without breaking the axis.",
      t006: "Profile not filled in",
      t007: "Name, level and coach are not collected in this version",
      t008: "Appearance",
      t009: "Auto",
      t010: "Light",
      t011: "Dark",
      t019: "it got too hard",
      t020: "REST BETWEEN SETS",
      s000: "TODAY",
      s001: "Plan for the day",
      s002: "ANSWER READY · WHILE YOU TRAIN",
      s003: "Open →",
      s004: "No records",
      toolsToggle: "Analysis tools",
      toolsToggleShort: "tools",
      fullscreenBtn: "⤢ Full screen",
      fullscreenTitle: "Video full screen",
      oneThingEyebrow: "THE ONE THING",
      rotationExplainer: "This is the rotation count the way judges count it. Measured flight revolutions are shown separately: rotation at takeoff and landing can make these numbers differ.",
      revealDetail: "Show the measurement",
      guessEyebrow: "YOUR CALL FIRST",
      guessTitle: "What jump was that?",
      guessDesc: "Your answer first, the measurement second. That trains your own feel instead of just reading a number.",
      guessTurns: "How many rotations do you think you got?",
      guessReveal: "Show the measurement",
      guessSkip: "Just show the numbers",
      guessMatch: "Your feel matched the measurement.",
      guessDiff: "Your feel and the measurement differ - that gap is the most useful place to work.",
      vcTitle: "Is this right?",
      vcOptional: "Give feedback on the analysis",
      vcDesc: "Feedback helps review analysis quality. It is optional.",
      vcYes: "Yes, correct",
      vcNo: "No, fix it",
      vcPick: "Which jump was it?",
      vcTurns: "How many rotations?",
      vcSave: "Save correction",
      vcOther: "A different jump or a different rotation count",
      attemptsTitle: "All attempts in this video",
      keysHint: "← → frame · Shift — 10 frames · space — pause · [ ] — attempt",
      todayLearnLink: "Glossary: terms and ISU rules",
      surveyEyebrow: "About you",
      surveyOpen: "Fill in",
      surveyEdit: "Edit",
      surveySave: "Save",
      surveyIntro: "7 questions, one minute, and sessions fit you",
      goalPickTitle: "Or pick a goal. The session is built without a video.",
      liveCardEyebrow: "Live training",
      liveCardTitle: "Prop up the phone and skate",
      liveCardDesc: "Every jump is analysed on its own while you are on the ice. Tap “Stop → analyse” for a breakdown of all attempts.",
      liveCardBtn: "Record an on-ice session",
      todayAskLink: "Ask the coach: technique, rules, drills", navLearn: "Glossary", navAsk: "Ask the coach",
      attemptsListTitle: "List of all attempts",
      vcPairTitle: "Lutz or Flip?",
      vcPairDesc: "One camera cannot see the take-off edge. Name the jump, and the system remembers it for your next videos.",
      frameStepBtn: "frame by frame",
      w000: "Minimise",
      w001: "How to do it",
      w002: "Common mistakes",
      w003: "Rep done",
      w004: "Set done",
      w005: "End session",
      w006: "The next set starts automatically when the countdown ends.",
      w007: "+30 s",
      w008: "Skip",
      w009: "How did the session feel?",
      w010: "The session difficulty and drill results help shape your next plan. If you do not choose, the difficulty remains unknown.",
      w011: "Easy: I could do more",
      w012: "Right: hard but clean",
      w013: "Too much: technique broke down",
      w014: "Save · back to Today",
      w015: "ISU TERM",
      w016: "Open my training session",
      w017: "Ask the coach about this term",
      w018: "CURRENT SESSION",
      w019: "Resume session",
      w020: "Drill video",
      w021: "Ask anything about technique, ISU rules or drills.",
      w022: "Report for coach and parents",
      w023: "The report uses only measured analyses, the same as the journal. No guesses.",
      w024: "🖨️ Print report",
      w025: "↗️ Share",
      learnSearchPh: "Ask the knowledge base…",
      s005: "Upload a video to analyse",
      s006: "",
      s007: "Step 1 of 4 · finding jump attempts",
      waitEta: "Time depends on the video length. No need to wait here: we will tell you when it is ready.",
      speedWord: "speed",
      s008: "YOUR VIDEO · ANALYSIS RUNNING ON THE SERVER",
      s009: "waiting…",
      s010: "queued",
      s011: "Go to training for now",
      lastAnsRevLbl: 'rotations in flight',
      s012: "Warm-up",
      s013: "ATTEMPTS IN THIS VIDEO",
      s014: "1 · Attempt",
      s015: "JUMP ANALYSIS",
      s016: "ROTATIONS",
      s017: "Jump analysis",
      s018: "Assessed under ISU rules",
      s019: "takeoff —",
      s020: "flight —",
      s021: "landing —",
      s022: "🦴 Skeleton",
      s023: "🧊 3D avatar",
      s024: "🔊 Read aloud",
      s025: "s",
      s026: "cm",
      back: "Back",
      videoSpeedTitle: "Video speed",
      phaseTakeoffTitle: "Takeoff",
      phaseFlightTitle: "Flight",
      phaseLandingTitle: "Landing",
      skeletonOverlayTitle: "Biomechanics overlay",
      avatar3dTitle: "3D jump avatar",
      zoomTitle: "Zoom foot/blade",
      voiceTitle: "Voice narration",
      s027: "2 found",
      s028: "What the coach will do with this",
      s029: "STABILITY AND GLIDE",
      s030: "Strong stability and a smooth exit",
      s031: "Landing knee angle:",
      s032: "Torso lean:",
      s033: "The exit position is clean and the knee absorbs the load softly.",
      s034: "Next attempt · 2 of 3",
      s035: "appear once analyses measure jump height",
      s036: "TEST 1 OF 7",
      s037: "Skip",
      s038: "Save · next",
      s039: "Coach report · PDF",
      s040: "DRILL · LEVEL 2 · OFF-ICE",
      s041: "Closed-axis hold",
      s042: "SETS",
      s043: "REPS",
      s044: "REST",
      s045: "ONE CUE",
      s046: "“Imagine flying through a narrow tube — don’t touch its walls until you land.”",
      s047: "Dosage and technique",
      s048: "Quality over speed. If the axis opens early, stop and rest.",
      recordGuideTitle: 'Before recording',
      shotSide: 'Side-on to the camera', shotFps: '60 fps if available',
      shotWhole: 'Whole jump in frame', quickTimer: 'Quick drill timer',
      timerStart: 'Start', timerReset: 'Reset',
      learnFeatTitle: 'What under-rotation means (q and <)',
      learnFeatDesc: 'The ISU rules on under-rotation, the 90° (q) boundary and the drills that fix it.',
      learnFeatBtn: 'Read the explanation',
      viewfinderCue: 'Stand side-on to the camera',
      trendsEyebrow: 'Weekly trends',
      fitnessEyebrow: 'Physical tests',
      skillsEyebrow: 'Skill profile',
      goalEyebrow: 'Goal',
      recordsEyebrow: 'PERSONAL BESTS',
      isuMatrixEyebrow: 'ISU jump classification',
      fitnessDetails: 'All test details',
      fitnessRunBtn: 'Take the tests one by one',
      fitnessManualBtn: 'Enter results manually',
      goalEditBtn: 'Change goal',
      whySession: 'Why this session',
      toeJumps: 'Toe jumps:',
      edgeJumps: 'Edge jumps:',
      toeJumpsList: 'Toe Loop, Flip, Lutz',
      edgeJumpsList: 'Salchow, Loop, Axel',

      btnLiveRec: 'Live recording: training with feedback',
      btnDemoSample: 'See a sample analysis',
      demoCardTitle: 'No video at hand?',
      demoCardSub: 'Open a real analysis of a real jump. These are the same screens you will get.',
      declareTitle: 'Which jump? Optional, the system will check it',
      trainConsent: 'Allow this video and claim to be used to train the system',
      demoChooseLabel: 'Sample analysis',

      liveCancel: 'Cancel',

      liveStop: '■ Stop → analyse',

      quickModeOn: 'Quick',

      goalsEyebrow: 'By goal · did the drills help',

      markDoneAll: 'Did the whole session? Mark it done',

      whatIsThis: 'what does this mean?',

      todayFocus: "Today's session comes from your own analyses",
      todayFocusDesc: 'The focus appears once the plan loads.',
      todaySessionTitle: "Today's session",
      continueSession: 'Start session · block 1 of 5',
      lastAnswerEyebrow: 'Last answer',
      readinessEyebrow: 'How you feel today',
      readinessQuestion: 'How do your legs feel after the last session?',
      rpeFresh: 'Fresh',
      rpeOkay: 'Okay',
      rpeTired: 'Tired',
      readinessNote: 'Default is “Okay”. Change it and the session adapts.',

      /* Record & Waiting (3.1 & 3.2) */
      recEyebrow: 'Jump',
      recTitle: 'Film a jump',
      recDesc: 'Upload a jump video for its name, rotation count and measurement details.', recordHonest: 'Any phone video is fine. The result says what it could and could not measure, and why.',
      btnShoot: 'Record now',
      btnUpload: 'Choose from gallery',
      recordFileHint: 'MP4 or MOV from your phone · analysis starts right away',
      degPerSec: '°/s',
      recordDropHint: 'Or drag a video here',
      recordExplainer: '',
      analysisFailedTitle: 'Could not finish the analysis',
      retryAnalysis: 'Try again',
      cancelAnalysis: 'Cancel this analysis',
      studentEyebrow: 'Skater’s journal',
      previousAttempt: 'Previous attempt',
      nextAttempt: 'Next attempt',
      mainNavigation: 'Main navigation',
      stgAttempts: 'Reading the video',
      stgRotation: 'Finding you and your jumps',
      stgPhases: 'Measuring rotation',
      stgVerdict: 'Answer',
      waitPlay: 'Play video',
      waitEarlyFound: 'Jump found · measuring…',
      waitEarlyFoundMany: '{n} jumps found · measuring…',
      waitEarlyAir: 'In the air',
      waitEarlyLoop: 'YOUR JUMP · HALF SPEED',
      waitLiveReading: 'Reading the video…',
      waitLiveLooking: 'Looking for you in the frame…',
      waitLiveFound1: 'Found 1 jump',
      waitLiveFoundN: 'Found {n} jumps',
      waitLiveFoundCount: 'Found {n} jumps',
      waitLiveMeasuring: 'Measuring rotation…',
      waitLivePreparing: 'Preparing your results…',
      waitLiveDone: 'Done',
      stgValReading: 'reading…',
      stgValLooking: 'looking…',
      stgValMeasuring: 'measuring…',
      stgValDone: 'done',
      stgValFound1: '1 jump',
      stgValFoundN: '{n} jumps',
      stgValFoundCount: '{n} found',
      stgValNone: 'no jumps found',
      stgValTook: '{s} s',
      waitAskEyebrow: 'While you wait',
      waitAskTitle: 'What did you jump?',
      waitAskWhy: 'Your answer, given before you see the numbers, teaches the system the most.',
      waitAskSaved: 'Got it: {j}. It goes with this video as soon as the analysis is ready.',
      waitAskSavedAns: 'Your answer from before the numbers is saved: {j}.',
      waitWarmupEyebrow: 'Use the minutes · warm-up block',
      startWarmup: 'Start warm-up',

      /* Answer (3.1) */
      airTime: 'Air time',
      flightRevs: 'Rotations in flight',
      flightRevsNote: 'flight only; the rest of the turn is on take-off and check-out',
      rotRate: 'Rotation speed in flight',
      jumpHeight: 'Height',
      notMeasuredTitle: 'Measurement details',
      twoNamesTitle: 'Two names apply',
      openToday: 'What to train',
      ansAgain: 'Analyse a new video',
      ansShare: 'Share',
      cleanVerdict: 'Fully rotated (clean)',
      shortVerdict: 'Slightly short of full (q)',
      downgradedVerdict: 'Downgraded (<)',

      /* Progress (3.5 & 3.6) */
      progEyebrow: 'Your progress',
      progTitle: 'Trends and attempt log',
      progSub: 'All measurements are compared strictly with your own history.',
      bestWeekEyebrow: 'BEST THIS WEEK',
      logTitle: 'Attempt log',
      logFilter: 'All jumps',

      /* Learn (3.7) */
      learnEyebrow: 'Knowledge base',
      learnTitle: 'Every word an answer uses, explained once',
      learnFeaturedEyebrow: 'From your last answer',
      learnFeaturedNeutral: 'ISU rules',
      learnTermsTitle: 'Terms',

      /* Onboarding (3.9) */
      obIntroEyebrow: 'JumpSight',
      obIntroTitle: 'Which jump, how many turns?',
      obIntroDesc: 'One phone video shows you the rotations, the jump name, and what the camera could not see.',
      obExampleEyebrow: 'Example answer · not your data',
      obExampleRevUnit: "rotations (judges' count) · count estimated · name likely",
      obExampleVerdict: 'Double Lutz · no errors found',
      obExampleChecks: 'Checked: fall, step-out, touch-down, hand-down, axis. Two-foot landing and landing knee cannot be checked from one camera.',
      obExampleAirLbl: 'IN THE AIR',
      obExampleHeightLbl: 'HEIGHT',
      obExampleFlightLbl: 'ROTATION SPEED',
      obHonestTitle: 'What this video did NOT show',
      obHonestBody: 'One camera cannot see the Lutz/Flip edge, so the app says so instead of guessing.',
      obExampleFoot: 'A real measurement of a real phone video. Your video gets its own numbers, only the ones that could be measured.',
      obIntroCta: 'Next: 1 question',
      onboardSkip: 'Skip, choose later',
      onboardEyebrow: 'Working jump',
      onboardTitle: 'Which jump are you working on?',
      onboardDesc: 'It sets the session focus and the order of names on the answer screen. You can change it later.',
      onboardContinue: 'Save and continue',

      /* Waiting & Disambig */
      waitAnalyzing: 'Analyzing jump',
      waitVideo: 'Preparing your analysis',
      disambigEyebrow: 'Two jump names',

      /* Account */
      accountEyebrow: 'Personal account',
      accountTitle: 'Skater profile',
      accountSettingsTitle: 'Application settings',

      /* Coach Hub */
      coachEyebrow: 'Assistant · JumpSight',
      coachTitle: 'Ask the coach',
      coachDesc: 'Questions about technique, ISU rules and drills, with the source cited.',
      chatPlaceholder: 'Ask the coach…',
      commentPlaceholder: 'Comment for the skater…',
      send: 'Send'
  };

  function t(key) {
    /* an empty string is deliberate (nothing to show), not a leaked key */
    if (key in DICT) return DICT[key];
    return key;
  }

  /* Fill every [data-t], [data-t-ph], [data-t-aria] and [data-t-title] element,
     except those already holding live data (data-live="1"). */
  function apply() {
    document.documentElement.lang = 'en';
    document.title = 'JumpSight — jump analysis';
    document.querySelectorAll('[data-t]').forEach(el => {
      if (el.dataset.live === '1') return;
      const val = t(el.getAttribute('data-t'));
      if (val !== undefined && val !== null) el.textContent = val;
    });
    document.querySelectorAll('[data-t-ph]').forEach(el => {
      const val = t(el.getAttribute('data-t-ph'));
      if (val) el.placeholder = val;
    });
    document.querySelectorAll('[data-t-aria]').forEach(el => {
      const val = t(el.getAttribute('data-t-aria'));
      if (val) el.setAttribute('aria-label', val);
    });
    document.querySelectorAll('[data-t-title]').forEach(el => {
      const val = t(el.getAttribute('data-t-title'));
      if (val) el.setAttribute('title', val);
    });

    /* Onboarding jump names are built from the jump code (data-jump) */
    const TURN = { 1: 'Single', 2: 'Double', 3: 'Triple', 4: 'Quad' };
    const KIND = { A: 'Axel', S: 'Salchow', T: 'Toe loop', Lo: 'Loop', F: 'Flip', Lz: 'Lutz' };
    document.querySelectorAll('.onboard-picker-btn[data-jump]').forEach(btn => {
      const code = btn.getAttribute('data-jump') || '';
      const turn = TURN[parseInt(code[0], 10)];
      const kind = KIND[code.slice(1)];
      const nameEl = btn.querySelector('.onboard-picker-name');
      if (!turn || !kind || !nameEl) return;
      nameEl.textContent = `${turn} ${kind}`;
    });

    document.querySelectorAll('.tabs__b').forEach(b => {
      const tab = b.getAttribute('data-tab');
      if (tab === 'today') b.querySelector('span').textContent = t('tabToday');
      if (tab === 'record') b.querySelector('span').textContent = t('tabRecord');
      if (tab === 'progress') b.querySelector('span').textContent = t('tabProgress');
      if (tab === 'learn') b.querySelector('span').textContent = t('tabLearn');
    });
  }

  window.TEXT = { t, apply };
  window.t = t;
})();
