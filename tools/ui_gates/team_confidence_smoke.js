/* Coach cards from the actual HTTP team endpoint; no private browser records. */
async page => {
  const team = __BACKEND_TEAM__, checks = [], errors = [];
  /* English only; a stored 'uk' choice is ignored; count_named
     in the fixture is deliberately a raw Ukrainian string ('double'): the client must translate it
     even if the old server did not translate it */
  for (const width of [320,390,1024]) for (const lang of ['en']) {
    const context = await page.context().browser().newContext({viewport:{width,height:844},hasTouch:true,isMobile:width<768});
    const tab = await context.newPage();
    tab.on('pageerror', e => errors.push(e.message));
    await tab.route('**/coach/**',route=>{
      const path=new URL(route.request().url()).pathname.replace('/coach','');
      if(path==='/me'||path==='/auth/guest') return route.fulfill({json:{uid:'coach_confidence_fixture',role:'coach',name:'Coach',code:'TEST'}});
      if(path==='/team') return route.fulfill({json:team});
      if(['/team/pending','/goals','/history','/sessions','/mascot_list'].includes(path)) return route.fulfill({json:[]});
      return route.fulfill({json:{}});
    });
    try {
      await tab.goto('http://127.0.0.1:8029');
      await tab.locator('.rz-team__row').first().waitFor();
      /* One confidence language matches the student answer ('name — probable').
         Same rule: each conclusion in the coach row carries its own confidence;
         a finding with low or unknown confidence is shown only as 'possibly: …'. */
      for(const tier of ['low','medium','high','None']) {
        const card=tab.locator('.rz-team__row').filter({hasText:`controlled_${tier}`});
        const text=await card.innerText();
        const words={low:'possible',medium:'likely',high:'confident',None:'confidence unknown'};
        for(const label of ['name —','count —'])
          if(!text.includes(`${label} ${words[tier]}`)) throw new Error(`Missing ${label}/${tier}/${lang}: ${text}`);
        const sure=tier==='medium'||tier==='high';
        const errLabel=sure?`Step-out — ${words[tier]}`:'possibly: step-out';
        if(!text.includes(errLabel)) throw new Error(`Unqualified error label ${tier}/${lang}: ${text}`);
      }
      if(!(await tab.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))) throw new Error(`Overflow ${width}/${lang}`);
      const cyr=await tab.evaluate(()=>(document.getElementById('scr-team').innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g)||[]).slice(0,5));
      if(cyr.length) throw new Error(`Cyrillic on the coach screen: ${JSON.stringify(cyr)}`);
      checks.push({width,lang,cards:team.length});
      if(width===390) await tab.screenshot({path:'output/playwright/team-confidence-390.png',fullPage:false});
    } finally {await context.close();}
  }
  if(errors.length) throw new Error(errors.join('; '));
  return {checks,pageerrors:errors,scope:'Actual authenticated HTTP team with cached and controlled records; mobile/desktop rendering'};
}
