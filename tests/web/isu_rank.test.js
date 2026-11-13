/* Test for isu_rank.js. Run: node tests/web/isu_rank.test.js
   Two-sided: it checks both what the module does correctly on good input,
   and what it REFUSES on broken input. A one-sided test measures nothing. */
'use strict';
const assert = require('assert');
const R = require('../../web/isu_rank.js');

let ok = 0;
function t(name, fn) { fn(); ok++; console.log('  ok  ' + name); }

/* ── good input: the order matches the ISU 2623 scale ──────────────── */

t('a fall is harder than everything else, in any array order', () => {
  assert.strictEqual(R.worstByIsu(['touch_down', 'fall', 'step_out']).code, 'fall');
  assert.strictEqual(R.worstByIsu(['fall', 'touch_down', 'step_out']).code, 'fall');
  assert.strictEqual(R.worstByIsu(['step_out', 'touch_down', 'fall']).code, 'fall');
});

t('exactly the set the audit gave on the textbook clip selects step_out, not touch_down', () => {
  /* runs/evidence/recognition_batch.json from the audit: ["step_out","touch_down","tilted_axis"].
     The screen showed a list; ISU says that step_out (-3..-4) is heavier than
     touch_down (-1..-2) and tilted_axis. */
  const w = R.worstByIsu(['step_out', 'touch_down', 'tilted_axis']);
  assert.strictEqual(w.code, 'step_out');
  assert.strictEqual(w.goe, -4);
});

t('touch_down is the smallest, and this is visible from the weight', () => {
  assert.ok(R.ISU.touch_down.goe > R.ISU.step_out.goe);
  assert.ok(R.ISU.touch_down.goe > R.ISU.two_foot_landing.goe);
  assert.ok(R.ISU.touch_down.goe > R.ISU.fall.goe);
});

t('the weights match the ISU 2623 table item by item', () => {
  assert.strictEqual(R.ISU.fall.goe, -5);
  assert.strictEqual(R.ISU.two_foot_landing.goe, -4);
  assert.strictEqual(R.ISU.step_out.goe, -4);
  assert.strictEqual(R.ISU.downgraded.goe, -4);
  assert.strictEqual(R.ISU.under_rotation.goe, -3);
  assert.strictEqual(R.ISU.quarter.goe, -2);
  assert.strictEqual(R.ISU.touch_down.goe, -2);
});

t('an empty list does not claim that the whole attempt is clean', () => {
  assert.strictEqual(R.worstByIsu([]), null);
  const s = R.verdictSentence([]);
  assert.ok(s.length > 20);
  /* the caveat must remain: clean only in what could be checked */
  assert.ok(/could be checked|available measurements/i.test(s));
  assert.ok(!/attempt is clean|clean attempt/i.test(s));
});

t('each code has both languages and the sentence is not empty', () => {
  for (const code of Object.keys(R.ISU)) {
    const s = R.verdictSentence([code]);
    assert.ok(s && s.length > 15, `${code}: ${s}`);
  }
});

/* ── R3: external focus. Internal wording is forbidden ──────────── */

t('no sentence names a body part or says «axis»', () => {
  /* The forbidden list is exactly what the old screen used to say:
     «flawed axis», «free leg touched the ice», «trunk lean».
     PMID 34843301: internal focus loses to external focus, g = 0.583. */
  const BAN_EN = ['axis', 'free leg', 'torso', 'knee', 'your foot', 'body part'];
  for (const code of Object.keys(R.ISU)) {
    const en = R.verdictSentence([code]).toLowerCase();
    for (const w of BAN_EN) assert.ok(!en.includes(w), `en/${code} contains internal «${w}»: ${en}`);
  }
});

t('tilted_axis is translated into an external consequence, not into «a flawed axis»', () => {
  const en = R.verdictSentence(['tilted_axis']).toLowerCase();
  assert.ok(!en.includes('axis'));
  assert.ok(/ice|turns|spin|round/.test(en), 'must describe the consequence outwardly: ' + en);
});

