/* Empty transport control with real local A/B videos, no inference. */
async page=>{
  const fixtures=__FIXTURES__,videos=__VIDEOS__,checks=[],errors=[];
  for(const role of ['coach','skater'])for(const width of [320,390])for(const lang of ['en'])for(const mode of ['loaded','late']){
    /* English only; a stored 'uk' choice in localStorage is ignored. */
    const context=await page.context().browser().newContext({viewport:{width,height:844},isMobile:true,hasTouch:true});
    const tab=await context.newPage();let release,held,posts=[],shares=[];
    tab.on('pageerror',e=>errors.push(e.message));
    await tab.addInitScript(()=>{Object.defineProperty(navigator,'share',{value:async()=>{}});});
    const gate=new Promise(r=>release=r),started=new Promise(r=>held=r);
    await tab.route('**/coach/**',async route=>{
      const path=new URL(route.request().url()).pathname.replace('/coach','');
      if(['/me','/auth/guest'].includes(path))return route.fulfill({json:{uid:'empty_ui_123',role,coach:'fixture_coach',code:'EMP123'}});
      if(path==='/comments/media_a'){held();if(mode==='late')await gate;return route.fulfill({json:[{text:'Comment A',name:'Coach A',role:'coach',ts:1790700000}]});}
      if(path==='/comments/media_b')return route.fulfill({json:[{text:'Comment B',name:'Coach B',role:'coach',ts:1790700000}]});
      if(path==='/comment'){posts.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});}
      if(path==='/share'){shares.push(route.request().postDataJSON());return route.fulfill({json:{token:'fixture_empty_token'}});}
      return route.fulfill({json:[]});
    });
    await tab.route('**/demos',route=>route.fulfill({json:[]}));
    await tab.route('**/summary/media_a',route=>route.fulfill({json:{fps:fixtures[0].fps,jumps:[fixtures[0].summary]}}));
    await tab.route('**/summary/media_b',route=>route.fulfill({json:{state:'done',fps:fixtures[1].fps,jumps:[]}}));
    for(const [i,f]of fixtures.entries())await tab.route('**/media/'+f.job+'/full/original',route=>{
      const bytes=Buffer.from(videos[i],'base64'),match=(route.request().headers()['range']||'').match(/^bytes=(\d+)-(\d*)$/);
      if(match){const start=Number(match[1]),end=Math.min(match[2]?Number(match[2]):bytes.length-1,bytes.length-1);return route.fulfill({status:206,contentType:'video/mp4',body:bytes.subarray(start,end+1),headers:{'Accept-Ranges':'bytes','Content-Range':`bytes ${start}-${end}/${bytes.length}`}});}
      return route.fulfill({contentType:'video/mp4',body:bytes,headers:{'Accept-Ranges':'bytes'}});
    });
    try{
      await tab.goto('http://127.0.0.1:8029');
      await tab.evaluate(async()=>await window.APP.openJob('media_a'));await started;
      await tab.waitForFunction(()=>document.getElementById('ans-video').readyState>=2);
      if(mode==='loaded')await tab.waitForFunction(()=>document.getElementById('comments-list').textContent.includes('Comment A'));
      await tab.evaluate(()=>document.getElementById('comment-text').value='Unfinished draft');
      await tab.evaluate(async()=>await window.APP.openJob('media_b'));
      if(mode==='late'){
        const response=tab.waitForResponse(r=>new URL(r.url()).pathname==='/coach/comments/media_a');release();await(await response).finished();
      }
      if(__ASSERT_IMPROVED__)await tab.waitForFunction(()=>document.getElementById('comments-list').textContent.includes('Comment B')&&document.getElementById('ans-video').readyState>=2);
      await tab.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
      const comments=await tab.locator('#comments-list').innerText();
      const source=await tab.locator('#ans-video').getAttribute('src');
      const current=await tab.locator('#ans-video').evaluate(v=>new URL(v.currentSrc).pathname);
      const title=await tab.locator('#ans-verdict-t').innerText();
      const draft=await tab.locator('#comment-text').inputValue();
      const phasesDisabled=await tab.locator('#lbl-ph-flight').isDisabled();
      /* 'Share' opens a sheet (card + link);
         the analysis link is created by the 'Send link' button. */
      await tab.locator('#btn-ans-share').click();
      /* Wait for the link request itself, not 300 ms: on a slow
         environment the POST did not finish and the gate failed without a product defect */
      const shareRequest=tab.waitForRequest(r=>new URL(r.url()).pathname==='/coach/share',{timeout:10000}).catch(()=>null);
      await tab.locator('#btn-share-link').click();
      await shareRequest;await tab.waitForTimeout(100);
      await tab.locator('#btn-close-share').click();
      if(role==='coach'){
        await tab.locator('#comments-form').waitFor({state:'visible'});
        // Empty B has its own draft; A's text stays with A.
        await tab.locator('#comment-text').fill('Comment on empty B');
        const response=tab.waitForResponse(r=>new URL(r.url()).pathname==='/coach/comment');await tab.locator('#btn-comment-send').click();await(await response).finished();
      }
      const overflow=await tab.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
      const cyr=await tab.evaluate(()=>(document.getElementById('scr-answer').innerText.match(/[\u0400-\u04FF][^\n]{0,40}/g)||[]).slice(0,5));
      if(cyr.length)throw Error('Cyrillic on the answer screen: '+JSON.stringify(cyr));
      checks.push({role,width,lang,mode,comments,source,current,title,draft,phasesDisabled,posts,shares,overflow});
      if(__ASSERT_IMPROVED__&&(!comments.includes('Comment B')||comments.includes('Comment A')||source!=='/media/media_b/full/original'||current!==source||draft!==''||!phasesDisabled||shares[0]?.job!=='media_b'||posts.some(p=>p.job!=='media_b'||p.text!=='Comment on empty B')||overflow))throw Error('Empty result retained old context '+JSON.stringify(checks.at(-1)));
    }finally{release();await context.close();}
  }
  if(errors.length)throw Error(errors.join(';'));
  return{scope:'Empty summary is a synthetic transport control; media and nonempty A summary are real cached fixtures',checks,errors};
}
