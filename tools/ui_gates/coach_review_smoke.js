/* Explicit review: GET does not confirm; a POST failure does not hide the new state. */
async page => {
  const context = await page.context().browser().newContext({ viewport: { width: 320, height: 800 }, isMobile: true, hasTouch: true });
  const tab = await context.newPage(), checks = [], errors = [];
  let status = 'pending', fail = false, conflict = false, posts = 0, reads = 0;
  let version = 'a'.repeat(64);
  tab.on('pageerror', e => errors.push(e.message));
  /* English-only UI; a stored 'uk' choice is ignored. */
  await tab.route('**/coach/**', route => {
    const path = new URL(route.request().url()).pathname.replace('/coach', '');
    if (path === '/me' || path === '/auth/guest') return route.fulfill({ json: { uid: 'coach_review_123', role: 'coach', code: 'COA123' } });
    if (path === '/team') return route.fulfill({ json: [{ uid: 'student_review_123', name: 'Student', code: 'STU123', new: status === 'pending' ? 1 : 0 }] });
    if (path.endsWith('/history') && path.startsWith('/team/')) { reads++; return route.fulfill({ json: [{ job: 'job_review_123', ts: 1790700000, jump: 'Axel', review_version: version, review_status: status }] }); }
    if (path.endsWith('/review')) {
      posts++;
      if (fail) return route.fulfill({ status: 503, json: {} });
      if (conflict) { conflict = false; version = 'b'.repeat(64); return route.fulfill({ status: 409, json: {} }); }
      const body = route.request().postDataJSON();
      if (body.version !== version) throw new Error('Stale version');
      status = body.reviewed ? 'reviewed' : 'pending';
      return route.fulfill({ json: { status, new: status === 'pending' ? 1 : 0, review_pending: status === 'pending' ? 1 : 0 } });
    }
    if (path === '/goals') return route.fulfill({ json: [{ code: 'landing_stability', label: 'Landing' }] });
    if (['/history', '/sessions', '/team/pending', '/mascot_list'].includes(path)) return route.fulfill({ json: [] });
    return route.fulfill({ json: {} });
  });
  const check = (ok, label) => { if (!ok) throw new Error(label); checks.push(label); };
  try {
    await tab.goto('http://127.0.0.1:8029');
    await tab.locator('.rz-team__row').click();
    const button = tab.locator('[data-review-job]');
    await button.waitFor();
    check(posts === 0 && status === 'pending', 'Opening does not confirm the review');
    fail = true;
    await button.click();
    await tab.waitForFunction(() => !document.querySelector('[data-review-job]').disabled);
    check(status === 'pending', '503 does not change the status');
    fail = false; conflict = true;
    await button.click();
    await tab.waitForFunction(() => document.querySelector('[data-review-job]')?.dataset.version === 'b'.repeat(64));
    check(reads === 2 && status === 'pending', '409 refreshes the log before retry');
    await button.click();
    await tab.waitForFunction(() => document.querySelector('[data-review-job]')?.dataset.reviewed === 'true');
    check(status === 'reviewed', 'Explicit mark is saved');
    check(await button.evaluate(el => el === document.activeElement), 'Focus returns to the action');
    check(await tab.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Log has no overflow at 320px');
    check(await button.evaluate(el => el.getBoundingClientRect().height >= 44), 'Review button is touch-friendly');
    await button.click();
    await tab.waitForFunction(() => document.querySelector('[data-review-job]')?.dataset.reviewed === 'false');
    check(status === 'pending', 'Can return to the queue');
    const cyr = await tab.evaluate(() => (document.getElementById('sheet-student').innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g) || []).slice(0, 5));
    check(!cyr.length, `Student sheet has no Cyrillic: ${JSON.stringify(cyr)}`);
    check(!errors.length, `No JS errors: ${errors.join(', ')}`);
    await tab.screenshot({ path: 'output/playwright/coach-review-mobile.png' });
    return checks;
  } finally { await context.close(); }
}
