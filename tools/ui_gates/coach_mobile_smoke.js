/* Coach scenarios with a controlled API; private data is not changed. */
async page => {
  const context = await page.context().browser().newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const tab = await context.newPage();
  const checks = [], errors = [];
  let teamFails = false, historyFails = false, focusCalls = 0;
  const students = [
    { uid: 'student_one_123', name: 'Alexandra Kovalchuk-Doroshenko', code: 'AAA111', new: 2, days_since: 0, stuck: ['landing_stability'], last: { job: 'fixture_job', jump: 'Axel', count_named: 'single', errors: ['step_out'] } },
    { uid: 'student_two_123', name: 'Mark', code: 'BBB222', new: 0, days_since: 8, stuck: [], coach_focus: { goal: 'landing_stability' } },
    { uid: 'student_three_123', name: 'Irina <new student>', code: 'CCC333', new: 0, days_since: null, stuck: [] }
  ];
  tab.on('pageerror', e => errors.push(e.message));
  /* The interface is English only; an old 'uk' choice is ignored.
     count_named in the journal is deliberately raw text, and the client translates it. */
  const cyrillic = sel => tab.evaluate(s => (document.querySelector(s).innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g) || []).slice(0, 5), sel);
  await tab.route('**/coach/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/coach', '');
    if (path === '/me' || path === '/auth/guest') return route.fulfill({ json: { uid: 'coach_mobile_123', role: 'coach', name: 'Coach', code: 'COA111' } });
    if (path === '/team') return route.fulfill(teamFails ? { status: 503, json: { detail: 'fixture outage' } } : { json: students });
    if (path === '/goals') return route.fulfill({ json: [{ code: 'landing_stability', label: 'Stable landing' }] });
    if (path.endsWith('/history') && path.startsWith('/team/')) return route.fulfill(historyFails ? { status: 503, json: {} } : { json: [
      { job: 'fixture_job', jump: 'Axel', count_named: 'single', errors: [], clean: true, ts: 1790700000 },
      { job: 'refused_job', jump: null, count_named: 'triple', count_supported: false, ts: 1790600000 }
    ] });
    if (path.endsWith('/focus')) { focusCalls++; const body = route.request().postDataJSON(); students[0].coach_focus = { goal: body.goal }; return route.fulfill({ json: { ok: true } }); }
    if (['/history', '/sessions', '/team/pending', '/mascot_list'].includes(path)) return route.fulfill({ json: [] });
    return route.fulfill({ json: {} });
  });
  const check = (ok, name) => { if (!ok) throw new Error(name); checks.push(name); };
  try {
    await tab.goto('http://127.0.0.1:8029');
    await tab.locator('.rz-team__row').first().waitFor();
    check(await tab.locator('[data-tab="team"]').isVisible(), 'Coach has its own navigation');
    check(!await tab.locator('[data-tab="record"]').isVisible(), 'The athlete scenario is not mixed with the coach');
    check(await tab.locator('#team-list button').count() === 3, 'All students are visible');
    await tab.evaluate(() => window.APP.go('record'));
    check(await tab.locator('#scr-team').isVisible(), 'Old athlete URL returns the coach to the team');
    await tab.locator('[data-team-filter="new"]').click();
    check(await tab.locator('#team-list button').count() === 1, 'New analyses filter');
    await tab.locator('[data-team-filter="all"]').click();
    await tab.locator('#team-search').fill('CCC333');
    check(await tab.locator('#team-list button').count() === 1, 'Search by code');
    check((await tab.locator('#team-list').innerText()).includes('<new student>'), 'Name is shown as text');
    await tab.locator('#team-search').fill('nonexistent');
    check(await tab.locator('#team-state').isVisible(), 'Empty search shows an explanation');
    await tab.locator('#team-search').fill('');
    await tab.locator('#team-invite summary').click();
    check(await tab.locator('#team-empty-student-code').isVisible(), 'Invite is available with existing students');
    await tab.locator('#team-invite summary').click();
    for (const width of [320, 390, 768, 1024, 1440]) {
      await tab.setViewportSize({ width, height: 900 });
      check(await tab.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `No overflow at ${width}px`);
      const smallControls = await tab.locator('#scr-team button:visible, #scr-team summary:visible').evaluateAll(elements => elements.filter(el => el.getBoundingClientRect().height < 44).map(el => el.textContent));
      check(!smallControls.length, `Buttons at least 44px at ${width}px: ${smallControls.join(', ')}`);
    }
    await tab.setViewportSize({ width: 390, height: 844 });
    await tab.screenshot({ path: 'output/playwright/coach-mobile-dashboard.png', fullPage: false });
    historyFails = true;
    await tab.locator('.rz-team__row').first().click();
    await tab.locator('#sheet-student-rows button').waitFor();
    check((await tab.locator('#sheet-student-rows').innerText()).includes('could not be loaded'), 'Log error does not look like missing attempts');
    historyFails = false;
    await tab.locator('#sheet-student-rows button').click();
    await tab.locator('#sheet-student-rows [data-job]').first().waitFor();
    check((await tab.locator('#sheet-student-rows [data-job="refused_job"]').innerText()).includes('not resolved'), 'Refused analysis is available in the log');
    check(!(await tab.locator('#sheet-student-rows [data-job="refused_job"]').innerText()).includes('triple'), 'Unconfirmed count is not shown');
    check(!(await cyrillic('#sheet-student')).length, `Student sheet has no Cyrillic: ${JSON.stringify(await cyrillic('#sheet-student'))}`);
    await tab.locator('#student-focus-sel').selectOption('landing_stability');
    await tab.locator('#student-focus-save').click();
    check(focusCalls === 1, 'Focus assignment calls the API');
    await tab.locator('#btn-close-student-sheet').focus();
    await tab.keyboard.press('Shift+Tab');
    check(await tab.evaluate(() => document.getElementById('sheet-student').contains(document.activeElement)), 'Focus stays in the dialog');
    await tab.screenshot({ path: 'output/playwright/coach-mobile-student.png', fullPage: false });
    await tab.keyboard.press('Escape');
    check(!await tab.locator('#sheet-student').isVisible(), 'Escape closes the student sheet');
    check(await tab.evaluate(() => document.activeElement.classList.contains('rz-team__row')), 'Closing returns focus to the student row');
    teamFails = true;
    await tab.locator('[data-tab="account"]').click();
    await tab.locator('[data-tab="team"]').click();
    await tab.locator('#team-state button').waitFor();
    check(!await tab.locator('#team-empty').isVisible(), 'Team error is not an empty team');
    teamFails = false;
    await tab.locator('#team-state button').click();
    await tab.locator('.rz-team__row').first().waitFor();
    check(await tab.locator('.rz-team__row').count() === 3, 'Retry loads the team');
    check(!await tab.locator('#btn-lang').count() && await tab.evaluate(() => document.documentElement.lang === 'en'), 'English only: no language switcher');
    await tab.waitForFunction(() => document.querySelector('#team-result-count').textContent.includes('Showing'));
    check((await tab.locator('#team-tools').innerText()).includes('New analyses'), 'English coach navigation');
    check((await tab.locator('#team-list').innerText()).includes('Stable landing'), 'Focus in English');
    check(!(await cyrillic('#scr-team')).length, `Team screen has no Cyrillic: ${JSON.stringify(await cyrillic('#scr-team'))}`);
    /* Theme switch lives only in Profile; the header is kept light. */
    await tab.evaluate(() => document.querySelector('.theme-b[data-theme="dark"]').click());
    check(await tab.evaluate(() => document.documentElement.dataset.theme === 'dark' || document.documentElement.classList.contains('dark')), 'Dark theme is available');
    check(await tab.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Dark English layout has no overflow');
    await tab.screenshot({ path: 'output/playwright/coach-mobile-dark-en.png', fullPage: false });
    check(!errors.length, `No pageerror: ${errors.join('; ')}`);
    return checks;
  } finally { await context.close(); }
}
