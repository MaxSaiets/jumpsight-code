/* Turns job summaries into attempts, fetches results, failure and last-answer screens. */
(function () {
  'use strict';
  const NS = window.JS.app;
  /* The single rendering of the verdict for the summary and the history. */
  function summaryToAttempt(j, jobId) {
    // Old reports could contain an empty name with name_uncertain=false.
    const nameDisplay = typeof j.name_display === 'string' ? j.name_display.trim() : '';
    const rawName = typeof j.name === 'string' ? j.name.trim() : '';
    const nameUncertain = [true, 'true', 'True'].includes(j.name_uncertain)
      || (!nameDisplay && !rawName);
    j = { ...j, name: rawName, name_display: nameDisplay || null, name_uncertain: nameUncertain };
    const rev = typeof j.rev === 'number' ? j.rev : null;
    const turns = typeof j.turns === 'number' ? j.turns : null;
    const band = Array.isArray(j.band) && j.band.length === 2 ? j.band : null;
    const halfBand = band ? (band[1] - band[0]) / 2 : null;   /* ± spread of the revolution measurement */
    const air = typeof j.air_s === 'number' ? j.air_s : null;
    const noJump = j.state === 'no_jump' || j.state === 'error';
    /* Production, a clip with rotation and no jump: an 'approach fragment'
       (flight < 0.2 s) got 'THE ONE THING: ended on the ice' and a confident
       'Fall', although there is no jump to talk about. The fragment behaves
       as an unconfirmed jump: execution errors are not assessed. */
    const airAny = typeof j.air_s === 'number' ? j.air_s
      : (typeof j.air_s_raw === 'number' ? j.air_s_raw : null);
    /* a raw flight < 0.2 s that did not pass the check is a fragment, whatever
       cause the engine named first (on a 60 fps clip: 0.07 s with the cause
       AZIMUTH_ALIASING_SUSPECT was shown as 'Axel · name likely') */
    /* the same condition as in the log (coach/jobs.py, count is None),
       otherwise the screen said 'not a jump' while the log recorded a jump with a count */
    const fragment = !noJump && turns === null && typeof j.air_s !== 'number' && airAny !== null && airAny < 0.2;
    let vClass = 'none', vTitle = 'No ISU call issued', vSub = '', heroWhy = null, shownTurns = null;
    if (noJump) {
      vTitle = 'Jump not confirmed';
      /* The reason is spelled out here: the full report is not linked from this
         screen, and the engine reasons are mapped to plain words. */
      const NOJUMP_TEXT = {
        'no take-off found at this moment': 'no take-off from the ice is visible here',
        'could not be analysed': 'this part could not be analysed',
        'POSE_PERSON_UNSUPPORTED': 'The skater’s pose could not be reliably detected in this segment: the body or skates are too small or out of frame here.',
        'NO_BALLISTIC_PROFILE': 'The movement here did not look like a jump in the air: the skater did not leave the ice long enough to measure, or the take-off or landing is not in the video.',
        'BBOX_SHAPE_CHANGE': 'The skater’s shape changed in a way a take-off does not explain (for example a turn, a deep bend or a camera zoom), so no jump was counted.',
        'INSUFFICIENT_TIME_SUPPORT': 'There are too few distinct timestamps to check flight — the video looks slowed down; the original without slow motion can be checked.',
        'CURVATURE_NOT_GRAVITY': 'The trajectory does not provide a reliable flight measurement: the camera moves too much in this segment.',
      };
      const reason = j.why || j.error || '';
      const codes = reason.split(';').map(code => code.trim()).filter(Boolean);
      if (codes.includes('POSE_PERSON_UNSUPPORTED')) {
        vTitle = 'Skater not confirmed';
        vSub = NOJUMP_TEXT.POSE_PERSON_UNSUPPORTED;
      } else vSub = codes.map(code => NOJUMP_TEXT[code] || (/^[A-Z][A-Z0-9_]+$/.test(code)
        ? 'There are not enough reliable frames to check the jump.' : code)).join(' ')
        || 'take-off and landing were not confirmed';
    /* ORDER OF BRANCHES: the whole count is checked FIRST. When the engine holds a DECIMAL
       number but gives a WHOLE count (turns=2), the screen must not show a dash and
       'revolutions not measured'. Measured on a fresh cache: a count is present
       in 21 of 50 clips, and in almost all of them a decimal number is held. */
    } else if (turns !== null) {
      const tn = { 1: 'Single', 2: 'Double', 3: 'Triple', 4: 'Quad' }[turns] || String(turns);
      const isAxel = j.call_family === 'axel';
      /* ONE RULE FOR TWO PATHS: the family from `call_family` is used for the count ONLY when
         the name is ready to name it. `call_family` comes from the count bands, which pick the
         family from the same shaky Bayes type that the NAME path may have judged unreliable
         (name_uncertain); without this rule a refusal in one place would leak as an
         assertion in another ('NOT DETERMINED' above, 'Double Axel — 2.5 revolutions' below).
         Otherwise the whole revolution count is shown,
         which does not depend on the family, and it is said honestly that an axel
         would add half a revolution more.
         Nothing is invented: the family is named only when it is known.
         The axel step is not applied here. */
      const familyStated = !j.name_uncertain || !!j.name_display;
      /* A PAIR also counts as a set name ('lutz or flip'), and a lutz is never 2.5 revolutions:
         half a revolution is added only when the axel itself is named. */
      const namedAxel = /axel/i.test(
        String(j.name_display || j.name || ''));
      const axelNominal = isAxel && familyStated && namedAxel;
      const shown = axelNominal && typeof j.turns_nominal === 'number'
        ? j.turns_nominal : turns;
      shownTurns = shown;
      /* GREEN MEANS 'ALL GOOD', NOT 'I DON'T KNOW'.
         The block is green only where the name is present; a green message
         under 'name not determined' would contradict the content. */
      /* EXECUTION ERROR OUTWEIGHS COLOR. The green block 'Double Lutz' stood on the same screen
         where below it said 'Execution errors · 1 found' and 'attempt
         ended with a step-out'. The color said 'all good' where
         the system itself had just said the opposite.
         */
      vClass = (j.errors && j.errors.length) ? 'bad'
        : ((!j.name_uncertain || j.name_display) ? 'clean' : 'short');
      /* One fact, once. The heading says what is not in the hero: the NAME
         of the jump in plain words ('Double Lutz'), and does not
         repeat the number from above. When there is no name, only the
         size remains: nothing needs to be invented. */
      /* When the bridge marked the name uncertain
         (low confidence and 3+ equal alternatives), the heading does not
         name the jump, otherwise the person reads a guess as a fact
         (measured: in such clips the name is right in 3 of 19). */
      const humanName = j.name_display
        ? NS.jumpPairLocal(j.name_display)
        : (j.name_uncertain ? null : NS.jumpNameLocal(j.name));
      /* the count taken as the NEAREST band after the call was held (estimated in /summary)
         is an estimate, not a measurement (1 of 60 counts in the cache):
         '≈' in the heading and a reason. */
      const estimated = j.estimated === true;
      /* the estimate comes in three kinds, and each has its own reason.
         None of them may be written as just 'fell between bands':
         for azimuth aliasing and agreement of two channels that would be untrue. */
      const estKind = j.estimate_kind || 'between_bands';
      vTitle = humanName
        ? `${tn} ${humanName}`
        : (axelNominal
          ? `${tn} Axel — ${shown} rotations`
          /* ONE FACT, ONCE. The revolution count already stands at the top in huge digits;
             repeating it here ('Double — 2 revolutions') would take a line and add nothing.
             Without a jump name this heading says the SIZE, which
             the hero does not have.
             Nothing else is needed here. */
          : tn);
      /* The heading says the MAIN thing (how many revolutions); the measurement detail is
         one calm line. The raw 68% range stays out of the verdict
         ('0.61–2.46') and so does a 'requires filming at 60
         frames/s' complaint, which reads as a malfunction although it is an honest band.
         The band stays in the log and the full report. */
      /* The ± (68%) band belongs to the FLIGHT revolutions (the measurement), not to
         the human count: '2 ±0.9' read as 'may be 1 or 3'.
         Under the count, the count's confidence in words, as in the JSON. */
      const half = band ? (band[1] - band[0]) / 2 : null;
      /* '2.83 ±1.92' without a caption reads as a malfunction. The ± is
         the MEASUREMENT SPREAD, and when it is larger than half a revolution,
         it is more honest to say so in words than to leave the user guessing. */
      /* The count branch is checked FIRST, so a decimal number that is empty
         can be reached here (the engine held the count but not the decimal
         number); `rev.toFixed` must not crash behind an empty catch. */
      if (estimated) vTitle = '≈ ' + vTitle;
      /* Half a revolution that cannot be seen. The engine treats the family as an axel, but
         the name cannot be stated, so the number is ambiguous too: the axel
         counts half a revolution more than the rest. Staying silent about this
         is not allowed: the person sees a whole number and does not know that it
         depends on the family. */
      const halfTurnDoubt = isAxel && !familyStated;
      const estWhy = countEstimateWhy(estKind);
      /* ONE SENTENCE: the key point is
         one: the number depends on the family, and the family is not visible.
         The origin of the count ('from flight physics') stays under
         'Show measurement', which is where it belongs. */
      vSub = (halfTurnDoubt
                ? 'if this is an axel, there is half a turn more'
                : '')
        + (halfTurnDoubt && estimated ? ' · ' : '')
        + (estimated ? estWhy : '')
        // A model estimate does not show where exactly the revolution difference was accumulated.
        + (estimated ? '' : (rev !== null && j.rev_usable !== false
              /* The flight revolution count and its spread stand
                 in a tile below: here only the link between it and
                 the count. The separator is unconditional when there is already
                 text ahead, otherwise the words run together. */
              ? ((halfTurnDoubt || estimated) ? ' · ' : '')
                + (half != null && half > 0.5
                   ? 'in-flight rotation is imprecise here — the count also relies on flight physics'
                   /* This note lives in the caption of the 'Revolutions in flight' tile,
                      not under the name. */
                   : '')
              /* When the sentence above already says 'this video does not hold' about
                 the family, repeating the same phrase about the number is
                 noise. The second half of the sentence stays only
                 when the first one did not apply. */
              : (halfTurnDoubt
                 ? ''
                 : 'counted from the flight time; this footage does not give a more precise rotation number')));
      vSub = vSub.replace(/\s·\s*$/, '');
      const rotConfUA = { low: 'low', medium: 'medium', high: 'high' };
      // The confidence of physical revolutions and of the nominal count are different quantities.
      const countConf = ['low', 'medium', 'high'].includes(j.count_confidence)
        ? j.count_confidence : (estimated ? 'low' : null);
      /* in words, like the name; without confidence we write nothing */
      void rotConfUA;
      heroWhy = countConf ? ({ high: 'count — confident',
                               medium: 'count — likely',
                               low: 'count — estimate' })[countConf]
        : '';
    } else if (rev === null || j.rev_usable === false) {
      vTitle = 'Rotations not measured on this footage';
      /* The reason comes from the server (rot_reason), and each has
         its own advice: 30 frames/s
         is advice only for aliasing (27 cases of 124 in the cache). */
      const ROT_WHY = {
        air_time_non_ballistic_hip_trajectory: [
          'motion in this window does not support free flight. Review take-off and landing in the video; the window is saved for checking.'],
        /* The limit of THIS video without orders ('shoot closer'),
           PRODUCT.md, hard constraint No. 4: the system describes its own limits */
        AZIMUTH_ALIASING_SUSPECT: [
          'the rotation is too fast for this video’s frame rate: almost half a turn passes between frames, so the rotation count is not reliable on these frames.'],
        REV_BAND_WIDER_THAN_HALF_TURN: [
          'the uncertainty band is wider than half a turn: these frames do not support a precise count.'],
        TIMING_PHASE_UNSUPPORTED: [
          'there are too few frames showing the rotation around the possible take-off or landing.'],
        REV_BAND_INCLUDES_ZERO: [
          'the uncertainty band includes zero: the flight is too short or too unclear to count rotations.'],
        AIR_TIME_IMPLAUSIBLE: [
          'the flight time came out implausible — the video looks slowed down or has dropped frames; the original without slow motion can be measured.'],
        TOO_FEW_FLIGHT_OBSERVATIONS: [
          'too few frames in flight show a usable pose: the skater is small in frame or the frame rate is low.'],
        ENDPOINT_OUTSIDE_VALID_RANGE: [
          'the jump starts or ends outside the video.'],
      };
      if (j.rot_reason === 'air_time_non_ballistic_hip_trajectory') {
        vTitle = 'Flight needs review';
      }
      /* AIR_TIME_IMPLAUSIBLE has TWO different meanings, and confusing
         them is dishonest: a flight shorter than 0.2 s is an approach fragment
         (measured: 0.10–0.20 s at 0.002–0.03 revolutions), and one longer than
         0.9 s is slow-motion video. The advice must differ. */
      const airS = typeof j.air_s === 'number' ? j.air_s
        : (typeof j.air_s_raw === 'number' ? j.air_s_raw : null);
      if ((j.rot_reason === 'AIR_TIME_IMPLAUSIBLE' || typeof j.air_s !== 'number') && airS !== null && airS < 0.2) {
        /* the number is NOT printed: it did not pass the check as a measurement,
           and serves only to choose the wording */
        vTitle = 'Looks like an entry fragment, not a jump';
        vSub = 'the time off the ice is too short for a jump — more likely a step or hop on the entry. Real attempts are shown first.';
      }
      const isFragment = (vTitle && vTitle.indexOf('fragment') >= 0);
      const rotWhy = isFragment ? null : ROT_WHY[j.rot_reason];
      if (rotWhy) {
        vSub = (rotWhy[0]);
      } else if (!vSub) {
        vSub = 'the rotation measurement did not pass its quality check. Check the confidence and explanation beside each finding below.';
      }
      /* THE NAME IS THE HEADING, WITHOUT REVOLUTIONS: name confidence is project
         priority No. 2 and must not hide behind a 'Revolutions not measured…' heading.
         The name is the heading, the reason is the subtitle. */
      if (!isFragment) {
        const nm0 = j.name_display ? NS.jumpPairLocal(j.name_display)
          : (j.name_uncertain || !j.name ? null : NS.jumpNameLocal(j.name));
        if (nm0) {
          vTitle = nm0.charAt(0).toUpperCase() + nm0.slice(1);
          vSub = 'rotations not measured: ' + vSub;
        }
      }
    } else {
      /* Revolutions measured, but the count did not match the band.
         j.clean in /summary is a NUMBER of passed checks (e.g.
         4), not a boolean 'clean', so it must not be read as a verdict
         'Full rotation (clean)'. The ISU
         verdict of jumpsight is not output at all, so here
         it CANNOT be synthesized from nothing. */
      /* The branch enters exactly when there is NO WHOLE count.
         Printing decimal revolutions as the heading is allowed only when
         the engine itself accepted them as valid: otherwise the screen showed
         a big '—' under the caption ROTATIONS and at the same time '0.31 rev in
         flight' two lines below. */
      vTitle = (j.rev_usable === false)
        ? `${j.name || 'Jump'} — rotations not measured`
        : `${j.name || 'Jump'} — ${rev.toFixed(2)} rotations in the air`;
      vSub = 'the whole-turn count for this attempt did not match any count band';
    }
    const att = {
      stem: j.stem || jobId,
      peak: j.peak_frame,
      /* the skater track for 'close-up'; old analyses do not have it */
      track: (j.track && Array.isArray(j.track.pts)) ? j.track : null,
      heroWhy,
      /* Decimal revolution count is shown only as a MEASUREMENT,
         when the uncertainty band is narrower than half a revolution and does not include
         zero (the same rule already applied in the log). Otherwise
         a dash: inventing precision is worse than honestly staying silent. */
      /* The biggest number on screen must carry the same
         mark as the verdict (with azimuth aliasing the verdict says '≈ Double Axel',
         so a bare '2' beside it would read as a measurement). */
      num: shownTurns !== null
           ? (j.estimated === true ? '≈' : '') + String(shownTurns)
           : ((rev !== null && j.rev_usable !== false) ? rev.toFixed(2) : '—'),
      heroUnit: shownTurns !== null
        ? "rotations (judges' count)" : 'rotations',
      countEstimated: shownTurns !== null && j.estimated === true,
      /* name_display is an honest PAIR 'lutz or flip' where the edge from
         one camera is fundamentally not visible. A guessed name in this
         place is worse than the pair: a coach can work with a pair, but not with
         a wrong name (flip<->lutz swaps gave 8 errors out of 21).
         The bridge keeps j.name as top-1 for the log. */
      name: noJump ? 'Not confirmed'
                   : (j.name_display
                      ? NS.jumpPairLocal(j.name_display)
                      : (j.name_uncertain || !j.name
                         ? 'Not resolved'
                         : NS.jumpNameLocal(j.name) || j.name)),
      /* a hint instead of an invented confidence: the two most likely
         names stay visible, but as versions, not as a verdict */
      nameUncertain: !noJump && !!j.name_uncertain,
      nameDisplay: j.name_display || null,
      /* family instead of a name: 'toothed' / 'edge' is not a verdict,
         but the only thing visible from one angle */
      nameFamily: j.name_family_hint || null,
      nameConf: j.name_conf || null,
      nameP: (typeof j.name_p === 'number') ? j.name_p : null,
      nameAlts: Array.isArray(j.alts) ? j.alts.slice(0, 2) : [],
      nameNote: j.name_note || null,
      jumpCode: '',
      verdictClass: vClass, verdictTitle: vTitle, verdictSub: vSub,
      /* Rotation speed in flight is the only number on
         the screen with an EXTERNAL reference (Bruening 2018 norm); since
         it is the tile (rateDeg/rateNote below); the difference is named only
         when the measurement band does not cover the norm. */
      /* raw measurements for the tiles: decimal revolutions only when valid */
      revFlight: (rev !== null && j.rev_usable !== false) ? rev : null,
      revHalf: (rev !== null && j.rev_usable !== false && halfBand != null) ? halfBand : null,
      rateDeg: (typeof j.rate_deg_s === 'number') ? j.rate_deg_s : null,
      /* The person counts revolutions, not degrees: the caption carries the same numbers
         (band, Bruening norm) in revolutions per second; degrees go in the last
         line for the coach. Conversion by /360, no new measurements. */
      rateBandRps: (typeof j.rate_deg_s === 'number' && Array.isArray(j.rate_band_deg_s))
        ? (j.rate_band_deg_s[1] - j.rate_band_deg_s[0]) / 2 / 360 : null,
      rateNote: (typeof j.rate_deg_s === 'number')
        ? [(j.rate_vs_norm === 'same'
              ? ('about the same as typical ' + j.rate_norm_class)
              : j.rate_vs_norm && j.rate_norm_deg_s
              ? ((j.rate_vs_norm === 'below' ? 'slower' : 'faster') + ' than typical ' + j.rate_norm_class
                  + ` (~${(j.rate_norm_deg_s / 360).toFixed(1)}/s)`)
              : ''),
           `${j.rate_deg_s} °/s`].filter(Boolean).join(' · ')
        : null,
      airTime: air !== null ? air.toFixed(2) : '—',
      /* ± half of the 68% band: the engine measures it, but the screen did not yet
         show it, so the height '72 cm' read as an exact measurement */
      airHalf: (air !== null && Array.isArray(j.air_band) && j.air_band.length === 2)
        ? (j.air_band[1] - j.air_band[0]) / 2 : null,
      heightHalfCm: (typeof j.height === 'number' && Array.isArray(j.height_band) && j.height_band.length === 2)
        ? (j.height_band[1] - j.height_band[0]) * 50 : null,
      /* HEIGHT IS MEASURED (h = g*t^2/8 from flight time; frame scale
         is not needed). The engine computes it, so the field is never a
         hardcoded '—' with a 'Not measured' reason. */
      height: (typeof j.height === 'number') ? (j.height * 100).toFixed(0) : '—',
      heightWithheld: j.height_withheld || null,   /* the band reached zero */
      takeoff: Number.isFinite(j.t_s) ? j.t_s.toFixed(2) : null,
      timeEstimated: j.time_source !== 'presentation_timestamps',
      flight: air !== null ? air.toFixed(2) : null,
      landing: Number.isFinite(j.landing_s) ? j.landing_s.toFixed(2)
        : (j.time_source !== 'unavailable' && Number.isFinite(j.t_s) && air !== null) ? (j.t_s + air).toFixed(2) : null,
      revReason: null,
      rotReason: j.rot_reason || null,   /* the concrete reason is already in the subtitle */
      noJump,
      fragment,
      errors: (j.errors && j.errors.length) ? j.errors : null,
      errorsConf: j.errors_conf || {},
      errorsUncertain: j.errors_uncertain || [],
      errorsClean: (typeof j.clean === 'number') ? j.clean : 0,
      errorsCleanCodes: Array.isArray(j.clean_codes) ? j.clean_codes : [],
      stabilityScore: null, stabilityCategory: null,
      kneeAngle: null, torsoTilt: null, stabilityCue: null,
      hasDisambig: Boolean(j.alts && j.alts.length > 1),
      alts: j.alts || [],
      /* raw values for checking against the person's assessment */
      rawName: String(j.name || '').toLowerCase().replace(' ', '_'),
      turnsNum: shownTurns
    };
    /* DECLARED JUMP. The person themselves
       said they jumped; the name in the heading is THEIR words, and that is visible,
       while the line under the name says what the measurement says about the declaration (verify_declared).
       Measured on the reference set: a correct declaration is confirmed by the system in 63–65%,
       falsely refuted in 2–7%; a false declaration is caught in 39–41%. */
    const dc = j.declared_check;
    if (dc && dc.declared && !noJump) {
      const dn = NS.jumpNameLocal(dc.declared) || dc.declared;
      const _tt = (typeof shownTurns === 'number') ? shownTurns
        : ((j.declared_turns_check && Number.isInteger(j.declared_turns_check.declared)) ? j.declared_turns_check.declared : null);
      const tnw = (typeof _tt === 'number')
        ? ({ 1: 'Single', 2: 'Double', 3: 'Triple', 4: 'Quad' }[Math.floor(_tt)] || '')
        : '';
      const other = dc.best_other ? (NS.jumpNameLocal(dc.best_other) || NS.jumpPairLocal(dc.best_other) || dc.best_other) : '';
      const verdict = dc.verdict === 'consistent'
        ? 'the video is consistent with it'
        : dc.verdict === 'contradicted'
          ? `the video looks more like “${other}” — check it is the right jump`
          : 'the video can neither confirm nor rule it out';
      const edge = dc.edge_unseen ? ' · the Lutz/flip edge is not visible from one angle' : '';
      const cap = (x) => x ? x.charAt(0).toUpperCase() + x.slice(1) : x;
      /* The heading with the declaration lost the '≈' of the count estimate: the number
         '≈3' stood under 'Triple Axel', as if the count were measured
         (real_report_ui_smoke, an analysis with the declaration 'axel · triple') */
      att.verdictTitle = (tnw && att.countEstimated ? '≈ ' : '') + cap(tnw ? `${tnw} ${dn}` : dn);
      att.name = dn;
      att.nameUncertain = false;
      att.nameDisplay = null;
      att.nameConf = null;
      att.nameNote = 'declared by you · ' + verdict + edge;
      att.declaredVerdict = dc.verdict;
    }
    /* DECLARED COUNT. Measured on the reference set (3 caches):
       a correct declaration is confirmed by the system in 33–46%, a wrong one (±1) only in
       3–6%, falsely refuted ≤4%. When the system did not name the count, the number
       is shown as DECLARED, not as a measurement. */
    const dtc = j.declared_turns_check;
    if (dtc && Number.isInteger(dtc.declared) && !noJump) {
      const tv = dtc.verdict === 'consistent'
        ? 'declared by you · the measurement agrees'
        : dtc.verdict === 'contradicted'
          ? `declared by you · the measurement says ${dtc.measured} — check`
          : 'declared by you · the measurement does not settle the count';
      if (att.turnsNum == null || att.num === '—') { att.num = String(dtc.declared); att.turnsNum = dtc.declared; }
      att.heroWhy = tv;
    }
    return att;
  }

  async function fetchJobResults(jobId, { refreshOnly = false, requestEpoch = null, fromHistory = false, completionContext = null } = {}) {
    // A language change does not cancel a new analysis that has not opened yet.
    if (refreshOnly && NS.pendingOpenEpoch !== null) return;
    if (!fromHistory && !refreshOnly && !completionContext && NS.activeJobId === jobId) {
      completionContext = { jobId, owner: NS.activeJobOwner, watcherEpoch: NS.watcherEpoch };
    }
    const epoch = requestEpoch ?? ++NS.resultRequestEpoch;
    const current = () => epoch === NS.resultRequestEpoch && (!completionContext
      || (completionContext.watcherEpoch === NS.watcherEpoch && NS.activeJobId === completionContext.jobId
          && (!completionContext.owner || NS.jobOwnerCurrent(completionContext.owner))));
    if (!current()) return;
    const selectedIdx = NS.currentAttemptIdx;
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 15000);
    try {
      const res = await fetch(`/summary/${encodeURIComponent(jobId)}`, { signal: controller.signal });
      if (!current()) return;
      if (fromHistory && res.status === 404) {
        NS.notice('This analysis cannot be opened: it is no longer on the server or it belongs to another profile. If it is yours, sign in to your account. The journal numbers remain.', 8000);
        return null;
      }
      if (!res.ok) throw new Error(`summary HTTP ${res.status}`);
      if (res.ok) {
        const data = await res.json();
        if (!current()) return;
        const jumps = data.jumps || (Array.isArray(data) ? data : []);
        /* HONEST MAPPING: a number only when
           it arrived; otherwise '—' and the honest verdict 'not determined'
           (no substituted revolutions, flight, height, jump name, errors, stability, knee or tilt). */
        const realAll = jumps.filter(j => j.state !== 'duplicate' && j.state !== 'cancelled')
          /* REAL attempts go first: a demoted hop or fragment honestly
             stays as a card, but is not opened FIRST instead of the
             real jump. Among done attempts, those that HAVE a count and full revolutions go
             before fragments without a count.
             Chronology is kept inside each group,
             no value changes, only the order of the pills. */
          .sort((a, b) => {
            /* rank is computed by the bridge (confidence -> revolutions -> chronology): one
               source of truth for the UI and all measurements. The local rule
               is the fallback for results without a rank. */
            if (typeof a.rank === 'number' && typeof b.rank === 'number') {
              return a.rank - b.rank;
            }
            const grp = j => (j.state !== 'done' ? 2
              : (typeof j.turns === 'number' ? 0
                : (typeof j.rev === 'number' && j.rev >= 0.5 ? 1 : 2)));
            return grp(a) - grp(b);
          });
        /* '1/5' with two '•••' were hops and approach fragments that the bridge marked
           no_jump. They are not needed first by the person: in the
           carousel the real jumps remain; the rest is available in the full report. */
        const real = realAll.some(j => j.state === 'done')
          ? realAll.filter(j => j.state === 'done') : realAll;
        if (real.length > 0 || data.state === 'done') {
          const mapped = real.map(j => summaryToAttempt(j, jobId));
          NS.lastJobId = jobId;
          /* consent to training: the question is only for the owner, and only when it is not yet given */
          NS.JOB_CONSENT.set(jobId, { mine: data.mine === true, consent: data.train_consent === true });
          if (Number.isFinite(data.fps) && data.fps > 0) NS.videoFps = data.fps;
          NS.demoShown = data.demo === true;
          if (data.warnings && typeof data.warnings === 'object') {
            const wk = Object.keys(data.warnings);
            if (wk.length) NS.JOB_WARNINGS[jobId] = wk; else delete NS.JOB_WARNINGS[jobId];
          }
          try { document.getElementById('live-preview')?.remove(); } catch (_) { }
          NS.activeAttempts = mapped;
          /* answer from the wait screen: a label before the numbers are shown */
          if (!fromHistory && !refreshOnly) { await NS.sendWaitAnswer(jobId, jumps, mapped); if (!current()) return; }
          window.__jsSkippedFragments = realAll.length - real.length;
          NS.realResults = true;
          NS.rebuildPills();
          /* The local preview belongs only to the job accepted from this file.
             Otherwise new measurements cannot stay next to the previous video. */
          const av = document.getElementById('ans-video');
          const source = NS.previewJobId === jobId && NS.previewUrl
            ? NS.previewUrl : `/media/${encodeURIComponent(jobId)}/full/original`;
          if (av && av.getAttribute('src') !== source) {
            av.pause();
            NS.ANS_WIN = null;
            av.src = source;
            av.style.display = '';
          }
          NS.loadComments(jobId);
        } else throw new Error('summary not completed');
      }
    } catch (e) {
      if (!current()) return;
      /* A mapping error is visible both in the console and to the person;
         an empty catch would silently show the empty 'upload video' state. */
      console.error('[fetchJobResults]', e);
      if (fromHistory) {
        NS.notice('Could not open the analysis. Try again — the previous result and current analysis are preserved.', 8000);
        return false;
      }
      if (refreshOnly) { NS.notice('Could not update the analysis language. Previous measurements are preserved.'); return; }
      analysisFailed('Could not load the analysis. Try again without uploading the video again.', null,
                     { jobId, owner: completionContext && completionContext.owner });
      return;
    } finally { clearTimeout(deadline); }
    if (!current()) return;

    /* The analysis was just written to the server log, so we pull it in AT ONCE,
       so that 'Today', 'Last answer' and 'Progress' show this
       jump, not the state at the time the page was opened. */
    loadLastAnswer();
    if (window.COACH && window.COACH.refresh) window.COACH.refresh(true);   // after analysis: forced

    if (refreshOnly) { NS.renderAttempt(selectedIdx); return true; }
    if (!fromHistory) {
      NS.clearPendingJob(jobId, completionContext && completionContext.owner);
      NS.activeJobId = null;
      NS.activeJobOwner = null;
      document.getElementById('rec-intro').hidden = false;
      document.getElementById('rec-waiting').hidden = true;
      document.getElementById('rec-waiting').setAttribute('aria-busy', 'false');
    }
    NS.renderAttempt(0);
    if (!fromHistory) {
      if (NS.currentScreen === 'record' || NS.currentScreen === 'answer') NS.go('answer');
      else showAnswerReadyBanner();
    }
    return true;
  }

  function showAnswerReadyBanner() {
    const banner = document.getElementById('answer-ready-banner');
    const textEl = document.getElementById('answer-ready-banner-text');
    if (!banner || !textEl) return;
    const a = NS.activeAttempts[0];
    /* 'lutz · —' for a failed attempt says nothing: the banner uses the verdict heading
       ('Double Lutz') and the first measured error ('Lutz · Fall'). */
    let txt = 'New analysis';
    if (a) {
      const ttl = a.verdictTitle && a.verdictTitle !== '—' ? a.verdictTitle : (a.name || '');
      const err = (a.errors && a.errors.length) ? (NS.ERR_UA[a.errors[0]] ? NS.ERR_UA[a.errors[0]][0] : String(a.errors[0]).replace(/_/g, ' ')) : '';
      txt = [ttl, err].filter(Boolean).join(' · ') || txt;
    }
    textEl.textContent = txt;
    banner.hidden = false;
    banner.onclick = () => { banner.hidden = true; NS.go('answer'); };
    banner.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); banner.click(); } };
  }

  /* Human explanations of technical refusal reasons. The backend gives the exact
     reason, but as a raw code, which tells the user nothing. */
  const FAIL_REASON = {
    'no jump could be analysed in this video': () => 'No jump was found in this video: no take-off and landing could be confirmed in these frames.',
    /* The remaining reasons come from the server and must say what to do
       ('unsupported file type', 'file larger than 1024 MB' alone do not). */
    'unsupported file type': () => 'This file type is not supported. Please use MP4, MOV or WebM.',
    'Analysis did not finish. Try again.': () => 'Analysis did not finish. Try again.',
    'The analysis queue is full. Upload again in a little while.': () => 'The analysis queue is full. Upload again in a little while.',
    'could not be analysed': () => 'Analysis broke on this video. Try again; if it repeats, try another clip.',
  };
  /* Reasons with a variable number ('file larger than 1024 MB', '... longer
     than 900 s') are matched by prefix; the number is taken from the message. */
  const FAIL_PREFIX = [
    [/^file larger than (\d+) MB/i, m => `File too large: over ${m[1]} MB. Trim the video to the jump itself.`],
    [/longer than (\d+) s/i, m => `The video is unreadable or longer than ${m[1]} s. Trim it to the jump.`],
  ];

  function analysisFailed(msg, title, { jobId = null, owner = null } = {}) {
    NS.clearPendingJob(jobId, owner);
    NS.stopWatching();
    document.getElementById('rec-waiting').setAttribute('aria-busy', 'false');
    /* Whoever went to 'Today' or 'Learn' saw: the spinner disappeared, no answer,
       no message. We return to the screen where the reason stands. */
    if (typeof NS.currentScreen !== 'undefined' && NS.currentScreen !== 'record') NS.go('record');
    document.getElementById('rec-intro').hidden = false;
    document.getElementById('rec-waiting').hidden = true;
    const raw = String(msg || '').trim();
    let human = FAIL_REASON[raw];
    if (!human) for (const [re, fn] of FAIL_PREFIX) { const m = raw.match(re); if (m) { human = () => fn(m); break; } }
    /* English only: an older server or a log analysis may
       return a free-text reason, and an engine failure comes as a raw
       'ValueError: …'. We print neither as is: a human phrase plus
       the failure name, so that it does not become silent. */
    if (!human && /^[A-Z][A-Za-z]*(Error|Exception)\b/.test(raw)) {
      const kind = raw.split(':')[0];
      human = () => 'Analysis broke on this video'
        + ` (${kind}). ` + 'Try again; if it repeats, try another clip.';
    }
    document.getElementById('rec-fail-reason').textContent = human ? human() : (msg || 'Server unavailable');
    /* The heading says WHAT failed. 'Could not finish the analysis' above
       'camera unavailable' read as a server failure, although the analysis had not even
       started: the person did not press 'Stop' but started a live recording. */
    const ttl = document.getElementById('rec-fail-title');
    if (ttl) ttl.textContent = title || 'Analysis did not finish';
    const box = document.getElementById('rec-fail-note');
    box.hidden = false; box.focus();
    const retry = document.getElementById('btn-retry-analysis');
    document.getElementById('btn-discard-live').hidden = true;
    retry.textContent = 'Retry';
    retry.hidden = !NS.lastUploadFile && !NS.retryJobId;
    retry.onclick = async () => {
      if (NS.retryJobId) {
        if (NS.retryJobOwner && !NS.jobOwnerCurrent(NS.retryJobOwner)) return;
        NS.prepareWaiting(NS.retryJobOwner && NS.retryJobOwner.name);
        NS.watchJob(NS.retryJobId, { owner: NS.retryJobOwner });
      } else if (NS.lastUploadFile) {
        const file = NS.lastUploadFile;
        if (!NS.analysisSessionReady()) {
          /* An early Retry refreshes the profile, but does not send the file with the callback. */
          const uploadEpoch = NS.uploadRequestEpoch;
          await NS.loadMe();
          if (uploadEpoch === NS.uploadRequestEpoch && file === NS.lastUploadFile) NS.notice('Once your profile has loaded, select Retry again to upload the video.');
          return;
        }
        if (file === NS.lastUploadFile) NS.handleFileUpload(file);
      }
    };
  }

  function countEstimateWhy(kind) {
    /* Owner: no 'not measured / not sure' wording, only where the number comes from */
    if (kind === 'flight_time') return 'counted from the air time and typical rotation speed';
    if (kind === 'kinematic') return 'counted by the body-motion model';
    if (kind === 'fused') return 'counted by the body-motion model';
    if (kind === 'family_remap') return 'counted for the detected jump type';
    return 'rounded to the nearest count';
  }


  async function loadLastAnswer() {
    try {
      const _h = await window.__jsHistory();
      if (_h.ok) {
        const history = _h.data;
        /* For a NEW user this card is dead weight: '—', 'No records',
           'Upload video', 'Go to the Record tab',
           four rows that repeat the session card above, which already has
           a working button 'Record or pick a video'. Shown only
           when there is something to show (measured on an empty profile). */
        const laCard = document.getElementById('card-last-answer');
        if (laCard) laCard.hidden = !(history && history.length > 0);
        window.__jsHistN = (history || []).length;
        if (history && history.length > 0) {
          /* /coach/history returns NEWEST FIRST (jobs.py: reversed), so the latest record is
             index 0. */
          const lastRaw = history[0];
          /* History is written for EVERY attempt, and the newest record is
             often a fragment without a count ('No records · completed'). For the card
             we take the newest attempt of the same video that has a jump name. */
          let last = lastRaw;
          try {
            const src = Array.isArray(history) ? history : null;
            if (src && lastRaw) {
              const same = src.filter(r => r && r.file_key && lastRaw.file_key
                                           ? r.file_key.split('#')[0] === lastRaw.file_key.split('#')[0] : r === lastRaw);
              const named = same.find(r => r && r.jump && r.jump !== 'None');
              if (named) last = named;
            }
          } catch (e) { }
          NS.lastAnswerStem = last.stem || null;
          NS.lastAnswerJob = last.job && last.job !== 'None' ? String(last.job) : null;
          const revEl = document.getElementById('last-ans-rev');
          const nameEl = document.getElementById('last-ans-name');
          const verdEl = document.getElementById('last-ans-verdict');
          const subEl = document.getElementById('last-ans-sub');
          
          /* AN EMPTY VALUE MUST ERASE THE PREVIOUS ONE: every field is ALWAYS assigned,
             otherwise a number from one jump would sit next to the name of another
             and a markup placeholder would stay under 'LAST ANSWER'. */
          if (revEl) {
            const _ok = last.rev_usable !== false && typeof last.revolutions === 'number';
            revEl.textContent = _ok ? Number(last.revolutions).toFixed(2) : '—';
            /* without a number, and without the block '— / revolutions in flight' */
            if (revEl.parentElement) revEl.parentElement.hidden = !_ok;
          }
          /* Next to the name: the human count ('double'), as on the answer screen;
             the flight revolutions alone, without it, read as a verdict. */
          if (nameEl && !last.jump)
            nameEl.textContent = 'Jump not resolved';
          /* AN UNCERTAIN NAME IS NOT A NAME. The log and the answer screen
             write 'name not determined', but this card showed the top-1
             ('toe loop · triple') as a fact: on clips with name_uncertain the name
             is right in 3 of 19. The count in words stays: it comes from the width bands
             and does not depend on the jump family. */
          if (nameEl && last.jump) nameEl.textContent =
            NS.historyJumpName(last) + (last.count_named
              /* The log stores the count as a word (jobs.py). */
              ? ` · ${last.count_estimated ? '≈ ' : ''}${last.count_named}`
              : '');
          if (verdEl) {
            /* The log (coach/jobs.py) writes a reliable boolean clean field, which is used
               directly: revolutions alone must not make a triple axel with a fall 'clean'. */
            /* Codes are never shown raw ('step_out, touch_down'): the same ERR_UA map as on the analysis screen. */
            /* Findings by confidence ('possibly: …' for low),
               color red only for a confident finding */
            const f = NS.findings(last.errors, last.errors_conf);
            verdEl.textContent = NS.historyExecutionLabel(last) || 'completed';
            verdEl.style.color = f.sure.length ? 'var(--short)'
              : f.maybe.length ? 'var(--dim2)' : (NS.historyNoFindings(last) ? 'var(--clean)' : 'var(--dim2)');
          }
          /* A raw stem ('clip_att9') tells a person nothing. Instead, show when it was
             and how many jumps are in that video: without a date
             the 'last answer' could be a month old. */
          if (subEl) {
            let when = '';
            try {
              const ts = parseFloat(last.ts);
              if (Number.isFinite(ts) && ts > 0) {
                const d = new Date(ts * 1000), now = new Date();
                const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
                const diff = Math.round((day(now) - day(d)) / 86400000);
                when = diff === 0 ? 'today' : diff === 1 ? 'yesterday'
                  : d.toLocaleDateString(NS.LOC(), { day: 'numeric', month: 'short' });
              }
            } catch (_) { }
            let nAtt = 0;
            try {
              const fk0 = last.file_key ? String(last.file_key).split('#')[0] : null;
              nAtt = fk0 ? history.filter(r => r && r.file_key && String(r.file_key).split('#')[0] === fk0 && r.jump && r.jump !== 'None').length : 0;
            } catch (_) { }
            const parts = [];
            if (when) parts.push(when);
            if (nAtt > 1) parts.push(`${nAtt} jumps in the video`);
            subEl.textContent = parts.join(' · ');
            subEl.dataset.live = '1';
          }
          NS.markMeasuredLive();
        }
      }
    } catch (e) { }
  }

  Object.assign(NS, {
     summaryToAttempt, fetchJobResults, analysisFailed, loadLastAnswer,
  });
})();