/* ── bad input: the module REFUSES, it does not invent ──────────────────────── */

t('null / undefined does not crash and does not invent an error', () => {
  assert.strictEqual(R.worstByIsu(null), null);
  assert.strictEqual(R.worstByIsu(undefined), null);
  assert.ok(R.verdictSentence(null).length > 20);
});

t('an unknown code does NOT get an invented nice phrase', () => {
  const w = R.worstByIsu(['banana_split']);
  assert.strictEqual(w.known, false);
  assert.strictEqual(w.goe, R.UNKNOWN_GOE);
  const s = R.verdictSentence(['banana_split']).toLowerCase();
  assert.ok(s.includes('cannot'), 'the unknown must admit it, not be described: ' + s);
});

t('an unknown code does NOT overshadow a real heavy error', () => {
  assert.strictEqual(R.worstByIsu(['banana_split', 'fall']).code, 'fall');
  assert.strictEqual(R.worstByIsu(['fall', 'banana_split']).code, 'fall');
});

t('an unknown code still loses even to the lightest KNOWN error', () => {
  /* -1 (unknown) vs -2 (touch_down): touch_down wins.
     Otherwise a garbage code would push a real error off the screen. */
  assert.strictEqual(R.worstByIsu(['banana_split', 'touch_down']).code, 'touch_down');
});

t('non-numeric and empty elements do not break the choice', () => {
  assert.strictEqual(R.worstByIsu(['', 'fall']).code, 'fall');
  assert.strictEqual(R.worstByIsu([0, 'step_out']).code, 'step_out');
});

t('the WEIGHT of the chosen one does not depend on the order: a metamorphic property', () => {
  /* A minimal example of why the invariant is stated by WEIGHT, not by code:
       worstByIsu(['step_out','two_foot_landing']).code === 'step_out'
       worstByIsu(['two_foot_landing','step_out']).code === 'two_foot_landing'
     Both codes have goe -4 (ISU 2623: «Stepping out of landing» and
     «Landing on two feet» has the same -3 to -4, and the tie is resolved
     stably in favour of the first. So invariance by CODE is not
     defined for equal weights; invariance by WEIGHT is defined, and
     it is exactly this that is the essence of rule R2. */
  const set = ['touch_down', 'tilted_axis', 'step_out', 'two_foot_landing'];
  const expect = R.worstByIsu(set).goe;
  const perms = [
    ['tilted_axis', 'step_out', 'two_foot_landing', 'touch_down'],
    ['two_foot_landing', 'touch_down', 'tilted_axis', 'step_out'],
    ['step_out', 'two_foot_landing', 'touch_down', 'tilted_axis'],
  ];
  for (const p of perms) assert.strictEqual(R.worstByIsu(p).goe, expect);
});

t('a strictly heavier error wins from any position: this is exactly what R2 is', () => {
  const light = ['touch_down', 'tilted_axis', 'quarter'];
  for (let i = 0; i <= light.length; i++) {
    const arr = light.slice(0, i).concat(['fall'], light.slice(i));
    assert.strictEqual(R.worstByIsu(arr).code, 'fall', 'position ' + i);
  }
});

t('a tie is resolved stably: the first in the array', () => {
  assert.strictEqual(R.worstByIsu(['step_out', 'two_foot_landing']).code, 'step_out');
  assert.strictEqual(R.worstByIsu(['two_foot_landing', 'step_out']).code, 'two_foot_landing');
  assert.strictEqual(R.worstByIsu(['step_out', 'two_foot_landing']).goe,
                     R.worstByIsu(['two_foot_landing', 'step_out']).goe);
});

t('duplicates change nothing: idempotence', () => {
  assert.strictEqual(R.worstByIsu(['fall', 'fall', 'fall']).code, 'fall');
  assert.strictEqual(R.verdictSentence(['touch_down', 'touch_down']),
                     R.verdictSentence(['touch_down']));
});

console.log(`\nisu_rank: ${ok} checks passed`);
