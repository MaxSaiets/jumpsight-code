// Run: playwright-cli -s=gate run-code --filename tools/ui_gates/coach_summary_smoke.cjs
// All coach responses are mocked; the test checks that the summary in attempts is grounded.
async page => {
  await page.unrouteAll({ behavior: 'wait' });
  /* The interface is English only; a stale stored language value is ignored */
  const history = [
    { job: 'latest-job', attempt_id: 2, ts: 200, jump: 'Lutz', outcome: 'measured',
      clean: false, checks_run: 2, errors: ['step_out'], revolutions: 2.1,
      rev_usable: true },
    { job: 'latest-job', attempt_id: 1, ts: 190, jump: 'Lutz', outcome: 'measured',
      clean: true, checks_run: 3, errors: [], revolutions: 2.2, rev_usable: true },
    { job: 'latest-job', attempt_id: 0, ts: 180, jump: null, outcome: 'not_measured',
      errors: ['fake_error_must_not_be_used'], reason: 'fragment_no_count' },
    { job: 'older-job', ts: 100, jump: 'Axel', outcome: 'measured', clean: false,
      checks_run: 2, errors: ['fall'], revolutions: 1.2, rev_usable: true },
  ];
  await page.route('**/coach/**', route => {
    const path = route.request().url().split('?')[0].replace(/^https?:\/\/[^/]+/, '');
    if (path === '/coach/history') return route.fulfill({ json: history });
    if (path === '/coach/today') return route.fulfill({ json: {
      focus_text: 'Stable exit', history_note: 'From your latest analyses',
      blocks: [{ block: 'main', drill_id: 'landing_hold', name: 'Landing hold',
        dosage: 'as your coach planned', cues: ['Soft knee'], steps: [], mistakes: [] }],
    } });
    if (['/coach/sessions', '/coach/mascot_list', '/coach/team', '/coach/comments']
      .some(prefix => path.startsWith(prefix))) return route.fulfill({ json: [] });
    return route.fulfill({ json: {} });
  });

  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('http://127.0.0.1:8000/');
  await page.locator('[data-tab="progress"]').click();
  const card = page.locator('#session-summary');
  await card.waitFor({ state: 'visible' });
  const text = await card.innerText();
  if (!text.includes('2 measured attempts')) throw new Error('Measured attempt count is not grounded');
  if (!text.includes('1 without enough data')) throw new Error('Degraded attempt is not explained');
  if (!text.toLowerCase().includes('lutz') || !text.includes('2.20'))
    throw new Error('Best clean attempt is not shown from measured data');
  if (!text.toLowerCase().includes('step-out')) throw new Error('Advice is not based on measured errors');
  if (text.includes('fake_error') || /\bfall\b/i.test(text))
    throw new Error('Summary leaked an unmeasured or older-job error');
  if (!text.includes('Landing hold')) throw new Error('Next action is not from the server plan');
  if (/[\u0400-\u04FF]/.test(text)) throw new Error(`Cyrillic in the summary: ${text}`);
  const actions = await card.locator('button, a').count();
  if (actions !== 1) throw new Error(`Expected one next action, got ${actions}`);
  /* Journal summaries live in the profile (#acc-stats) and show
     the same facts. */
  await page.locator('#btn-account').click();
  await page.locator('#acc-stats').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  if (!await page.locator('#acc-stats').isVisible())
    throw new Error('Profile stats stay hidden despite factual history');
  const statsText = await page.locator('#acc-stats').innerText();
  if (/[\u0400-\u04FF]/.test(statsText)) throw new Error(`Cyrillic in profile stats: ${statsText}`);
  if (/\bclean\b/i.test(statsText))
    throw new Error(`Profile still counts «clean», which is always 0: ${statsText}`);
  return { job: 'latest-job', measured: 2, degraded: 1, actions,
    parentDashboard: 'shown with history' };
}
