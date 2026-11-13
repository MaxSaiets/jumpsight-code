/* Runs one gate of the form `async page => {...}` without playwright-cli.
   Environments with the playwright library and Chromium but no
   `npx @playwright/cli` use this. Same contract as `playwright-cli run-code`:
   a fresh browser, a page open on the UI server, the function receives page,
   and the result prints as JSON. Gates with fixtures (`__...__`) must not be
   passed here: tools/run_ui_gates.py fills those in.

     node tools/run_gate_node.cjs tools/coach_mobile_smoke.js [--port 8029] [--browser chromium|webkit]
     python -c "import json; from tools.run_ui_gates import _controlled_team as t; print(json.dumps({'__BACKEND_TEAM__': t()}))" > team.json
     node tools/run_gate_node.cjs tools/team_confidence_smoke.js --fill team.json
*/
const fs = require('fs');
const path = require('path');
let pw;
try { pw = require('playwright'); }
catch (e) { pw = require(path.join(process.execPath, '..', '..', 'lib', 'node_modules', 'playwright')); }

(async () => {
  const args = process.argv.slice(2);
  const file = args.find(a => !a.startsWith('--'));
  const opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : null; };
  const port = opt('port') || '8029';
  const kind = opt('browser') || 'chromium';
  let src = fs.readFileSync(file, 'utf8').replace(/127\.0\.0\.1:8000/g, '127.0.0.1:' + port);
  /* --fill FILE.json: {"__NAME__": <value>} substitutes fixtures
     (for example __BACKEND_TEAM__ from tools.run_ui_gates._controlled_team) */
  if (opt('fill')) for (const [k, v] of Object.entries(JSON.parse(fs.readFileSync(opt('fill'), 'utf8'))))
    src = src.split(k).join(JSON.stringify(v));
  const left = src.match(/__[A-Z_]{4,}__/g);
  if (left) { console.error('Fixtures not substituted: ' + [...new Set(left)].join(', ')); process.exit(2); }
  const fn = eval('(' + src.replace(/^\s*(\/\/[^\n]*\n|\/\*[\s\S]*?\*\/\s*)*/, '') + ')');
  const browser = await pw[kind].launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:' + port);
  try {
    const out = await fn(page);
    console.log('### Result\n' + JSON.stringify(out, null, 1));
    await browser.close();
  } catch (e) {
    console.log('### Error\n' + (e && e.stack || e));
    await browser.close();
    process.exit(1);
  }
})();
