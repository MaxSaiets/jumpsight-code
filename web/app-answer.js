/* Answer screen: renders one analysed attempt (numbers, phases, errors, video). */
(function () {
  'use strict';
  const NS = window.JS.app;
  function renderAttempt(idx) {
    /* Demo data is shown ONLY while there is no real analysis yet.
       A real analysis with zero jumps is an honest empty state, not a demo. */
    const list = NS.activeAttempts.length ? NS.activeAttempts
      : [NS.realResults ? { num: '—',
          name: 'No jumps found', verdictClass: 'none',
          verdictTitle: 'No jump found in this video',
          /* 'Try another fragment' does not say WHAT to change. The reasons
             are taken from the filming requirements on the recording screen: from the side, the whole jump
             in frame, 60 fps if available. Measured on the corpus: clips with no
             attempt are either a skater far away or partly out of frame, or filming
             from above-behind, where the bottom of the frame does not leave. */
          verdictSub: 'Most common causes: the skater is far away or partly out of frame; filmed from above or behind; under 30 fps.',
          airTime: '—', height: '—', errors: null, hasDisambig: false } : NS.emptyAttempt()];
    NS.currentAttemptIdx = idx % list.length;
    const feedback = document.getElementById('verdict-feedback');
    if (feedback) feedback.open = false;
    /* the '1 / N' counter lived only in rebuildPills: arrows changed the attempt but not the number */
    { const _pos = document.getElementById('ans-att-pos'); if (_pos) _pos.textContent = `${NS.currentAttemptIdx + 1} / ${Math.max(1, list.length)}`; }
    const a = list[NS.currentAttemptIdx];
    /* the 'no jumps found' placeholder is not an attempt: no revolutions, errors,
       explanation, or 'Is this right?' (declared here because it is needed everywhere below) */
    const noJumpsFound = a.name === 'No jumps found';
    NS.playClickSound(640, 0.03);
    (function demoBanner() {
      const scr = document.getElementById('scr-answer');
      if (!scr) return;
      let b = document.getElementById('ans-demo-banner');
      if (!b) {
        b = document.createElement('p');
        b.id = 'ans-demo-banner';
        b.className = 'rz-note rz-demo-banner';
        b.setAttribute('role', 'note');
        const host = scr.querySelector('.rz-ans__body') || scr;
        host.prepend(b);
      }
      b.textContent = 'This is a sample — a real analysis of someone else’s video. Film your own jump to get yours.';
      b.hidden = !NS.demoShown;
    })();

    // Update Attempt Selector Pills
    document.querySelectorAll('.attempt-pill').forEach(pill => {
      const pIdx = parseInt(pill.getAttribute('data-att') || 0);
      if (pIdx === NS.currentAttemptIdx) {
        pill.classList.add('is-on');
      } else {
        pill.classList.remove('is-on');
      }
    });

    const eyeEl = document.getElementById('ans-attempt-eyebrow');
    /* Confidence in the name is project invariant No. 2: the JSON always has it, while the screen
       hid it. Lutz vs Flip from one angle is by principle never high. */
    const nameConfUA = { low: 'LOW', medium: 'MEDIUM', high: 'HIGH' };
    /* The caption is kept short: 'ATTEMPT 1/3 · AXEL · NAME CONFIDENCE MEDIUM' would repeat the position already
       shown as '1 / 3' and use the unexplained word `confidence`. The name confidence itself is
       NOT removed: project invariant No. 2 requires showing it. It sits under the
       measurement disclosure together with the other details. */
    /* SAY WHAT EXACTLY IS NOT DETERMINED (seen on a live
       screen). Here stood simply `a.name`, and for an uncertain name that
       is 'Not determined', and the words ended up just above the big number
       of revolutions. It read as 'the number is unknown', although the number is known and
       the NAME is unknown. One noun removes all the confusion. */
    /* When the name IS present, it stands in the verdict header six centimeters
       above, so do not duplicate it here ('LUTZ' and below it 'Double
       Lutz'). The line remains only for an honest 'not determined'. */
    if (eyeEl) {
      const _unres = a.nameUncertain && !a.nameDisplay;
      eyeEl.textContent = _unres ? 'JUMP NAME — NOT RESOLVED' : '';
      eyeEl.hidden = !_unres;
    }
    let confEl = document.getElementById('ans-name-conf');
    if (!confEl && eyeEl) {
      confEl = document.createElement('div');
      confEl.id = 'ans-name-conf';
      confEl.className = 'measurement-confidence';
      confEl.classList.add('rz-name-note');
      eyeEl.insertAdjacentElement('afterend', confEl);
    }
    if (confEl) {
      /* 'MEDIUM CONFIDENCE' next to the name and 'count confidence: low' under the number
         are two DIFFERENT confidences (in the jump name and in the revolution count). Side by side
         without a label they read as the system contradicting itself. */
      /* 'name confidence: medium' is protocol language. A person
         understands better: confident / probable / uncertain (PRODUCT.md §3). */
      const CONF_WORD = { high: 'name — confident',
                          medium: 'name — likely',
                          low: 'name — possible' };
      /* name not determined: the line above already says so, a badge would be a second time */
      confEl.textContent = (a.nameConf && !(a.nameUncertain && !a.nameDisplay)) ? (CONF_WORD[a.nameConf] || '') : '';
      confEl.hidden = !confEl.textContent;
    }
    /* The prior marker of the working jump: when the name is ordered by it,
       it must be visible on screen, not only in the JSON (invariant 2). */
    let noteEl = document.getElementById('ans-name-note');
    if (!noteEl && eyeEl) {
      noteEl = document.createElement('div');
      noteEl.id = 'ans-name-note';
      noteEl.className = 'rz-name-note';
      eyeEl.insertAdjacentElement('afterend', noteEl);
    }
    if (noteEl) {
      const _note = (a.nameUncertain && !a.nameDisplay) ? '' : (a.nameNote || '');
      noteEl.textContent = _note;
      noteEl.style.display = _note ? 'block' : 'none';
    }
    
    const heroNum = document.getElementById('ans-hero-num');
    // Shown at once, so a quick attempt switch cannot leave a stale count.
    if (heroNum) heroNum.textContent = a.num || '—';
    const heroUnit = heroNum?.parentElement?.querySelector('.rz-revs__lbl');
    if (heroUnit) {
      heroUnit.removeAttribute('data-t');
      heroUnit.textContent = a.heroUnit || 'rotations';
    }
    /* REVOLUTIONS are the main answer of the product. When they are missing, the reason stands
       as the FIRST line under the number, not lower in the card, otherwise the eye
       catches on 'flight 0.52 s' and reads it as the answer. */
    let heroWhy = document.getElementById('ans-hero-why');
    if (!heroWhy && heroNum) {
      heroWhy = document.createElement('div');
      heroWhy.id = 'ans-hero-why';
      /* Confidence stays next to the count regardless of whether details are expanded. */
      heroWhy.className = 'measurement-confidence';
      /* this node is a neighbor of the huge number and the non-breaking caption
         REVOLUTIONS in a flex row, and at 430 px 'count confidence: low' overlapped
         the caption. flex-basis:100% gives it its own line. */
      
      heroNum.insertAdjacentElement('afterend', heroWhy);
    }
    /* Under the dash, two words, not a third sentence about the same thing: the reason is already
       said by the subtitle (rot_reason from the server), and the 'Not measured' card appears only
       when there is no concrete reason (seen on a phone: three
       explanations of one missing quantity). */
    if (heroWhy) heroWhy.textContent = a.heroWhy ||
      ((a.num === '—' && NS.realResults && !a.noJump && !noJumpsFound && a.name !== 'No analyses yet')
        ? 'not measured'
        : '');
    /* No jump means no revolutions either: the block '— revolutions' under 'No jump found in the video'
       read as a broken number (seen on a phone). */
    /* When the subtitle already says 'revolutions not measured: <reason>', the block
       '— revolutions · not measured' under it is the same thing a third time (a clip with a
       fall). The number remains only where there is something to show. */
    const revsBox = heroNum && heroNum.closest('.rz-revs');
    if (revsBox) revsBox.hidden = noJumpsFound || a.name === 'No analyses yet'
      || (a.num === '—' && !!a.rotReason && NS.realResults);

    /* THE MAIN VERDICT: ONE thing, the hardest on the ISU scale, said by
       an external focus. The text comes from isu_rank.js; here only the placement.
       If the module did not load, the line is NOT invented: better empty
       than an invented tip (same principle as the 78/100 fallbacks). */
    const oneThing = document.getElementById('ans-one-thing');
    if (oneThing) {
      const R = window.ISU_RANK;
      /* Demo state and 'no jumps found' get no verdict about
         execution: there is no attempt to talk about. */
      const isReal = NS.realResults && a.num !== undefined
        && a.name !== 'No analyses yet'
        && a.name !== 'No jumps found'
        && !a.noJump && !a.fragment;
      const foundErrors = Array.isArray(a.errors) ? a.errors : [];
      const checkedErrors = Number.isFinite(a.errorsClean) && a.errorsClean > 0;
      const uncertainErrors = Array.isArray(a.errorsUncertain) && a.errorsUncertain.length > 0;
      /* a LOW-confidence signal does not become the 'main' finding; it lives in the
         error list as 'Possibly: …' with a jump to the moment in the video.
         'Main' speaks only about findings of medium and high confidence. */
      const sureErrors = foundErrors.filter(code => ['medium', 'high'].includes((a.errorsConf || {})[code]));
      oneThing.textContent = (R && isReal && sureErrors.length) ? R.verdictSentence(sureErrors) : '';
      const otCard = document.getElementById('card-one-thing');
      /* When errors are not assessed, the 'Main' card only
         repeated 'not measured' from the error card below. It appears only when
         it has something to say; the absence of an assessment is shown honestly in the error card. */
      /* and when no errors are found, the error card already says 'clean'
         with evidence (how many signs were checked); two cards in a row about the
         same thing are noise. 'Main' stays for a finding. */
      const nothingToSay = !sureErrors.length;
      if (otCard) otCard.hidden = !(R && isReal) || nothingToSay;
      /* VERDICT CHIP: color and word on the verdict card, not on the jump name
         (a red name read as an error in the name). */
      if (otCard) {
        let chip = document.getElementById('ans-verdict-chip');
        if (!chip) {
          chip = document.createElement('div'); chip.id = 'ans-verdict-chip';
          const eb = otCard.querySelector('.eyebrow, .rz-eyebrow');
          if (eb) eb.insertAdjacentElement('afterend', chip); else otCard.prepend(chip);
        }
        const errs = sureErrors;
        const cls = errs.length ? 'bad' : (checkedErrors && !uncertainErrors ? 'clean' : 'short');
        chip.className = 'verdict-chip verdict-chip--' + cls;
        chip.textContent = errs.length
          ? errs.slice(0, 2).map(e => (NS.ERR_UA[e] ? NS.ERR_UA[e][0] : e)
            + (!['medium', 'high'].includes((a.errorsConf || {})[e])
              ? ' (low confidence)' : '')).join(' · ')
          : (!checkedErrors ? 'Errors not assessed'
            : uncertainErrors ? 'Errors partially assessed'
            : 'No errors in checked features');
        /* one display. The sentence already names the error; the chip was a second one */
        chip.hidden = true;
      }
    }

    /* EXPLANATION OF THESE VERY NUMBERS, under 'what does this mean?'. The text depends on
       what is on screen: whole count, decimal revolutions or a dash, and
       whether the name is a pair. None of this is invented: everything is about how the
       engine got what is shown. */
    const expl = document.getElementById('ans-rotation-explainer');
    if (expl) {
      const parts = [];
      const isReal0 = NS.realResults && !a.noJump && !noJumpsFound && a.name !== 'No analyses yet';
      if (isReal0 && a.countEstimated) {
        parts.push('The big number is an estimated rotation count (the way judges count). It is marked ≈ because a direct rotation measurement is not confirmed in these frames. The estimate source and confidence are shown beside the result.');
      } else if (isReal0 && typeof a.turnsNum === 'number') {
        parts.push('The big number is the rotation count, the way judges count, from the available measurements; its source and confidence are shown beside it. It is not the number of full rotations in the air or a judging verdict. A decimal in-flight rotation measurement is shown separately only when it is precise enough.');
      } else if (isReal0 && a.num !== '—') {
        parts.push('This is the measured in-flight rotation — from take-off to landing. The rest of the turn happens on take-off and check-out, so the judging count can be higher than this number.');
      } else if (isReal0) {
        parts.push('There is no number because none of the independent rotation counters passed its own check on this footage — the reason is written above.');
      }
      if (isReal0) parts.push('“Confidence” is how well the measurement channels agreed with each other. The jump name comes from the entry and take-off; the Lutz-vs-Flip edge cannot be seen from a single angle, so its confidence is never high.');
      /* to the question 'did it complete the rotation?' an honest
         answer to the request, not a permanent 'not measured' line. */
      if (isReal0) parts.push('ISU under-rotation (q, <) is the blade angle at the moment of landing. A single 30–60 fps video does not show it reliably, so we do not issue a separate “rotated / under-rotated” call. The judging count and in-flight rotation are the closest honest measurements.');
      expl.innerHTML = parts.map(t => `<p>${t}</p>`).join('')
        + `<button type="button" class="quiet-link" id="btn-isu-under">ISU rules on under-rotation (q, <) →</button>`;
      expl.hidden = true;
      const tb = document.getElementById('btn-verdict-term');
      if (tb) { tb.hidden = !parts.length; tb.setAttribute('aria-expanded', 'false'); }
      const isu = document.getElementById('btn-isu-under');
      if (isu) isu.onclick = () => { if (window.COACH) window.COACH.openTermSheet('under'); };
    }

    const verdictBox = document.getElementById('ans-verdict-box');
    if (verdictBox) verdictBox.className = `verdict-banner scorecard__name verdict-banner--${a.verdictClass || 'short'}`;
    
    const vTitle = document.getElementById('ans-verdict-t');
    if (vTitle) vTitle.textContent = a.verdictTitle || 'No ISU call issued';
    
    const vSub = document.getElementById('ans-verdict-s');
    if (vSub) vSub.textContent = a.verdictSub || '';

    /* The 3D build starts only by the button, with no background computation on entry. */

    /* A dash with a unit ('— s', '— cm') reads as a broken number.
       The unit goes out together with the number. */
    const _unitOf = el => el && el.parentElement && el.parentElement.querySelector('.metric-box__unit');
    const airEl = document.getElementById('ans-air-time');
    if (airEl) { airEl.textContent = a.airTime || '—'; const u = _unitOf(airEl); if (u) u.hidden = !a.airTime || a.airTime === '—'; }

    const hEl = document.getElementById('ans-height');
    if (hEl) { hEl.textContent = a.height || '—'; const u = _unitOf(hEl); if (u) u.hidden = !a.height || a.height === '—'; }
    /* ±68% bands: only when the number is shown and the band came from the engine */
    const airBand = document.getElementById('ans-air-band');
    if (airBand) airBand.textContent = (typeof a.airHalf === 'number' && a.airTime && a.airTime !== '—')
      ? `±${a.airHalf.toFixed(2)}` : '';
    const hBand = document.getElementById('ans-height-band');
    if (hBand) hBand.textContent = (typeof a.heightHalfCm === 'number' && a.height && a.height !== '—')
      ? `±${Math.max(1, Math.round(a.heightHalfCm))}` : '';
    /* LAST TIME: under time and height, the same number from the
       previous attempt of THE SAME jump from the log (not from this video).
       These are measured quantities, not an estimate; without a previous attempt, nothing. */
    (async function prevSameJump() {
      const airPrev = document.getElementById('ans-air-prev');
      const hPrev = document.getElementById('ans-height-prev');
      if (!airPrev || !hPrev) return;
      airPrev.textContent = ''; hPrev.textContent = '';
      if (!NS.realResults || a.noJump || noJumpsFound || !a.rawName || a.nameUncertain) return;
      const myJob = NS.lastJobId;
      if (!myJob) return;
      let hist = [];
      try { const h = await window.__jsHistory(); hist = h.ok ? h.data : []; } catch (_) { }
      if (!Array.isArray(hist)) hist = [];
      /* We compare only against OWN log: a coach viewing a student's analysis,
         or a person with a foreign ?job= link, must not see 'last time'
         from their own jumps. The 'own' flag: this analysis is in the log
         (the log cache of 3 s may lag behind a just-finished one, so one
         repeated request). */
      if (!hist.some(r => r && r.job === myJob)) {
        try { const h = await window.__jsHistory(true); hist = h.ok && Array.isArray(h.data) ? h.data : []; } catch (_) { hist = []; }
        if (!hist.some(r => r && r.job === myJob)) return;
      }
      const same = hist.filter(r => r && r.jump && String(r.jump).toLowerCase().replace(/\s+/g, '_') === a.rawName
        && r.job && r.job !== myJob && !(r.name_uncertain === true || r.name_uncertain === 'True'));
      const prev = same.find(r => Number.isFinite(Number(r.air_time_s)) || Number.isFinite(Number(r.height_m)));
      if (!prev) return;
      /* the attempt could change while the log was loading */
      if (NS.activeAttempts[NS.currentAttemptIdx] !== a) return;
      /* No date: on a 170 px tile '(7 Sep)' wrapped onto a second line,
         and the date of the previous attempt is in the log anyway. We do not compute the difference:
         one frame at 30 fps = 0.03 s, '+0.03 s' would read as progress. */
      const pa = Number(prev.air_time_s), ph = Number(prev.height_m);
      if (Number.isFinite(pa) && pa > 0 && a.airTime && a.airTime !== '—')
        airPrev.textContent = `last time ${pa.toFixed(2)} s`;
      if (Number.isFinite(ph) && ph > 0 && a.height && a.height !== '—')
        hPrev.textContent = `last time ${(ph * 100).toFixed(0)} cm`;
    })();
    /* The 'revolutions in flight' and 'rotation speed' tiles: only when the engine
       measured them (a decimal number is a measurement when the band is narrower than
       half a revolution). An empty tile is not shown. The time and height tiles
       always stay: a dash there is the honest answer 'not measured'. */
    const tileRev = document.getElementById('tile-rev');
    const revEl = document.getElementById('ans-rev');
    const revBand = document.getElementById('ans-rev-band');
    if (tileRev && revEl) {
      const has = typeof a.revFlight === 'number';
      tileRev.hidden = !has;
      revEl.textContent = has ? a.revFlight.toFixed(2) : '—';
      if (revBand) revBand.textContent = (has && typeof a.revHalf === 'number') ? `±${a.revHalf.toFixed(2)}` : '';
    }
    const tileRate = document.getElementById('tile-rate');
    const rateV = document.getElementById('ans-rate-v');
    const rateS = document.getElementById('ans-rate-s');
    const rateUnit = document.getElementById('ans-rate-u');
    if (tileRate && rateV) {
      const has = typeof a.rateDeg === 'number';
      tileRate.hidden = !has;
      /* '1098 °/s' tells a person nothing; the headline number is in revolutions
         per second (same measurement recomputed), degrees go in the caption */
      /* the band in a small caption, like in the time tile: a large monospace
         '3.0 ±0.2' pushed the half tile wider at 320 px (compare gate) */
      rateV.textContent = has ? (a.rateDeg / 360).toFixed(1) : '—';
      if (rateUnit) rateUnit.textContent = (has && typeof a.rateBandRps === 'number' ? `±${a.rateBandRps.toFixed(1)} ` : '')
        + 'rotations/s';
      if (rateS) rateS.textContent = has ? (a.rateNote || '') : '';
    }
    /* an odd last tile: full width, with no empty cell beside it */
    (function squareTiles() {
      const tiles = [...document.querySelectorAll('#ans-metrics .rz-metric')].filter(t => !t.hidden);
      tiles.forEach(t => t.classList.remove('is-wide'));
      if (tiles.length % 2 === 1) tiles[tiles.length - 1].classList.add('is-wide');
    })();

    const lblTakeoff = document.getElementById('lbl-ph-takeoff');
    if (lblTakeoff) {
      lblTakeoff.textContent = a.takeoff != null && !a.noJump
        ? `takeoff at ${a.timeEstimated ? '≈ ' : ''}${a.takeoff} s`
        : 'takeoff —';
    }

    const lblFlight = document.getElementById('lbl-ph-flight');
    /* The airtime number stood here, in the 'AIR TIME' tile and in
       the caption next to it, three times on one screen. The phase row is a clickable
       marker on the video; the number lives in the tile. */
    if (lblFlight) lblFlight.textContent = 'flight';

    const lblLanding = document.getElementById('lbl-ph-landing');
    if (lblLanding) {
      lblLanding.textContent = a.landing != null
        ? `landing at ${a.timeEstimated ? '≈ ' : ''}${a.landing} s`
        : 'landing —';
    }

    /* The phase strip under the video takes its geometry and click targets
       from MEASURED takeoff/landing (a fixed split would draw a picture nobody measured:
       on a 7.4 s clip with a 0.52 s flight the true share of flight is 7%). When there
       is no time, the strip hides and does not invent a proportion. */
    /* switching attempts goes straight to its jump, not to the start of the recording */
    (function seekToAttempt() {
      const vv = document.getElementById('ans-video');
      const t = a.takeoff != null ? parseFloat(a.takeoff) : null;
      const l = a.landing != null ? parseFloat(a.landing) : null;
      NS.ANS_WIN = (t != null && l != null && l > t) ? { t0: Math.max(0, t - 1.0), t1: l + 1.0 } : null;
      NS.ANS_PH = (t != null && l != null && l > t) ? { t, l } : null;
      NS.scrubAll = false;
      if (window.__jsScrubSync) window.__jsScrubSync();
      /* comparison only for an attempt with measured take-off and landing */
      const cmpBtn = document.getElementById('btn-compare');
      if (cmpBtn) cmpBtn.hidden = !NS.ANS_PH || !!a.noJump;
      NS.syncFollowFor(a.noJump ? null : a);
      const watch = document.getElementById('btn-watch-jump');
      if (watch) {
        watch.hidden = !vv || !NS.ANS_WIN || !!a.noJump;
        const win = NS.ANS_WIN;
        watch.onclick = () => {
          if (!vv || !win) return;
          try { vv.currentTime = win.t0; const p = vv.play(); if (p && p.catch) p.catch(() => {}); } catch (_) { }
          document.getElementById('ans-vid-stage')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
      }
      if (!vv || !NS.ANS_WIN) return;
      const seek = () => { try { vv.currentTime = NS.ANS_WIN.t0; } catch (_) { } };
      if (vv.readyState >= 1) seek(); else vv.addEventListener('loadedmetadata', seek, { once: true });
    })();

    (function syncPhaseStrip() {
      const strip = document.getElementById('phase-strip');
      const segT = document.getElementById('ph-takeoff');
      const segF = document.getElementById('ph-flight');
      const segL = document.getElementById('ph-landing');
      const vv = document.getElementById('ans-video');
      if (!segT || !segF || !segL) return;
      const t = a.takeoff != null ? parseFloat(a.takeoff) : null;
      const l = a.landing != null ? parseFloat(a.landing) : null;
      const phaseButtons = [lblTakeoff, lblFlight, lblLanding].filter(Boolean);
      const clearSeek = () => phaseButtons.forEach(button => { button.onclick = null; button.disabled = true; });
      clearSeek();
      const phaseNote = document.getElementById('ans-phase-seek-note');
      const hasTimes = Number.isFinite(t) && Number.isFinite(l) && t >= 0 && l > t;
      if (phaseNote) {
        phaseNote.hidden = hasTimes;
        phaseNote.textContent = 'Phase navigation unavailable: takeoff and landing times were not determined.';
      }
      const apply = () => {
        const dur = vv && !vv.error && vv.duration && isFinite(vv.duration) ? vv.duration : null;
        const ok = hasTimes && dur && l <= dur;
        clearSeek();
        const holder = strip || segT.parentElement;
        if (!ok) {
          if (holder) holder.style.visibility = 'hidden';
          if (phaseNote && hasTimes && dur && l > dur) {
            phaseNote.hidden = false;
            phaseNote.textContent = 'The phase times do not match the stored video — navigation is unavailable.';
          }
          return;
        }
        if (phaseNote) phaseNote.hidden = true;
        if (holder) holder.style.visibility = '';
        const pct = x => `${Math.max(0, Math.min(100, x / dur * 100))}%`;
        segT.style.width = pct(t);
        segF.style.width = pct(l - t);
        segL.style.width = pct(dur - l);
        const seek = sec => () => { if (vv) { vv.currentTime = sec; vv.play().catch(() => {}); } };
        [[lblTakeoff,t],[lblFlight,t],[lblLanding,l]].forEach(([button,sec]) => {
          if (button) { button.disabled = false; button.onclick = seek(sec); }
        });
      };
      apply();
      if (vv) {
        // One active handler: the previous attempt does not control the new media.
        if (vv._phaseSeekMetadata) vv.removeEventListener('loadedmetadata', vv._phaseSeekMetadata);
        if (vv._phaseSeekError) vv.removeEventListener('error', vv._phaseSeekError);
        vv._phaseSeekMetadata = apply;
        vv._phaseSeekError = () => {
          clearSeek();
          if (strip) strip.style.visibility = 'hidden';
          if (phaseNote) {
            phaseNote.hidden = false;
            phaseNote.textContent = 'Phase navigation unavailable: the video did not load.';
          }
        };
        vv.addEventListener('loadedmetadata', apply);
        vv.addEventListener('error', vv._phaseSeekError);
      }
    })();

    /* OVERVIEW OF ALL ATTEMPTS in the video, for a coach who wants to see the series
       and not page through a pager. Only when there is more than one attempt; each row is
       the measured fields of the same attempt (take-off time, name, count, main
       error), and a tap opens it. Fragments without a jump (no_jump) are not
       shown in the carousel; here they are described by a number. */
    (function renderAttemptsList() {
      const card = document.getElementById('card-attempts');
      const rows = document.getElementById('attempts-rows');
      const meta = document.getElementById('attempts-meta');
      const foot = document.getElementById('attempts-foot');
      if (!card || !rows) return;
      const many = NS.activeAttempts.length > 1;
      card.setAttribute('data-has-list', many ? '1' : '0');
      if (!many) { card.hidden = true; rows.innerHTML = ''; return; }
      const clock = t => { const n = Math.max(0, Math.round(parseFloat(t) || 0)); return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`; };
      rows.innerHTML = NS.activeAttempts.map((x, i) => {
        const f = NS.findings(x.errors, x.errorsConf);
        const status = x.noJump ? 'not confirmed'
          : x.fragment ? 'not a jump'
          : f.text || (x.errorsClean ? 'no errors found' : '');
        const cls = (x.noJump || x.fragment) ? '' : (f.cls || (x.errorsClean ? 'is-done' : ''));
        return `<div class="rz-log-row${i === NS.currentAttemptIdx ? ' is-current' : ''}" role="button" tabindex="0" data-att="${i}">
          <span class="rz-log-row__ic ${cls}">${i + 1}</span>
          <div class="rz-log-row__main">
            <div class="rz-log-row__name">${x.name || '—'}</div>
            <div class="rz-log-row__sub">${[x.takeoff != null ? clock(x.takeoff) : '', status].filter(Boolean).join(' · ')}</div>
          </div>
          <div class="rz-log-row__num"><div class="rz-log-row__rev">${x.num || '—'}</div></div>
        </div>`;
      }).join('');
      rows.querySelectorAll('[data-att]').forEach(r => {
        const open = () => { renderAttempt(parseInt(r.getAttribute('data-att'), 10)); window.scrollTo({ top: 0, behavior: 'smooth' }); };
        r.onclick = open;
        r.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } };
      });
      /* Order by confidence (bridge rank), not by time; on a clip
         with 6 attempts the time went 0:02, 0:22, 0:25, 0:19… and read as an error */
      if (meta) meta.textContent = `${NS.activeAttempts.length} attempts · most certain first`;
      const skipped = window.__jsSkippedFragments || 0;
      if (foot) {
        foot.hidden = !skipped;
        foot.textContent = skipped ? ((skipped === 1 ? 'One more was a short hop or an entry fragment, not a jump; it is not analysed.' : `${skipped} more were short hops or entry fragments, not jumps; they are not analysed.`)) : '';
      }
      card.hidden = false;
    })();

    const nmCard = document.getElementById('card-not-measured');
    const nmBody = document.getElementById('ans-not-measured-body');
    if (nmCard && nmBody) {
      /* The card exists ONLY for truly missing main numbers: no permanent 'EDGE AT TAKE-OFF'
         line (the 'Two names' card explains it) and no 'HEIGHT ... not computed'
         (height is measured ballistically, see height above). */
      const items = [];
      if (a.num === '—' && !a.noJump && !a.rotReason && a.name !== 'No jumps found')
        items.push(['ROTATIONS', a.revReason ||
          'On this footage none of the independent counters passed its own check.']);
      if (a.height === '—' && a.airTime !== '—' && a.heightWithheld && !a.noJump)
        items.push(['HEIGHT',
          'The air time here is too uncertain to give a height — its range reaches zero.']);
      if (a.height === '—' && a.airTime === '—' && !a.noJump)
        items.push(['HEIGHT',
          'Computed from air time — which is not measured here.']);
      /* Engine warning from /status (fallback engine, unprepared
         video…), the same thing the wait screen showed; without this line
         the person would not know why the answer is poorer than usual. */
      (NS.JOB_WARNINGS[NS.lastJobId] || []).forEach(k => {
        const w = NS.WARN_TEXT[k];
        items.push(['ENGINE', w ? (w[0]) : String(k).replace(/_/g, ' ')]);
      });
      nmCard.hidden = !items.length;
      nmBody.innerHTML = items.map(([t, d]) => `
        <div class="unmeasured-item rz-nm__item">
          <div class="rz-nm__k">${t}</div>
          <div class="rz-nm__d">${d}</div>
        </div>`).join('');
      if (nmCard.open) nmCard.open = false;
    }

    /* PAIR MODE of the 'Is this right?' card: ONLY for a REAL
       ambiguity of the edge (Lutz/Flip, domain §4: from one angle the blade tilt
       is not visible). The pair is the question of the card itself, with one request for the label, and 'yes/no' is hidden: confirming
       'correct' for a name that the system itself calls ambiguous is not allowed.
       Top-2 statistical alternatives in general ('Lutz or Axel?' at
       p~0.13 vs 0.75) are NOT considered a pair, verified by measurement. */
    (function syncPairMode() {
      const two = (a.alts || []).slice(0, 2);
      const isEdgePair = !a.noJump && two.length === 2 &&
        two.includes('Lutz') && two.includes('Flip');
      a.edgePair = isEdgePair ? two : null;
      const title = document.getElementById('vc-title');
      const desc = document.getElementById('vc-desc');
      const yesno = document.getElementById('vc-yesno');
      const pair = document.getElementById('vc-pair-btns');
      const other = document.getElementById('btn-vc-other');
      const T = k => (window.TEXT ? window.TEXT.t(k) : '');
      if (title) { title.textContent = isEdgePair ? T('vcPairTitle') : T('vcTitle'); if (isEdgePair) title.dataset.live = '1'; else delete title.dataset.live; }
      if (desc) { desc.textContent = isEdgePair ? T('vcPairDesc') : T('vcDesc'); if (isEdgePair) desc.dataset.live = '1'; else delete desc.dataset.live; }
      if (yesno) yesno.hidden = isEdgePair;
      if (other) other.hidden = !isEdgePair;
      /* The button state belongs to the ATTEMPT, not the screen: after answering
         attempt 1 the buttons were hidden for attempt 2 too, and 'Recorded. Thank you'
         stood under someone else's jump. The answer to an attempt is remembered by
         syncFeedbackCards (localStorage key by stem). */
      ['btn-vc-yes', 'btn-vc-no'].forEach(id => { const b = document.getElementById(id); if (b) b.hidden = false; });
      ['vc-thanks', 'vc-fix'].forEach(id => { const b = document.getElementById(id); if (b) b.hidden = true; });
      document.querySelectorAll('#card-verdict-check .rz-check__consent').forEach(x => x.remove());
      if (pair) {
        pair.hidden = !isEdgePair;
        pair.innerHTML = isEdgePair ? two.map(n =>
          `<button class="btn btn--outline btn--sm btn-pair-choice" data-choice="${n}">${NS.jumpNameLocal(n) ? NS.jumpNameLocal(n).replace(/^./, c => c.toUpperCase()) : n}</button>`).join('') : '';
      }
    })();

    /* Quick label under the measurements. Not for a declared jump
       (the label before display already exists and is cleaner), not for an attempt already answered,
       not for an undetermined name. The Lutz/Flip pair is a 'which' question, because
       'yes' to an ambiguous name cannot be said (the same mode as in
       the card). The buttons lead to the same form, so the save path is one. */
    (function syncQuickCheck() {
      const box = document.getElementById('vc-quick');
      const btns = document.getElementById('vc-quick-btns');
      const ttl = document.getElementById('vc-quick-t');
      if (!box || !btns || !ttl) return;
      if (box.dataset.preReveal === '1') {
        box.querySelectorAll('.rz-check__consent').forEach(x => x.remove());
        delete box.dataset.preReveal;
      }
      /* This attempt already has a label BEFORE the numbers are shown (wait screen),
         so we do not ask a second time, only confirm and ask for training consent
         if it is not yet given (without consent the label does not enter the training set) */
      if (a.preRevealLabel && NS.realResults && !NS.demoShown) {
        const jc = NS.JOB_CONSENT.get(NS.lastJobId);
        box.querySelector('.rz-quick-check__why')?.remove();
        ttl.textContent = NS.TX('waitAskSavedAns').replace('{j}', NS.askLabel(a.preRevealLabel.jump, a.preRevealLabel.turns));
        btns.replaceChildren();
        if (jc && jc.mine && !jc.consent) { box.append(NS.trainConsentBox(NS.lastJobId, jc)); box.dataset.preReveal = '1'; }
        document.getElementById('verdict-feedback')?.classList.remove('is-quick');
        box.hidden = false;
        return;
      }
      let answered = false;
      try { answered = !!a.stem && localStorage.getItem('js.vc.' + a.stem) === '1'; } catch (_) { }
      const show = NS.realResults && !NS.demoShown && !a.noJump && !noJumpsFound && !!a.stem
        && !a.declaredVerdict && !answered && !(a.nameUncertain && !a.nameDisplay);
      box.hidden = !show;
      /* Two identical questions stood side by side: a short row and
         a collapsed 'Give feedback'. When the row is visible, the collapsed form is hidden
         and opens only from 'No'/'Other'. */
      document.getElementById('verdict-feedback')?.classList.toggle('is-quick', show);
      if (!show) return;
      const fb = () => { const d = document.getElementById('verdict-feedback'); if (d) d.open = true; return d; };
      /* Without a reason, the question 'Which jump was it?' under 'Double Lutz'
         read as doubt without grounds */
      let why = box.querySelector('.rz-quick-check__why');
      if (!why) { why = document.createElement('p'); why.className = 'rz-note rz-quick-check__why'; ttl.after(why); }
      why.textContent = a.edgePair
        ? 'Lutz and flip differ only by the take-off edge, which one camera cannot see. Your answer teaches the system.'
        : 'One tap. Your answers are how the system gets more accurate.';
      if (a.edgePair) {
        ttl.textContent = 'Which jump was it?';
        btns.innerHTML = a.edgePair.map(n => `<button class="btn btn--outline btn--sm" data-q-pair="${n}">${
          (NS.jumpNameLocal(n) || n).replace(/^./, c => c.toUpperCase())}</button>`).join('')
          + `<button class="btn btn--outline btn--sm" data-q-other="1">Other</button>`;
      } else {
        ttl.textContent = 'Did the system get the jump right?';
        btns.innerHTML = `<button class="btn btn--outline btn--sm" data-q-yes="1">Yes</button>`
          + `<button class="btn btn--outline btn--sm" data-q-no="1">No</button>`;
      }
      btns.querySelectorAll('button').forEach(b => {
        b.onclick = () => {
          const d = fb();
          if (b.dataset.qYes) document.getElementById('btn-vc-yes')?.click();
          else if (b.dataset.qNo) document.getElementById('btn-vc-no')?.click();
          else if (b.dataset.qOther) document.getElementById('btn-vc-other')?.click();
          else if (b.dataset.qPair) document.querySelector(`.btn-pair-choice[data-choice="${b.dataset.qPair}"]`)?.click();
          if (!b.dataset.qYes && !b.dataset.qPair) d?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
      });
    })();

    const errCount = document.getElementById('ans-err-count');
    /* Honest caption in three states: found N; nothing found, but
       the checks passed ('checked N — clean'); no checks were run
       ('not measured'). Passed checks are never captioned 'not measured'. */
    const errors = a.errors || [];
    const uncertainN = (a.errorsUncertain || []).length;
    /* The main word stands first, in the language of a person on the ice: no errors
       / this many found. How many checks passed and what remained
       uncertain is evidence; it lives under the disclosure nearby. */
    if (errCount) errCount.textContent = errors.length
      ? `${errors.length} found`
      : '';
    void uncertainN;

    const errBody = document.getElementById('ans-errors-body');
    if (errBody) {
      /* Detector confidence next to each error (invariant 2).
         step_out/touch_down/hand_down/tilted_axis the engine measures with tier=low:
         that is 'possibly', not a fact, and such do not go into the focus of the day. */
      const econf = a.errorsConf || {};
      const foundHtml = errors.map(e => {
        const it = NS.ERR_UA[e];
        const name = it ? it[0] : String(e).replace(/_/g, ' ');
        const why = it ? it[1] : '';
        const low = String(econf[e] || '').toLowerCase() === 'low';
        /* low detector confidence: 'possibly', with advice to check the video */
        return `<div class="rz-errs__row rz-errs__row--found${low ? ' rz-errs__row--maybe' : ''}">
          <div class="rz-errs__name">${low ? 'Possibly: ' : ''}${low ? name.toLowerCase() : name}</div>
          ${why ? `<div class="rz-errs__why">${why}</div>` : ''}
          ${low ? `<div class="rz-errs__why">Check this moment in the video.</div>${a.landing != null ? `<button type="button" class="rz-link rz-link--btn rz-errs__seek" data-seek="${parseFloat(a.landing)}">Show the moment in the video →</button>` : ''}` : ''}
        </div>`;
      }).join('');
      /* Neither "found" nor "clean": the geometry exists but is uncertain (e.g.
         the scale in the frame drifted outside the check window). Hiding such a case silently is
         as dishonest as counting it as an error. */
      const uncertain = a.errorsUncertain || [];
      const uncertainHtml = uncertain.map(u => {
        const it = NS.ERR_UA[u.code];
        const name = it ? it[0] : String(u.code).replace(/_/g, ' ');
        /* Without a concrete reason the second line repeated the header verbatim
           ('Fall: not determined reliably / not determined reliably'). */
        const why = NS.errorReasons()[u.reason] || '';
        return `<div class="unmeasured-item rz-nm__item">
          <div class="rz-nm__k">${name}</div>
          <div class="rz-nm__d">${why || 'could not be checked reliably on these frames'}</div>
        </div>`;
      }).join('');
      /* clean checks in one line, so that 'no errors found' has evidence */
      /* Shows WHICH checks passed, and an honest note that the rest were not checked
         (a video with a fall must not read 'No errors found: 2 checks passed'). */
      const cleanNames = (a.errorsCleanCodes || []).filter(Boolean)
        .map(c => (NS.ERR_UA[c] ? NS.ERR_UA[c][0] : String(c).replace(/_/g, ' ')).toLowerCase());
      const partial = uncertain.length > 0 || (cleanNames.length > 0 && cleanNames.length < 4);
      const cleanHtml = (!errors.length && a.errorsClean)
        ? `<div class="rz-errs__row rz-errs__row--clean"><div class="rz-errs__why">${
            cleanNames.length
              ? `No errors found in what was checked: ${cleanNames.join(', ')}.`
                + (partial ? ' ' + 'The rest could not be checked on this video — that does not mean they are absent.' : '')
              : `No errors found — ${a.errorsClean} check${a.errorsClean === 1 ? '' : 's'} passed.`}</div></div>`
        : '';
      /* nothing was checked: one sentence why, instead of an empty card */
      const noneHtml = (!errors.length && !a.errorsClean && !uncertain.length)
        ? `<div class="unmeasured-item rz-nm__item"><div class="rz-nm__k">Execution errors</div><div class="rz-nm__d">${
            'fall, two-foot, step-out, touch-down and axis could not be checked reliably on these frames — we do not show them rather than guess.'}</div></div>`
        : '';
      errBody.innerHTML = foundHtml + cleanHtml;
      errBody.querySelectorAll('[data-seek]').forEach(btn => {
        btn.onclick = () => {
          const vv = document.getElementById('ans-video');
          const t = parseFloat(btn.dataset.seek);
          if (!vv || !Number.isFinite(t)) return;
          try { vv.pause(); vv.currentTime = Math.max(0, t - 0.3); } catch (_) { }
          document.getElementById('ans-vid-stage')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
      });
      /* 'Not determined reliably' and 'could not check' are
         service information. They do not disappear (no silent failures), but
         live in the collapsed 'Measurement details', not on the first screen. */
      const techBody = document.getElementById('ans-not-measured-body');
      const techCard = document.getElementById('card-not-measured');
      /* Without the subtitle 'Two-foot landing — …' next to 'No errors
         found', it read as a found error. These are checks that could not be done on these frames,
         so we say so. */
      /* the jump is not confirmed: there is nothing to check for errors, and the line
         'fall, two feet… not checked' only confused. */
      const techExtra = (a.noJump || a.fragment) ? '' : uncertainHtml
        ? `<div class="rz-nm__h">Not checked on this video</div>` + uncertainHtml + noneHtml
        : noneHtml;
      if (techBody && techCard && techExtra) {
        techBody.insertAdjacentHTML('beforeend', techExtra);
        techCard.hidden = false;
      }
      const errCard = document.getElementById('card-errors');
      /* no attempt (no jumps found): no error card */
      if (errCard) errCard.hidden = noJumpsFound || a.name === 'No analyses yet' || !!a.noJump || !!a.fragment
        || (!errors.length && !a.errorsClean);
      NS.loadNextStep(noJumpsFound ? null : a);
      NS.checkPersonalRecord(a);
      NS.syncSharedBanner();
      const hs = document.getElementById('btn-hero-share');
      if (hs) hs.hidden = noJumpsFound || !!a.noJump;
    }

    // Skating Stability & Flow Card
    /* Stability/knee/tilt are shown ONLY when measured. Fallbacks
       78/100, 148°, and 6.2° were invented on every real analysis. */
    const stabCard = document.getElementById('card-stability');
    const hasStab = a.stabilityScore != null || a.kneeAngle != null || a.torsoTilt != null;
    if (stabCard) {
      stabCard.setAttribute('data-has-stab', hasStab ? '1' : '0');
      stabCard.hidden = !hasStab;   /* an empty card is never shown */
    }
    const stabScore = document.getElementById('ans-stability-score');
    if (stabScore) stabScore.textContent = a.stabilityScore != null ? `${a.stabilityScore} / 100` : '';
    const stabCat = document.getElementById('ans-stability-category');
    if (stabCat) stabCat.textContent = a.stabilityCategory || '';
    const kneeEl = document.getElementById('ans-knee-angle');
    if (kneeEl) kneeEl.textContent = a.kneeAngle != null ? `${a.kneeAngle}°` : '—';

    const torsoEl = document.getElementById('ans-torso-tilt');
    if (torsoEl) torsoEl.textContent = a.torsoTilt != null ? `${a.torsoTilt}°` : '—';

    const cueEl = document.getElementById('ans-stability-cue');
    if (cueEl) cueEl.textContent = a.stabilityCue || '';

    /* The 'next attempt' button is hidden when there is only one attempt: offering
       a transition to nowhere is a click into nothing ('Next attempt · 1 of 1'). */
    const nextBtnTxt = document.getElementById('btn-next-attempt-txt');
    const nextBtnEl = document.getElementById('btn-next-attempt');
    if (nextBtnEl) nextBtnEl.hidden = list.length < 2;
    /* No '· 2 of 3' here: the position is shown at the top of the screen ('1 / 3'). */
    if (nextBtnTxt) nextBtnTxt.textContent = 'Next attempt';
    NS.markMeasuredLive();
    try { if (window.__jsAskGuess) window.__jsAskGuess(); } catch (e) { }
  }

  function openAttempt(name, rot, verdict) {
    renderAttempt(0);
    NS.go('answer');
  }

  Object.assign(NS, {
     renderAttempt, openAttempt,
  });
})();
