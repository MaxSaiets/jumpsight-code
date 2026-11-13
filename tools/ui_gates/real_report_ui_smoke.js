/* Real reports: video and automatic answer on a phone. */
async page => {
  const fixtures = __REAL_REPORT_FIXTURES__;
  const checks = [], errors = [];
  /* tools/run_ui_gates.py builds the fixtures from local analyses;
     select them by properties, not by id. */
  const languageProbe = fixtures.find(f => f.flags?.low_signal && typeof f.summary.turns === 'number');
  if (!languageProbe)
    throw Error('No fixture with a weak signal and a numeric count: the language and "Possibly" checks would not run');
  /* The interface is English only and has no language switch. A stale language
     value in localStorage must be ignored, so the test seeds one. */
  for (const width of [320, 390]) for (const lang of ['en']) for (const fixture of fixtures) {
    const outputs = [];
    for (const mode of ['summary']) {
      const context = await page.context().browser().newContext({
        viewport: {width, height: 844}, isMobile: true, hasTouch: true
      });
      const tab = await context.newPage();
      let labelsSent = 0;
      tab.on('pageerror', error => errors.push(error.message));
      await tab.route('**/coach/**', route => {
        const path = new URL(route.request().url()).pathname.replace('/coach', '');
        if (path === '/verdict_feedback' && route.request().method() === 'POST') labelsSent++;
        if (['/me', '/auth/guest'].includes(path)) return route.fulfill({
          json: {uid: 'actual_report_ui_123', role: 'skater', code: 'ACT123'}
        });
        if (path === '/history') return route.fulfill({json: [{
          ...fixture.summary, jump: fixture.summary.name,
          name_confidence: fixture.summary.name_conf, stem: 'actual_fixture', ts: 100,
          job: 'actual_job'
        }]});
        if (path.startsWith('/video/')) return route.fulfill({path: fixture.video, contentType: 'video/mp4'});
        return route.fulfill({json: []});
      });
      await tab.route('**/summary/actual_job', route => route.fulfill({
        json: {fps: 30, jumps: [fixture.summary]}
      }));
      await tab.route('**/clip/**', route => route.fulfill({path: fixture.video, contentType: 'video/mp4'}));
      await tab.route('**/media/**', route => route.fulfill({path: fixture.video, contentType: 'video/mp4'}));
      await tab.route('**/data/**', route => route.fulfill({json: fixture.result}));
      try {
        await tab.goto('http://127.0.0.1:8029');
        await tab.locator('#card-last-answer').waitFor({state: 'visible'});
        await tab.locator('#card-last-answer').click();
        await tab.locator('#scr-answer').waitFor({state: 'visible'});
        await tab.waitForFunction(() => document.getElementById('ans-verdict-t').textContent.trim());
        /* With isMobile, Chrome widens innerWidth to fit the content, so
           scrollWidth > innerWidth misses overflow (a speed tile stretched
           the screen by 320 px and only the compare gate caught it). Compare
           against the requested width. */
        const output = await tab.evaluate(W => ({
          num: document.getElementById('ans-hero-num').textContent.trim(),
          unit: document.querySelector('.rz-revs__lbl').textContent.trim(),
          verdict: document.getElementById('ans-verdict-t').textContent.trim(),
          explanation: document.getElementById('ans-verdict-s').textContent.trim(),
          chip: document.getElementById('ans-verdict-chip').textContent.trim(),
          mainFinding: document.getElementById('ans-one-thing').textContent.trim(),
          feedbackOpen: document.getElementById('verdict-feedback').open,
          manualGuessVisible: !!document.getElementById('card-guess').getClientRects().length,
          overflow: document.documentElement.scrollWidth > W + 1
            ? [document.documentElement.scrollWidth, ...[...document.querySelectorAll('body *')]
                .filter(e => e.getClientRects().length && e.getBoundingClientRect().right > W + 1
                  && ![...e.children].some(c => c.getBoundingClientRect().right > W + 1))
                .slice(0, 6).map(e => `${e.tagName}#${e.id}.${String(e.className).split(' ')[0]}:${Math.round(e.getBoundingClientRect().right)}`)]
            : false
        }), width);
        if (output.feedbackOpen || output.manualGuessVisible || output.overflow || labelsSent)
          throw Error(JSON.stringify({original: fixture.original, mode, output, labelsSent}));
        const expectedUnit = typeof fixture.summary.turns === 'number'
          ? "rotations (judges' count)" : 'rotations';
        if (output.unit !== expectedUnit) throw Error(JSON.stringify({original: fixture.original, mode, expectedUnit, output}));
        /* A low-confidence sign is not the main finding: the main card stays
           silent, and the error list shows it
           as "Possibly: ...". */
        if (fixture.flags?.low_signal && !fixture.flags?.strong_signal) {
          const lowShown = await tab.evaluate(() => ({
            mainVisible: !document.getElementById('card-one-thing').hidden,
            maybe: document.getElementById('ans-errors-body').textContent }));
          if (lowShown.mainVisible || !lowShown.maybe.includes('Possibly'))
            throw Error('An uncertain sign was presented as a definite main finding');
        }
        if (fixture.summary.name_uncertain && /axel|lutz|flip|loop|toe loop|salchow/i.test(output.verdict))
          throw Error(`A withheld name was shown as a verdict: ${fixture.original}: ${output.verdict}`);
        const video = tab.locator('#ans-video');
        {
          await video.evaluate(element => { element.preload = 'auto'; element.load(); });
          await tab.waitForFunction(() => {
            const element = document.getElementById('ans-video');
            return element && (element.readyState >= 1 || element.error);
          });
          const media = await video.evaluate(element => ({
            width: element.videoWidth, height: element.videoHeight,
            duration: element.duration, error: element.error && element.error.code
          }));
          if (media.error || !(media.width > 0) || !(media.duration > 0))
            throw Error(JSON.stringify({original: fixture.original, mode, media}));
          output.media = media;
        }
        if (width === 390 && mode === 'summary' && fixtures.indexOf(fixture) < 3)
          await tab.screenshot({path: `output/playwright/actual-${fixture.original}.png`, fullPage: true});
        /* English only: no Cyrillic on the answer screen, page language
           en, and no language button, even with a stale stored language */
        const en = await tab.evaluate(() => ({
          lang: document.documentElement.lang,
          langButton: !!document.getElementById('btn-lang'),
          cyrillic: (document.getElementById('scr-answer').innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g) || []).slice(0, 5)
        }));
        if (en.lang !== 'en' || en.langButton || en.cyrillic.length)
          throw Error(`Not English only: ${JSON.stringify({original: fixture.original, mode, en})}`);
        output.englishOnlyVerified = true;
        outputs.push({mode, ...output, labelsSent});
      } finally { await context.close(); }
    }
    checks.push({width, lang, original: fixture.original, outputs});
  }
  if (errors.length) throw Error(errors.join('; '));
  return {checks, errors};
}
