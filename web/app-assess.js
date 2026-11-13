/* Self-assessment first (guess) and verified-correction flows on the answer screen. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* In the cloud this wakes the GPU while the person picks a video (the server
     limits the rate itself); locally it does nothing */
  function prewarm(live) { try { fetch('/prewarm' + (live === true ? '?live=1' : ''), { method: 'POST', keepalive: true }).catch(() => {}); } catch (_) { } }

  function guessKey() {
    const a = NS.activeAttempts[NS.currentAttemptIdx];
    return 'js.guessed.' + ((a && a.stem) || NS.lastAnswerStem || '');
  }

  /* The working jump from onboarding goes first in the list: in most
     cases it is the one being filmed, so the answer is a single tap. */
  function guessJumpOrder() {
    const code = localStorage.getItem('js.focusJump') || '';
    const map = { A: 'axel', S: 'salchow', T: 'toe_loop', Lo: 'loop',
                  F: 'flip', Lz: 'lutz' };
    const m = code.match(/^[1-4]?(Lz|Lo|[ASFT])$/);
    const first = m ? map[m[1]] : null;
    if (!first) return NS.VC_JUMPS;
    return [...NS.VC_JUMPS].sort((a, b) => (b[0] === first) - (a[0] === first));
  }

  function guessPaint() {
    const jb = document.getElementById('guess-jump-btns');
    const tb = document.getElementById('guess-turn-btns');
    if (jb) jb.innerHTML = guessJumpOrder().map(([k, en]) =>
      `<button class="btn btn--outline g-j" data-k="${k}" style="min-height:42px;padding:0 12px;${
        NS.guessJump === k ? 'border-color:var(--action);color:var(--action);' : ''}">${en}</button>`).join('');
    /* The rotation question appears AFTER the jump is chosen: showing
       ten buttons at once is not "simple and clear". */
    const turnsWrap = document.getElementById('guess-turns-wrap');
    if (turnsWrap) turnsWrap.hidden = !NS.guessJump;
    if (tb) tb.innerHTML = [1, 2, 3, 4].map(n =>
      `<button class="btn btn--outline g-t" data-n="${n}" style="flex:1;min-height:42px;${
        NS.guessTurns === n ? 'border-color:var(--action);color:var(--action)' : ''}">${n}</button>`).join('');
    document.querySelectorAll('.g-j').forEach(b => {
      b.onclick = () => { NS.guessJump = b.getAttribute('data-k'); guessPaint(); };
    });
    document.querySelectorAll('.g-t').forEach(b => {
      b.onclick = () => { NS.guessTurns = parseInt(b.getAttribute('data-n')); guessPaint(); };
    });
  }

  /* One question per analysis, not two. If the person already named the jump
     BEFORE the numbers were shown, a post-reveal "Is this right?" is the same
     question asked twice in a row (and worse: after the answer was seen,
     anchoring kicks in). We show it ONLY to those who skipped the
     self-assessment. */
  function syncFeedbackCards() {
    const raw = localStorage.getItem(guessKey());
    const _cur0 = NS.activeAttempts[NS.currentAttemptIdx] || {};
    const vcDone = !!(_cur0.stem && localStorage.getItem('js.vc.' + _cur0.stem) === '1');
    const answered = !!(raw && raw !== 'skipped') || vcDone;
    const vc = document.getElementById('card-verdict-check');
    /* Optional feedback does not ask to confirm an uncertain name. */
    const _cur = NS.activeAttempts[NS.currentAttemptIdx] || {};
    /* "Is this right?" asks about the ATTEMPT; without an attempt (no jumps found,
       no analyses yet) the answer would go to the stem of the previous analysis. */
    const _noAttempt = !NS.activeAttempts.length || !!_cur.noJump;
    /* coach on a student's analysis: their answer is an expert label */
    const _vd = document.getElementById('vc-desc');
    if (_vd && NS.ME && NS.ME.role === 'coach') _vd.textContent = 'Your answer as a coach is an expert label: it teaches the system to recognise your skaters’ jumps.';
    if (vc) vc.hidden = NS.demoShown || _noAttempt || answered || (!!(_cur.nameUncertain && !_cur.nameDisplay) && !_cur.edgePair);
    const feedback = document.getElementById('verdict-feedback');
    if (feedback) feedback.hidden = !vc || vc.hidden;
  }

  /* LEARNING MOMENT (13-UX-RESEARCH §2.1): after the numbers are shown,
     the person should see whether their sense matched the measurement. Without
     this line the assessment would only collect labels, not train judgment. */
  function guessOutcomeNote() {
    const a = NS.activeAttempts[NS.currentAttemptIdx];
    if (!a || (!NS.guessJump && !NS.guessTurns)) return;
    const raws = [String(a.rawName || ''),
                  ...(a.alts || []).map(x => String(x))]
      .map(x => x.toLowerCase().replace(' ', '_')).filter(Boolean);
    /* lutz/flip pair: if the system honestly says "one or the other", a match
       counts for either of the two names; otherwise the person would be penalized for
       something no one can see from a single camera. */
    const _att = NS.activeAttempts[NS.currentAttemptIdx] || {};
    const nameOk = (NS.guessJump && !(_att.nameUncertain && !_att.nameDisplay))
      ? raws.some(x => x === NS.guessJump) : null;
    const turnsOk = (NS.guessTurns && typeof a.turnsNum === 'number')
      ? NS.guessTurns === a.turnsNum : null;
    const parts = [];
    if (nameOk !== null) parts.push(nameOk);
    if (turnsOk !== null) parts.push(turnsOk);
    if (!parts.length) return;
    const allOk = parts.every(Boolean);
    let box = document.getElementById('guess-outcome');
    if (!box) {
      box = document.createElement('div');
      box.id = 'guess-outcome';
      box.className = 'card card--pad';
      const anchor = document.getElementById('card-guess');
      if (anchor && anchor.parentNode)
        anchor.parentNode.insertBefore(box, anchor);
    }
    box.style.borderColor = allOk ? 'var(--clean)' : 'var(--short)';
    box.style.color = allOk ? 'var(--clean)' : 'var(--short)';
    box.style.fontSize = '14px';
    box.style.fontWeight = '600';
    box.textContent = allOk
      ? (window.TEXT ? window.TEXT.t('guessMatch') : '')
      : (window.TEXT ? window.TEXT.t('guessDiff') : '');
    box.hidden = false;
  }

  function guessRevealNumbers() {
    const card = document.getElementById('card-guess');
    if (card) card.hidden = true;
    guessOutcomeNote();
    syncFeedbackCards();
    document.querySelectorAll('[data-guess-veil]').forEach(el => {
      el.style.visibility = '';
      el.removeAttribute('data-guess-veil');
    });
  }

  /* Hide only the NUMBERS (not the whole page): the video stays visible,
     watching yourself BEFORE the hint is the same structured
     self-assessment the literature recommends. */
  function guessVeilNumbers() {
    /* WHAT TO HIDE IS DECLARED IN THE MARKUP, NOT IN THIS LIST: a hand-kept list
       misses new phase blocks (an AIR TIME card hidden while another line still
       showed "airborne 0.39 s"). The source of truth is the data-veil attribute in
       index.html; the explicit list is a fallback for markup
       without attributes. */
    const marked = document.querySelectorAll('#scr-answer [data-veil]');
    const fallback = [document.getElementById('ans-hero-num'),
                      document.getElementById('ans-verdict-t'),
                      document.getElementById('ans-verdict-s'),
                      ...document.querySelectorAll('#scr-answer .metric-box__v')];
    const targets = marked.length ? [...marked] : fallback;
    targets.forEach(el => {
      if (!el) return;
      /* NOT visibility:hidden. An empty space read as a load failure: the green verdict block showed empty,
         the cards showed only captions. A placeholder of the same size
         is drawn by CSS ([data-guess-veil]::after), so the DOM and value updates
         stay intact. */
      if (!el.getAttribute('data-veil-ph')) {
        el.setAttribute('data-veil-ph',
          el.id === 'ans-verdict-t' ? 'your call first'
                                    : '•••');
      }
      el.style.visibility = '';
      el.setAttribute('data-guess-veil', '1');
    });
  }
  function maybeAskGuess() {
    const card = document.getElementById('card-guess');
    if (!card) return;
    const k = guessKey();
    const stemKnown = k !== 'js.guessed.';
    /* The very first answer is shown WITHOUT a test: the person just
       uploaded a video to LEARN — hiding the numbers and asking them
       the same question would be a dead end. The research on
       judgment (13-UX-RESEARCH §2.1) switches on from the SECOND analysis,
       once the value has been shown. __jsHistN is set by loadLastAnswer
       on page load. */
    const firstEver = !(window.__jsHistN > 0);
    /* The "your assessment first" mode is enabled ONLY by explicit choice.
       Users saw "•••" instead of the name and rotations, and the card with the button
       "show" sat below the fold, and they read this as "nothing
       is displayed". By default numbers are visible immediately; the mode is switched on
       with a toggle on the answer screen (js.guessMode). */
    let guessMode = false;
    try { guessMode = localStorage.getItem('js.guessMode') === '1'; } catch (e) { }
    /* The mode toggle lives in Profile → Settings. */
    document.getElementById('btn-guess-mode')?.remove();
    if (!guessMode || NS.demoShown) {
      card.hidden = true;
      guessRevealNumbers();
      if (NS.demoShown) syncFeedbackCards();
      return;
    }
    /* the assessment card sits above the hidden numbers, as the first block on screen */
    try {
      const scr = document.getElementById('scr-answer');
      const first = scr && scr.querySelector('.card, .hero-num, #ans-attempt-eyebrow');
      if (scr && first && card.parentNode && first.parentNode && card !== first) {
        const host = first.closest('.rz-ans__body > *') || first.closest('#scr-answer > *') || first;
        host.parentNode.insertBefore(card, host);
      }
    } catch (e) { }
    if (firstEver || !stemKnown || localStorage.getItem(k) || !NS.activeAttempts.length
        || (NS.activeAttempts[NS.currentAttemptIdx] || {}).noJump) {
      card.hidden = true;
      syncFeedbackCards();
      return;
    }
    // while we ask for the assessment, there is no post-reveal card on screen
    const vc0 = document.getElementById('card-verdict-check');
    if (vc0) vc0.hidden = true;
    NS.guessJump = null; NS.guessTurns = null;
    const oldNote = document.getElementById('guess-outcome');
    if (oldNote) oldNote.hidden = true;
    guessPaint();
    guessVeilNumbers();
    card.hidden = false;
  }

  async function guessSend() {
    const a = NS.activeAttempts[NS.currentAttemptIdx];
    const stem = (a && a.stem) || NS.lastAnswerStem;
    if (!stem) return;
    try {
      await fetch('/coach/verdict_feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stem, jump: NS.guessJump, turns: NS.guessTurns,
                               source: 'pre_reveal' })
      });
    } catch (e) { /* offline does not block showing the measurement */ }
  }

  function vcPaint() {
    /* When the model was unsure (p < 0.6), its top 2 are highlighted in the confirmation card
       — the answer headline stays decisive, and the person's tap
       becomes a verified label exactly where it is needed
       (measured: in 4 of 14 errors the truth was second). */
    const act = NS.activeAttempts[NS.currentAttemptIdx] || {};
    /* when the bridge honestly says "undetermined" (name_uncertain),
       the confirmation card is ALWAYS needed — that is where the person's tap
       turns uncertainty into a verified label. The condition cannot rely
       only on nameP, which may be absent in such attempts. */
    const hesitant = (act.nameUncertain
                      || (typeof act.nameP === 'number' && act.nameP < 0.6))
      && (act.nameAlts || []).length >= 2;
    const hintIds = hesitant
      ? act.nameAlts.map(n => String(n).toLowerCase().replace(/\s+/g, '_'))
      : [];
    const hintEl = document.getElementById('vc-hint');
    if (hintEl) {
      hintEl.hidden = !hesitant;
      if (hesitant) hintEl.textContent = `The system hesitates: ${act.nameAlts[0]} or ${act.nameAlts[1]}? Your answer helps.`;
    }
    const jb = document.getElementById('vc-jump-btns');
    const tb = document.getElementById('vc-turn-btns');
    if (jb) jb.innerHTML = NS.VC_JUMPS.map(([k, en]) => {
      const sel = NS.vcJump === k ? 'border-color:var(--action);color:var(--action);' : '';
      const hint = !sel && hintIds.includes(k) ? 'border-color:var(--short);' : '';
      return `<button class="btn btn--outline vc-j" data-k="${k}" style="min-height:42px;padding:0 12px;${sel}${hint}">${en}</button>`;
    }).join('');
    if (tb) tb.innerHTML = [1, 2, 3, 4].map(n =>
      `<button class="btn btn--outline vc-t" data-n="${n}" style="flex:1;min-height:42px;${
        NS.vcTurns === n ? 'border-color:var(--action);color:var(--action)' : ''}">${n}</button>`).join('');
    document.querySelectorAll('.vc-j').forEach(b => {
      b.onclick = () => { NS.vcJump = b.getAttribute('data-k'); vcPaint(); };
    });
    document.querySelectorAll('.vc-t').forEach(b => {
      b.onclick = () => { NS.vcTurns = parseInt(b.getAttribute('data-n')); vcPaint(); };
    });
  }

  async function vcSend(correct) {
    const a = NS.activeAttempts[NS.currentAttemptIdx];
    const stem = (a && a.stem) || NS.lastAnswerStem;
    if (!stem) return;
    const body = { stem, correct };
    if (!correct) { body.jump = NS.vcJump; body.turns = NS.vcTurns; }
    const th = document.getElementById('vc-thanks');
    try {
      const r = await fetch('/coach/verdict_feedback', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) });
      const d = await r.json();
      if (th) {
        th.hidden = false;
        th.textContent = d.ok
          ? 'Saved. Thank you — this genuinely helps.'
          : ('Could not save: ' + (d.error || ''));
        th.style.color = d.ok ? 'var(--clean)' : 'var(--bad)';
      }
      if (d.ok) {
        try { localStorage.setItem('js.vc.' + stem, '1'); } catch (_) { }
        /* The reply from the quick row: thanks and the question appear right where the person
           tapped (the thanks form is collapsed at the bottom of the page). */
        const quick = document.getElementById('vc-quick');
        const fromQuick = !!(quick && !quick.hidden);
        if (fromQuick) {
          document.getElementById('verdict-feedback')?.removeAttribute('open');
          const qt = document.getElementById('vc-quick-t');
          if (qt) qt.textContent = 'Saved — thank you!';
          document.getElementById('vc-quick-btns')?.replaceChildren();
        }
        /* Consent can be given only at upload and only together with the claim, so a
           label without it would be lost: the owner gets one explicit question after the label;
           nothing is pre-checked. */
        const job = NS.lastJobId, jc = NS.JOB_CONSENT.get(job);
        document.querySelectorAll('.rz-check__consent').forEach(x => x.remove());
        const needConsent = !!(jc && jc.mine && !jc.consent);
        if (fromQuick && !needConsent) setTimeout(() => quick.setAttribute('hidden', ''), 2500);
        if (!fromQuick) quick?.setAttribute('hidden', '');
        if ((th || fromQuick) && needConsent) {
          const box = NS.trainConsentBox(job, jc);
          if (fromQuick) quick.append(box); else th.after(box);
        }
        const fix = document.getElementById('vc-fix');
        if (fix) fix.hidden = true;
        /* answer accepted — the buttons are not broken, just cleared: hide them, keep the thanks */
        ['btn-vc-yes', 'btn-vc-no', 'vc-pair-btns', 'btn-vc-other'].forEach(id => {
          const b = document.getElementById(id); if (b) b.hidden = true;
        });
      }
    } catch (e) {
      if (th) { th.hidden = false; th.style.color = 'var(--bad)';
        th.textContent = 'The server did not respond.'; }
    }
  }

  function bootPart3() {
    /* ── Human confirmation of the verdict ──
       The system shows an answer even at low confidence, so
       the final word belongs to the person. Their correction is the only VERIFIED
       label in the target domain (YouTube titles do not qualify: there
       the most common error is exactly the same flip/lutz as ours). */
    NS.VC_JUMPS = [['axel', 'Axel'], ['salchow', 'Salchow'],
                      ['toe_loop', 'Toe loop'], ['loop', 'Loop'],
                      ['flip', 'Flip'], ['lutz', 'Lutz']];
    NS.vcJump = null, NS.vcTurns = null;
    /* Lutz/flip pair: one tap = one verified label. */
    document.getElementById('vc-pair-btns')?.addEventListener('click', e => {
      const button = e.target.closest('.btn-pair-choice');
      if (!button) return;
      NS.vcJump = button.dataset.choice.toLowerCase();
      NS.vcTurns = null;
      document.querySelectorAll('#vc-pair-btns .btn-pair-choice').forEach(b => b.classList.toggle('is-on', b === button));
      vcSend(false);
    });
    document.getElementById('btn-vc-other')?.addEventListener('click', () => {
      const fix = document.getElementById('vc-fix');
      if (fix) { fix.hidden = !fix.hidden; if (!fix.hidden) { vcPaint(); fix.scrollIntoView({ block: 'center', behavior: 'auto' }); } }
    });

    /* ── ASSESSMENT FIRST, THEN NUMBERS (13-UX-RESEARCH §2.1/§2.3) ──────────
       Hides the numeric cards until the person names their own answer or
       explicitly opts out. Self-direction is intentional here: the literature says
       that feedback the learner controls teaches better than
       imposed feedback, so "just show the numbers" is an equal button,
       not a penalty. Shown ONCE per analysis (key in localStorage
       by stem): reviewing one's own analysis again must not
       turn into a test again. */
    NS.guessJump = null, NS.guessTurns = null;

    /* One tap reveals the WHOLE measurement. Nothing is removed: everything on the first
       screen is here. After expanding, the button
       becomes "hide" so the action can be undone: control
       over display must stay with the learner (PMID 42413171). */
    /* On phones, measurements are not hidden behind a button; they are
       the answer. The function serves the "assessment first" mode, which after
       showing the numbers calls it; it only lifts the veil. */
    window.__jsRevealDetail = function () { return true; };

    window.__jsAskGuess = maybeAskGuess;

    document.addEventListener('click', (ev) => {
      const rev = ev.target.closest && ev.target.closest('#btn-guess-reveal');
      const skip = ev.target.closest && ev.target.closest('#btn-guess-skip');
      if (!rev && !skip) return;
      const k = guessKey();
      if (rev && (NS.guessJump || NS.guessTurns)) {
        guessSend();
        localStorage.setItem(k, JSON.stringify({ jump: NS.guessJump, turns: NS.guessTurns }));
        guessOutcomeNote();
      } else {
        localStorage.setItem(k, 'skipped');
      }
      guessRevealNumbers();
      /* "Show measurement" in the assessment card and the expand button under the video are
         the same action from the user's view, so both must reveal the cards together. */
      try { if (window.__jsRevealDetail) window.__jsRevealDetail(true); } catch (e) { }
    });
  }

  Object.assign(NS, {
     prewarm, vcPaint, vcSend, bootPart3,
  });
})();
