/* Comparison of two attempts: alignment by the measured take-off,
   synchronous playback, frame stepping, difference row by the band rule, and
   privacy: an analysis not from my log does not offer my attempts.
   Fixtures are real analyses supplied by tools/run_ui_gates.py. */
async page => {
  const all = __REAL_REPORT_FIXTURES__;
  const timed = all.filter(f => Number.isFinite(f.summary.t_s) && Number.isFinite(f.summary.landing_s)
    && f.summary.landing_s > f.summary.t_s);
  if (timed.length < 2) throw Error('Two fixtures with measured take-off and landing are required');
  const [A, B] = timed;
  /* Bytes of the same two videos (run_ui_gates) are served with Range, otherwise
     Chrome treats the video as non-seekable and currentTime stays 0 */
  const videos = __COMPARE_VIDEOS__;
  const serve = b64 => route => {
    const bytes = Buffer.from(b64, 'base64');
    const m = (route.request().headers()['range'] || '').match(/^bytes=(\d+)-(\d*)$/);
    if (m) {
      const s = Number(m[1]), e = Math.min(m[2] ? Number(m[2]) : bytes.length - 1, bytes.length - 1);
      return route.fulfill({status: 206, contentType: 'video/mp4', body: bytes.subarray(s, e + 1),
        headers: {'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${s}-${e}/${bytes.length}`}});
    }
    return route.fulfill({contentType: 'video/mp4', body: bytes, headers: {'Accept-Ranges': 'bytes'}});
  };
  const checks = [], errors = [];
  const near = (x, y, tol) => Math.abs(x - y) <= tol;
  /* Expected difference uses the same rule as the product: |Δ| > ±A + ±B */
  const half = band => Array.isArray(band) && band.length === 2 ? (band[1] - band[0]) / 2 : null;
  const expectAirDiff = (() => {
    const ha = half(A.summary.air_band), hb = half(B.summary.air_band);
    if (ha == null || hb == null) return null;
    return Math.abs(B.summary.air_s - A.summary.air_s) > ha + hb ? 'differs' : 'within';
  })();
  /* English only; a stored 'uk' choice in localStorage is ignored. */
  for (const width of [320, 390]) for (const lang of ['en']) for (const mine of [true, false]) {
    const context = await page.context().browser().newContext({viewport: {width, height: 844}, isMobile: true, hasTouch: true});
    const tab = await context.newPage();
    tab.on('pageerror', e => errors.push(e.message));
    const row = (f, job) => ({...f.summary, jump: f.summary.name, job, stem: f.summary.stem, ts: 1791400000, state: 'done'});
    await tab.route('**/coach/**', route => {
      const path = new URL(route.request().url()).pathname.replace('/coach', '');
      if (['/me', '/auth/guest'].includes(path)) return route.fulfill({json: {uid: 'compare_ui_123', role: 'skater', code: 'CMP123'}});
      /* mine=false: the coach views a student's analysis; this job is not in THAT student's log. */
      if (path === '/history') return route.fulfill({json: mine ? [row(A, 'cmp_a'), row(B, 'cmp_b')] : [row(B, 'cmp_b')]});
      return route.fulfill({json: []});
    });
    await tab.route('**/summary/cmp_a', route => route.fulfill({json: {fps: 30, jumps: [A.summary]}}));
    await tab.route('**/summary/cmp_b', route => route.fulfill({json: {fps: 30, jumps: [B.summary]}}));
    await tab.route('**/media/cmp_a/**', serve(videos[0]));
    await tab.route('**/media/cmp_b/**', serve(videos[1]));
    await tab.route('**/data/**', route => route.fulfill({json: A.result}));
    try {
      await tab.goto('http://127.0.0.1:8029');
      await tab.waitForFunction(() => window.APP?.currentUid());
      await tab.evaluate(async () => await window.APP.openJob('cmp_a'));
      await tab.locator('#scr-answer').waitFor({state: 'visible'});
      if (await tab.locator('#btn-compare').evaluate(e => e.hidden)) throw Error('Compare button is missing despite measured phases');
      await tab.locator('#btn-tools-toggle').click();
      await tab.locator('#btn-compare').click();
      await tab.locator('#sheet-compare').waitFor({state: 'visible'});
      await tab.waitForFunction(() => !document.getElementById('cmp-pick').disabled || !document.getElementById('cmp-empty').hidden);
      const options = await tab.evaluate(() => [...document.getElementById('cmp-pick').options].map(o => o.textContent));
      if (!mine) {
        const empty = await tab.evaluate(() => !document.getElementById('cmp-empty').hidden);
        if (options.length || !empty) throw Error(`Foreign analysis received attempts from my log: ${JSON.stringify(options)}`);
        checks.push({width, lang, mine, options});
        continue;
      }
      if (options.length !== 1) throw Error(`Expected one attempt from the log: ${JSON.stringify(options)}`);
      await tab.waitForFunction(() => ['cmp-video-a', 'cmp-video-b'].every(id => document.getElementById(id).readyState >= 2));
      await tab.waitForTimeout(400);
      const read = () => tab.evaluate(() => {
        const a = document.getElementById('cmp-video-a'), b = document.getElementById('cmp-video-b');
        return {a: a.currentTime, b: b.currentTime, pa: a.paused, pb: b.paused,
          overflow: document.documentElement.scrollWidth > innerWidth,
          diff: document.getElementById('cmp-diff').innerText, facts: document.getElementById('cmp-facts-b').innerText};
      });
      const rel = s => [s.a - A.summary.t_s, s.b - B.summary.t_s];
      const s0 = await read();
      const [ra0, rb0] = rel(s0);
      if (!near(ra0, rb0, 0.04)) throw Error(`Not aligned by take-off: ${ra0} / ${rb0}`);
      await tab.locator('#cmp-play').click();
      await tab.waitForTimeout(900);
      const s1 = await read();
      const [ra1, rb1] = rel(s1);
      if (s1.pa || !(ra1 > ra0) || !near(ra1, rb1, 0.12)) throw Error(`Playback is not synchronous: ${JSON.stringify({ra0, ra1, rb1, s1})}`);
      await tab.locator('#cmp-play').click();
      await tab.waitForTimeout(250);
      const s2 = await read();
      await tab.locator('#cmp-frame-next').click();
      await tab.waitForTimeout(250);
      const s3 = await read();
      const [ra2, rb2] = rel(s2), [ra3, rb3] = rel(s3);
      if (!s3.pa || !s3.pb || !near(ra3 - ra2, 1 / 30, 0.01) || !near(ra3, rb3, 0.02))
        throw Error(`Frame ▶ does not step both videos: ${JSON.stringify({ra2, ra3, rb3})}`);
      if (s3.overflow) throw Error('Horizontal overflow in the compare sheet');
      if (expectAirDiff) {
        const within = /within the measurement error/.test(s3.diff);
        if ((expectAirDiff === 'within') !== within) throw Error(`Difference row contradicts the bands: ${s3.diff}`);
      }
      // A number without a band is an error; B with no measurements (all '—') is honest, so the comparison is video only.
      if (/\d\s*(s|cm)\b/.test(s3.facts) && !/±/.test(s3.facts)) throw Error('Measurements of B without a ± band: ' + JSON.stringify(s3.facts));
      const cyr = await tab.evaluate(() => (document.getElementById('sheet-compare').innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g) || []).slice(0, 5));
      if (cyr.length) throw Error(`Cyrillic in the compare sheet: ${JSON.stringify(cyr)}`);
      await tab.keyboard.press('Escape');
      const closed = await tab.evaluate(() => document.getElementById('sheet-compare').hidden
        && document.getElementById('cmp-video-a').paused && document.getElementById('cmp-video-b').paused);
      if (!closed) throw Error('Closing did not stop the video');
      checks.push({width, lang, mine, options, aligned: +(ra0 - rb0).toFixed(3), synced: +(ra1 - rb1).toFixed(3)});
    } finally { await context.close(); }
  }
  if (errors.length) throw Error(errors.join('; '));
  return {pair: [A.original, B.original], expectAirDiff, checks};
}
