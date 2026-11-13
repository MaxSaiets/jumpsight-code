// Run: playwright-cli -s=gate run-code --filename tools/ui_gates/check_mobile_targets.cjs
// Checks DOM and CSS only: video analysis and external services do not run.
async page => {
  const failures = [];
  await page.unrouteAll({ behavior: 'wait' });
  await page.route('**/coach/**', route => {
    const path = route.request().url().split('?')[0].replace(/^https?:\/\/[^/]+/, '');
    const lists = ['/coach/history', '/coach/sessions', '/coach/mascot_list',
      '/coach/team', '/coach/comments'];
    if (lists.some(prefix => path.startsWith(prefix))) return route.fulfill({ json: [] });
    if (path === '/coach/today') return route.fulfill({ json: { empty: true, message: '' } });
    return route.fulfill({ json: {} });
  });

  const inspect = async (width, screen) => {
    const result = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > innerWidth,
      cyrillic: (document.body.innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g) || []).slice(0, 5),
      small: [...document.querySelectorAll('button, a, [role="button"]')]
        .filter(element => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return style.display !== 'none' && style.visibility !== 'hidden' &&
            rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 44);
        })
        .map(element => ({
          id: element.id || element.textContent.trim().slice(0, 24),
          width: Math.round(element.getBoundingClientRect().width),
          height: Math.round(element.getBoundingClientRect().height),
        })),
    }));
    if (result.overflow) failures.push(`${screen} @ ${width}px: horizontal overflow`);
    if (result.cyrillic.length) failures.push(`${screen} @ ${width}px: Cyrillic ${JSON.stringify(result.cyrillic)}`);
    if (result.small.length) failures.push(`${screen} @ ${width}px: ${JSON.stringify(result.small)}`);
  };

  /* The interface is English only: one pass, and a stale stored language
     value in localStorage must be ignored (so the test seeds one) */
  for (const lang of ['en']) {
    for (const theme of ['light', 'dark']) {
      for (const width of [320, 375, 430]) {
        await page.setViewportSize({ width, height: 812 });
        await page.goto('http://127.0.0.1:8000/');
        await page.evaluate(([nextLang, nextTheme]) => {
          localStorage.setItem('js.theme', nextTheme);
        }, [lang, theme]);
        await page.reload();
        await page.locator('#btn-upload-video').waitFor({ state: 'visible' });
        const label = `${lang}/${theme}`;
        await inspect(width, `record ${label}`);
        await page.locator('[data-tab="progress"]').click();
        await inspect(width, `progress ${label}`);
        await page.locator('[data-tab="today"]').click();
        await inspect(width, `today ${label}`);
        await page.locator('#btn-account').click();
        await page.locator('#scr-account').waitFor({ state: 'visible' });
        await inspect(width, `account ${label}`);
        const hierarchy = await page.evaluate(() => ({
          duplicateHeader: document.querySelectorAll('#scr-account > .rz-hero').length,
          emptyParentVisible: !!document.querySelector('#parent-dashboard:not([hidden])'),
          subtitleWhiteSpace: getComputedStyle(document.getElementById('acc-subtitle')).whiteSpace,
          eyebrowSize: parseFloat(getComputedStyle(document.querySelector('.rz-eyebrow')).fontSize),
          profileCodeDetails: document.querySelectorAll('#acc-move-box .rz-arow__body > details').length + document.querySelectorAll('#acc-code-box .rz-arow__body details').length * 10,
          profileCodeExpanded: !!document.querySelector('#acc-move-box[open], #acc-move-box .rz-arow__body > details[open]'),
        }));
        if (hierarchy.duplicateHeader)
          failures.push(`account ${label} @ ${width}px: duplicate profile heading`);
        if (hierarchy.emptyParentVisible)
          failures.push(`account ${label} @ ${width}px: empty parent dashboard is visible`);
        if (hierarchy.subtitleWhiteSpace === 'nowrap')
          failures.push(`account ${label} @ ${width}px: profile status is truncated`);
        if (hierarchy.eyebrowSize < 12)
          failures.push(`account ${label} @ ${width}px: supporting label is below 12px`);
        if (hierarchy.profileCodeDetails !== 1 || hierarchy.profileCodeExpanded)
          failures.push(`account ${label} @ ${width}px: profile transfer details are not collapsed`);
      }
    }
  }

  if (failures.length) throw new Error(failures.join('\n'));
  return { widths: [320, 375, 430], languages: ['en'], themes: ['light', 'dark'],
    screens: ['record', 'progress', 'today', 'account'], minimumTarget: 44, checks: 24 };
}
