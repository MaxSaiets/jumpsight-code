/* Remaining control wiring, jump picker, keyboard-aware tabs and the window.APP export. */
(function () {
  'use strict';
  const NS = window.JS.app;
  function bootPart4() {
    const vcYes = document.getElementById('btn-vc-yes');
    if (vcYes) vcYes.onclick = () => NS.vcSend(true);
    const vcNo = document.getElementById('btn-vc-no');
    if (vcNo) vcNo.onclick = () => {
      const fix = document.getElementById('vc-fix');
      if (fix) { fix.hidden = !fix.hidden; if (!fix.hidden) NS.vcPaint(); }
    };
    const vcSave = document.getElementById('btn-vc-save');
    if (vcSave) vcSave.onclick = () => {
      if (!NS.vcJump && !NS.vcTurns) return;
      NS.vcSend(false);
    };

    // Analysis triggers
    /* The camera button is a <label> around input[capture], so a click
       opens the phone camera by itself, without JS. Here there is only the same
       file-selection handler used for the gallery. */
    const camInput = document.getElementById('file-camera');
    if (camInput) camInput.onchange = (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = '';
      if (f) NS.handleFileUpload(f);
    };

    const skipWaitBtn = document.getElementById('btn-skip-waiting-to-answer');
    if (skipWaitBtn) {
      skipWaitBtn.onclick = () => {
        NS.go('today');
      };
    }
    /* Cancel: if queued, the job is removed; if already
       running — the server finishes it, but the screen does not wait for it. No dialog:
       the video is not lost and can be selected again. */
    const cancelBtn = document.getElementById('btn-cancel-analysis');
    if (cancelBtn) cancelBtn.onclick = async () => {
      const jid = NS.activeJobId;
      const owner = NS.activeJobOwner, generation = NS.identityGeneration;
      const cancelEpoch = ++NS.uploadRequestEpoch;
      NS.uploadInFlight = false;
      NS.clearPendingJob(jid, owner);
      NS.stopWatching();
      NS.lastUploadFile = null; NS.retryJobId = null; NS.retryJobOwner = null;
      document.getElementById('rec-waiting').hidden = true;
      document.getElementById('rec-waiting').setAttribute('aria-busy', 'false');
      document.getElementById('rec-intro').hidden = false;
      let msg = 'Analysis cancelled.';
      if (jid) {
        try {
          const r = await fetch(`/cancel/${encodeURIComponent(jid)}`, { method: 'POST' });
          const d = r.ok ? await r.json() : null;
          if (d && d.cancelled === false && d.state !== 'done' && d.state !== 'error')
            msg = 'The analysis had already started — the server will finish it, but we are not waiting here. The result will appear in the journal.';
        } catch (_) { }
      }
      if (cancelEpoch === NS.uploadRequestEpoch && generation === NS.identityGeneration) NS.notice(msg);
    };

    const filePicker = document.getElementById('file-picker');

    if (filePicker) {
      filePicker.onchange = (e) => {
        const file = e.target.files && e.target.files[0];
        e.target.value = '';
        if (file) NS.handleFileUpload(file);
      };
    }

    // Answer next attempt button
    const nextBtn = document.getElementById('btn-next-attempt');
    if (nextBtn) nextBtn.onclick = () => NS.renderAttempt(NS.currentAttemptIdx + 1);

    const openTodayFromAns = document.getElementById('btn-ans-open-today');
    if (openTodayFromAns) openTodayFromAns.onclick = () => NS.go('today');
    /* "another attempt" goes back to the video button; share the result text
       (to the coach in chat) — without localhost links. */
    const againBtn = document.getElementById('btn-ans-again');
    if (againBtn) againBtn.onclick = () => NS.go('record');
    const shareBtn = document.getElementById('btn-ans-share');
    if (shareBtn) shareBtn.onclick = () => NS.openShareSheet();
    NS.initCompare();
    const cmpBtn = document.getElementById('btn-compare');
    if (cmpBtn) cmpBtn.onclick = () => NS.openCompareSheet();
    const inviteBtn = document.getElementById('btn-acc-invite');
    if (inviteBtn) inviteBtn.onclick = async () => {
      const code = NS.ME && NS.ME.code;
      if (!code) return;
      const text = `I analyse my jumps on JumpSight. Add me as your skater — my code: ${code}`;
      const url = location.origin + '/';
      try {
        if (navigator.share) { await navigator.share({ text, url }); return; }
        if (navigator.clipboard) { await navigator.clipboard.writeText(text + '\n' + url); NS.notice('Invite copied — paste it into a message to your coach.'); return; }
      } catch (e) { if (e && e.name === 'AbortError') return; }
      NS.notice(`Your code: ${code}`);
    };
    const heroShare = document.getElementById('btn-hero-share');
    if (heroShare) heroShare.onclick = () => NS.openShareSheet();
    const revokeShareBtn = document.getElementById('btn-ans-revoke-share');
    if (revokeShareBtn) revokeShareBtn.onclick = async () => {
      if (!NS.activeJobIdShown) return;
      const r = await fetch('/coach/share/revoke', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job: NS.activeJobIdShown }) });
      if (r.ok) { revokeShareBtn.hidden = true; NS.notice('Share link revoked.'); }
      else NS.notice('Could not revoke the share link.');
    };
    const openJournalFromAns = document.getElementById('btn-ans-open-journal');
    if (openJournalFromAns) openJournalFromAns.onclick = () => NS.go('progress');


    /* The block reads the REAL focus of the day from the server and
       honestly says where it came from; if the focus is not from this analysis,
       it says so instead of pretending a link. */
    const sharedCta = document.getElementById('btn-shared-cta');
    if (sharedCta) sharedCta.onclick = () => { NS.sharedJobId = null; document.getElementById('ans-shared-banner').hidden = true; NS.go('record'); };
    const nextStepBtn = document.getElementById('btn-next-step');
    if (nextStepBtn) nextStepBtn.onclick = () => NS.go('today');

    // Onboarding Jump Selection
    /* SCOPE STRICTLY TO #scr-onboard. The .onboard-picker-btn class is reused
       by the post-session RPE survey buttons (index.html, data-post-rpe) —
       an unscoped binding here would OVERWRITE their handler from the coach scripts
       (this file initializes later), so the answer to "how did your legs feel"
       would be silently not saved and the loop adapting by RPE would receive nothing. */
    document.querySelectorAll('#scr-onboard .onboard-picker-btn').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('#scr-onboard .onboard-picker-btn').forEach(b => b.classList.remove('is-on'));
        btn.classList.add('is-on');
        NS.playClickSound(520, 0.03);
      };
    });

    /* Onboarding has TWO steps: first show what the system can do
       (a real measurement of the control video), and only then ask. */
    /* Analysis tools are behind one toggle (see the comment in
       index.html): by default only the video is visible. */
    /* The weekly plan is reference material, so it is collapsed (see the comment in
       index.html: it would take 665 px of the first screen for something viewed once a
       week). */
    const wpHead = document.getElementById('week-plan-head');
    if (wpHead) {
      wpHead.onclick = () => {
        const body = document.getElementById('week-plan-body');
        const caret = document.getElementById('week-plan-caret');
        if (!body) return;
        body.hidden = !body.hidden;
        if (caret) caret.textContent = body.hidden ? '+' : '–';
      };
    }

    const btnTools = document.getElementById('btn-tools-toggle');
    if (btnTools) {
      btnTools.onclick = () => {
        const box = document.getElementById('ans-tools');
        if (!box) return;
        box.hidden = !box.hidden;
        btnTools.classList.toggle('is-on', !box.hidden);
        btnTools.setAttribute('aria-expanded', String(!box.hidden));
      };
    }

    const btnObNext = document.getElementById('btn-onboard-next');
    if (btnObNext) {
      btnObNext.onclick = () => {
        const intro = document.getElementById('onboard-step-intro');
        const pick = document.getElementById('onboard-step-pick');
        if (intro) intro.hidden = true;
        if (pick) pick.hidden = false;
        window.scrollTo(0, 0);
        NS.playClickSound(700, 0.04);
      };
    }

    const btnObSkip = document.getElementById('btn-onboard-skip');
    if (btnObSkip) {
      btnObSkip.onclick = () => {
        /* Skipping is a FULL path, not an "unfinished
           onboarding": the focus can be chosen later in the account. Nothing
           is invented (see the comment in finish below). */
        localStorage.setItem('js.onboarded', 'true');
        NS.go('record');
      };
    }

    const btnOnboardFinish = document.getElementById('btn-onboard-finish');
    if (btnOnboardFinish) {
      btnOnboardFinish.onclick = () => {
        /* The scope and [data-jump] are required: an unscoped selector caught
           the RPE button with is-on by default (no data-jump) — and sent to the server
           {"jump": null} (the string "null" in localStorage). */
        const sel = document.querySelector('#scr-onboard .onboard-picker-btn.is-on[data-jump]');
        /* NO CHOICE — NO FOCUS. No plausible substitute is recorded: skipping
           the choice leaves the focus empty, and it can be set later in the account. */
        if (sel) {
          const jump = sel.getAttribute('data-jump');
          localStorage.setItem('js.focusJump', jump);
          /* The server must know the focus too; otherwise "will set the training focus" —
             a promise with no wiring (the value lived only in
             localStorage). Fire-and-forget: offline does not block onboarding. */
          try {
            fetch('/coach/focus_jump', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ jump })
            }).catch(() => { });
          } catch (e) { }
        }
        localStorage.setItem('js.onboarded', 'true');
        NS.playClickSound(800, 0.05);
        /* The activation goal is the FIRST analyzed jump (13-UX-RESEARCH
           §1.1). Sending a newcomer to "Today" with an empty plan would be a dead
           end: the main action is in another tab. Only new users see onboarding,
           so it always goes to "Record". */
        NS.go('record');
      };
    }

    // Printable Coach Report Sheet
    const btnExportReport = document.getElementById('btn-export-coach-pdf');
    const sheetReport = document.getElementById('sheet-coach-report');
    const btnCloseReport = document.getElementById('btn-close-coach-report');
    const btnPrintReport = document.getElementById('btn-print-report-now');
    const btnShareReport = document.getElementById('btn-share-report');

    if (btnExportReport && sheetReport) {
      btnExportReport.onclick = () => {
        sheetReport.hidden = false;
        sheetReport.style.display = 'flex';
        NS.playClickSound(650, 0.04);
      };
    }
    if (btnCloseReport && sheetReport) {
      btnCloseReport.onclick = () => {
        sheetReport.hidden = true;
        sheetReport.style.display = 'none';
      };
    }
    if (btnPrintReport) {
      btnPrintReport.onclick = () => {
        /* window.print() printed the WHOLE page: tab bar, player, cards —
           not the report. A body class keeps only the report sheet visible. */
        document.body.classList.add('printing-report');
        const done = () => document.body.classList.remove('printing-report');
        window.addEventListener('afterprint', done, { once: true });
        setTimeout(done, 60000);
        window.print();
      };
    }
    if (btnShareReport) {
      /* The share text carries no personal name (no athlete profile is collected),
         and "copied to clipboard" is shown only after an actual copy. */
      btnShareReport.onclick = () => {
        const body = document.getElementById('report-body');
        const text = 'JumpSight report' + '\n' + (body ? body.innerText.trim() : '');
        if (navigator.share) {
          navigator.share({ title: 'JumpSight Report', text }).catch(() => {});
        } else if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text)
            .then(() => NS.notice('Report text copied — paste it into a message to the coach.'))
            .catch(() => NS.notice('Could not copy — print the report or take a screenshot.'));
        } else {
          NS.notice('Sharing is not available here — print the report or take a screenshot.');
        }
      };
    }

    // Parent Dashboard Print Handler
    /* The same report sheet as in Progress opens — a table of attempts from the journal;
       printing the whole profile screen would include input fields, codes and toggles. */
    const btnPrintParent = document.getElementById('btn-print-parent-report');
    if (btnPrintParent && sheetReport) {
      btnPrintParent.onclick = () => {
        sheetReport.hidden = false;
        sheetReport.style.display = 'flex';
        NS.playClickSound(650, 0.04);
      };
    }

    // Service Worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => { });
    }
  }



  /* Choosing the working jump from "Training" is directly the second onboarding step:
     the intro "Did I complete the jump?" is redundant here, the person is already in the app. */
  function openJumpPicker() {
    NS.go('onboard');
    const intro = document.getElementById('onboard-step-intro');
    const pick = document.getElementById('onboard-step-pick');
    if (intro && pick) { intro.hidden = true; pick.hidden = false; }
  }

  /* KEYBOARD AND BOTTOM BAR.
     Where the browser shrinks the page for the keyboard (Chrome Android with
     interactive-widget=resizes-content, Firefox, Samsung Internet), the bottom
     tab bar rises above the keyboard and covers the field the person is typing in
     (chat "Ask", codes, name). While a text field is focused
     on a touch screen, the bar hides; it returns on blur. */
  (function keyboardAwareTabs() {
    const isText = el => !!el && (el.tagName === 'TEXTAREA' || el.isContentEditable
      || (el.tagName === 'INPUT' && !/^(checkbox|radio|range|button|submit|reset|file|color|image|hidden)$/i.test(el.type || '')));
    document.addEventListener('focusin', e => { if (isText(e.target)) document.documentElement.classList.add('kb-open'); });
    document.addEventListener('focusout', () => setTimeout(() => {
      if (!isText(document.activeElement)) document.documentElement.classList.remove('kb-open');
    }, 0));
  })();

  window.APP = {
    currentUid: () => NS.ME && NS.ME.uid,
    soundOn: NS.soundOn, openJumpPicker,
    boot: NS.boot, go: NS.go, openAttempt: NS.openAttempt, openJob: NS.openJob, renderAttempt: NS.renderAttempt, handleFileUpload: NS.handleFileUpload, pollJob: NS.pollJob, fetchJobResults: NS.fetchJobResults,
    jumpNameLocal: NS.jumpNameLocal,   // journal and report (coach.js) show names in the same language as the answer screen
    historyJumpName: NS.historyJumpName, // the "Lutz or flip" pair in the journal, goals and filter — the same as on the answer screen
    /* one language for findings and confidence in the journal (coach.js) */
    findings: NS.findings, historyNoFindings: NS.historyNoFindings, confWord: NS.confWord,
    notice: NS.notice,          // confirmation of a saved session on Today (coach.js)
    /* live recording: available for local testing without a camera or cloud */
    liveStart: NS.liveStart, liveStop: NS.liveStop, renderLivePreview: NS.renderLivePreview, renderLiveFeed: NS.renderLiveFeed,
    /* waiting screen: checks /status states without a server */
    prepareWaiting: NS.prepareWaiting, applyJobStatus: NS.applyJobStatus,
    openDrill: NS.openDrill, openDrillBlock: NS.openDrillBlock, setTheme: NS.setTheme, toggleTheme: NS.toggleTheme, playClickSound: NS.playClickSound,
    getActiveAttempt: () => (NS.activeAttempts[NS.currentAttemptIdx] || null),
    ERR_UA: NS.ERR_UA
  };

  Object.assign(NS, {
     bootPart4,
  });
})();
