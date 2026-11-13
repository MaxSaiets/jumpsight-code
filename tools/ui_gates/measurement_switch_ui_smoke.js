/* An old numeric RAF cannot overwrite another attempt's result. */
async page => {
  const source = __REAL_REPORT_FIXTURES__;
  const appOverride = __APP_JS_OVERRIDE__;
  // Clips 94_* are no longer on this machine; fixtures are built by
  // tools/run_ui_gates.py from local analyses. This checks switching
  // attempts (the old RAF does not overwrite the new number), not counting accuracy,
  // so counts 4 / 2 / ≈3 are set explicitly over the real report shape.
  const first = source.find(value => typeof value.summary.turns === 'number') || source[0];
  const second = source.find(value => value !== first) || first;
  const rows = [{...first.summary, turns: 4, turns_nominal: 4, estimated: false, stem: 'initial_attempt', rank: 0},
    {...first.summary, turns: 2, turns_nominal: 2, estimated: false, stem: 'first_attempt', rank: 1},
    {...second.summary, turns: 3, turns_nominal: 3, estimated: true, stem: 'second_attempt', rank: 2}];
  const checks = [];
  /* English only; a stored 'uk' choice is ignored. */
  for (const width of [320, 390]) for (const lang of ['en']) {
    const context = await page.context().browser().newContext({viewport: {width, height: 844}, reducedMotion: 'no-preference'});
    const tab = await context.newPage();
    let servedOverride = 0;
    if (appOverride) await tab.route('**/static/app.js*', route => {
      servedOverride++;
      return route.fulfill({path: appOverride, contentType: 'application/javascript'});
    });
    await tab.route('**/coach/**', route => {
      const path = new URL(route.request().url()).pathname.replace('/coach', '');
      if (['/me', '/auth/guest'].includes(path)) return route.fulfill({json: {uid: 'number_switch_ui_123', role: 'skater', code: 'NUM123'}});
      if (path === '/history') return route.fulfill({json: [{...rows[0], jump: rows[0].name, job: 'switch_job', ts: 100}]});
      return route.fulfill({json: []});
    });
    await tab.route('**/summary/switch_job', route => route.fulfill({json: {fps: 30, jumps: rows}}));
    await tab.route('**/media/**', route => route.fulfill({path: first.video, contentType: 'video/mp4'}));
    await tab.route('**/data/**', route => route.fulfill({json: first.result}));
    try {
      await tab.goto('http://127.0.0.1:8029');
      if (appOverride && !servedOverride) throw Error('Isolated override of the old JS was not applied');
      await tab.locator('#card-last-answer').click();
      await tab.locator('#ans-attempt-nav').waitFor({state: 'visible'});
      await tab.locator('#btn-att-next').dblclick();
      const sampled = await tab.evaluate(async () => {
        const values = [];
        const start = performance.now();
        await new Promise(resolve => {
          const read = now => {
            values.push(document.getElementById('ans-hero-num').textContent.trim());
            if (now - start >= 900) resolve(); else requestAnimationFrame(read);
          };
          requestAnimationFrame(read);
        });
        return [...new Set(values)];
      });
      if (sampled.length !== 1 || sampled[0] !== '≈3')
        throw Error(JSON.stringify({width, lang, sampled, expected: '≈3'}));
      const cyr = await tab.evaluate(() => (document.getElementById('scr-answer').innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g) || []).slice(0, 5));
      if (cyr.length) throw Error(`Cyrillic on the answer screen: ${JSON.stringify(cyr)}`);
      checks.push({width, lang, sampled});
    } finally { await context.close(); }
  }
  return {checks};
}
