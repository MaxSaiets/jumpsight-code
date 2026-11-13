/* ══════════════════════════════════════════════════════════════════════
   isu_rank.js — ONE THING THAT MUST BE SAID AFTER THE ATTEMPT

   Why this file exists (research/08-what-to-tell-a-skater.md of the research
   project, rules R2 and R3):

   1. The answer screen showed ALL the errors found as a list. But the deduction
      for GOE in ISU carry different weights, and one can act on only one. So the screen
      names the HEAVIEST by the objective scale, not the first in the array.

   2. The wording was about body parts: "a collapsed axis", "the free leg
      touched the ice". This is an INTERNAL focus of attention. A meta-analysis of 73 studies
      (Hedges g = 0.583 on holding, 95% CI [0.425, 0.741], PMID 34843301)
      favors an EXTERNAL focus — on the outcome of the movement.
      So every code has wording about the ice, the rotation and the exit, not about
      the leg, the axis or the torso.

   The scale — ISU Communication 2623, Season 2024/25, section III
   "Updated Guidelines in establishing GOE for errors", p. 11.
   Copy of the document: ctsu_2623.pdf,
   sha256[:16] = a4bad21c11621f98.

   Weight = the LOWER (worst) bound of the GOE deduction. We take the lower one, because the order
   of importance must match the worst possible consequence of an error,
   not the optimistic one.

   THE LIMIT OF THIS MODULE, stated plainly: it orders what the detector produced.
   The detector makes mistakes (falls were not
   flagged on any of the three falls). The correct order on
   faulty input gives a correctly worded falsehood. Fixing the
   detectors is a separate task.
   ══════════════════════════════════════════════════════════════════════ */
(function (root) {
  'use strict';

  /* code -> { goe: <lower bound of the deduction>, isu: <ISU wording>,
               en: <screen wording> } */
  var ISU = {
    fall:               { goe: -5, isu: 'Fall',
                          en: 'This one ended on the ice — the single biggest loss there is under ISU rules.' },
    two_foot_landing:   { goe: -4, isu: 'Landing on two feet in a jump',
                          en: 'You came down on both blades instead of one.' },
    step_out:           { goe: -4, isu: 'Stepping out of landing in a jump',
                          en: 'The exit did not hold: a second blade had to go down on the ice.' },
    downgraded:         { goe: -4, isu: 'Downgraded (sign <<)',
                          en: 'You were more than half a turn short of the full count.' },
    under_rotation:     { goe: -3, isu: 'Under-rotated (sign <)',
                          en: 'You were a bit more than a quarter turn short of the full count.' },
    wrong_edge:         { goe: -4, isu: 'Wrong edge take off F/Lz (sign "e")',
                          en: 'The entry ran on the opposite side of the blade from what this jump needs.' },
    quarter:            { goe: -2, isu: 'Landed on the quarter (sign q)',
                          en: 'You were a quarter turn short of the full count.' },
    tilted_axis:        { goe: -3, isu: 'Poor speed, height, distance, or air position',
                          en: 'The spin went off-square, so the turns came round more slowly.' },
    low_height:         { goe: -3, isu: 'Poor speed, height, distance, or air position',
                          en: 'There was little lift — not much time over the ice.' },
    touch_down:         { goe: -2, isu: 'Touch down with one hand or free foot',
                          en: 'Something brushed the ice on the way out. On the ISU scale this is the smallest item on the list.' },
    hand_down:          { goe: -2, isu: 'Touch down with one hand or free foot',
                          en: 'A hand went down to the ice to steady the exit.' },
    two_hands_down:     { goe: -3, isu: 'Touch down with both hands in a jump',
                          en: 'Both palms went down to the ice.' },
    stiff_landing_knee: { goe: -3, isu: 'Weak landing (bad pos./wrong edge/scratching etc)',
                          en: 'The weight came down hard — the impact was not absorbed.' },
    poor_takeoff:       { goe: -4, isu: 'Poor take-off',
                          en: 'The push off did not come from where it should: this jump did not start the way it starts.' },
    long_preparation:   { goe: -3, isu: 'Long preparation',
                          en: 'The approach dragged on before the jump itself.' },
    weak_landing:       { goe: -3, isu: 'Weak landing (bad pos./wrong edge/scratching etc)',
                          en: 'The exit came out wobbly and scraped the ice.' }
  };

  var CLEAN = 'No errors found in what could be checked.';

  var UNKNOWN_GOE = -1;   // a code missing from the ISU table: the lightest, but not zero

  /* The heaviest error by the ISU scale. Returns null if there are no errors.
     The order is stable: at equal weight, the one that came earlier wins. */
  function worstByIsu(errors) {
    if (!errors || !errors.length) return null;
    var best = null;
    for (var i = 0; i < errors.length; i++) {
      var code = String(errors[i]);
      var row = ISU[code];
      var goe = row ? row.goe : UNKNOWN_GOE;
      if (best === null || goe < best.goe) {
        best = { code: code, goe: goe, isu: row ? row.isu : null, known: !!row, order: i };
      }
    }
    return best;
  }

  /* A sentence for the screen — with an external focus.
     An empty or missing error list gives the statement "clean", and NOT
     an empty string: a screen without a main statement explains nothing. */
  function verdictSentence(errors) {
    var w = worstByIsu(errors);
    if (w === null) return CLEAN;
    var row = ISU[w.code];
    if (row) return row.en;
    /* An unknown code is NOT turned into a pretty phrase: we honestly say that
       the system named something we cannot explain in words. */
    return 'The system flagged something on this attempt but cannot put it into words.';
  }

  var API = { ISU: ISU, worstByIsu: worstByIsu, verdictSentence: verdictSentence,
              UNKNOWN_GOE: UNKNOWN_GOE };

  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.ISU_RANK = API;
})(typeof window !== 'undefined' ? window : globalThis);
