/* Production bundle browser checks. No backend or external network requests are allowed. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { pathToFileURL } = require('node:url');
const { performance } = require('node:perf_hooks');
const root = path.resolve(__dirname, '../..');
const web = path.join(root, 'apps/web');
const output = process.argv[2];
if (!output) throw new Error('Provide a NEW JSON output path');
if (fs.existsSync(output)) throw new Error('Existing evidence must not be overwritten');
const requireWeb = createRequire(path.join(web, 'package.json'));
const { chromium } = process.env.PLAYWRIGHT_MODULE_DIR
  ? require(path.join(process.env.PLAYWRIGHT_MODULE_DIR, 'playwright')) : require('playwright');
const results = [], consoleErrors = [], pageErrors = [], external = [], api = [];
const started = performance.now();
async function check(name, action) {
  const t = performance.now();
  try { await action(); results.push({ name, status: 'PASS', seconds: (performance.now()-t)/1000 }); }
  catch (e) { results.push({ name, status: 'FAIL', error: String(e.message), seconds: (performance.now()-t)/1000 }); }
}
function contrast(a, b) {
  const lum = hex => {
    const s = hex.replace('#','');
    const values = [0,2,4].map(i => parseInt(s.slice(i,i+2),16)/255).map(c => c<=0.04045 ? c/12.92 : ((c+.055)/1.055)**2.4);
    return .2126*values[0]+.7152*values[1]+.0722*values[2];
  };
  const x=lum(a), y=lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
}

(async () => {
  let context;
  const artifacts = path.dirname(path.resolve(output));
  fs.mkdirSync(artifacts, {recursive:true});
  const profile = path.join(root,'work/stage2/browser-profile-'+Date.now());
  const executablePath = process.env.BROWSER_EXECUTABLE;
  try {
    context = await chromium.launchPersistentContext(profile, { headless:true, executablePath, viewport:{width:1440,height:1000} });
    const page = await context.newPage();
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('console', message => { if(message.type()==='error'&&!message.text().includes('401 (Unauthorized)')) consoleErrors.push(message.text()); });
    // Fulfill only the built static site at a synthetic localhost origin. Browser socket loopback
    // is restricted on this Windows host; this is NOT a live HTTP deployment/E2E claim.
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if(url.pathname==='/api/auth/status')return route.fulfill({contentType:'application/json',body:'{"provider_available":false,"remote_enabled":false}'});
      if(url.pathname==='/api/auth/me')return route.fulfill({contentType:'application/json',body:JSON.stringify({user_id:'test-ui',institution_id:'A',institution_name:'합성기관',role:'manager',institution_admin:false,csrf_token:'synthetic-csrf'})});
      if (url.origin !== 'http://127.0.0.1:4173') { external.push(url.origin); return route.abort(); }
      if (url.pathname==='/api/documents') return route.fulfill({status:401,contentType:'application/json',body:JSON.stringify({detail:'authentication_not_configured'})});
      if (url.pathname.startsWith('/api') || url.pathname==='/health' || url.pathname==='/documents' || url.pathname==='/search') { api.push(url.pathname); return route.abort(); }
      const dist=path.join(web,'dist');
      const file=path.resolve(dist,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
      if (!file.startsWith(dist+path.sep)) return route.abort();
      if (url.pathname==='/favicon.ico') return route.fulfill({status:204,body:''});
      if (!fs.existsSync(file)) return route.fulfill({status:404,body:'not found'});
      const contentType=file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html';
      return route.fulfill({status:200,body:fs.readFileSync(file),contentType});
    });
    await page.goto('http://127.0.0.1:4173/#/home',{timeout:15000});
    await page.locator('h1').waitFor();
    await check('home semantic landmarks and no fake data', async () => {
      assert.equal(await page.locator('html').getAttribute('lang'),'ko');
      assert.equal(await page.locator('main').count(),1); assert.equal(await page.locator('h1').count(),1);
      assert.equal(await page.locator('nav[aria-label="주 메뉴"]').count(),1);
      assert.equal(await page.locator('h1').innerText(),'업무 홈');
      assert.equal(await page.locator('[role="progressbar"],input,textarea').count(),0);
      assert.match(await page.locator('.connection-notice').innerText(),/데이터 미연결/);
    });
    await check('skip link keyboard access', async () => {
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.className),'skip-link');
      await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
    });
    await check('keyboard visible focus and control targets', async () => {
      await page.locator('.brand').focus(); await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.textContent),'업무 홈');
      assert.equal(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineWidth),'3px');
      assert.ok(await page.locator('nav a').evaluateAll(nodes=>nodes.every(n=>n.getBoundingClientRect().height>=44)));
    });
    await page.screenshot({path:path.join(artifacts,'home-desktop.png'),fullPage:true});
    await check('four page navigation, title and active sidebar', async () => {
      for (const [id,label] of [['documents','문서 관리'],['ai','AI 업무 지원'],['help','도움말'],['home','업무 홈']]) {
        await page.locator(`nav a[href="#/${id}"]`).click();
        await page.waitForFunction(expected=>document.querySelector('h1')?.textContent===expected,label);
        assert.equal(await page.title(),label+' · 서무ITDA');
        assert.equal(await page.locator('nav a[aria-current="page"]').count(),1);
        assert.equal(await page.locator('nav a[aria-current="page"]').getAttribute('href'),'#/'+id);
        assert.equal(await page.evaluate(()=>document.activeElement.id),'page-heading');
      }
    });
    await check('documents fail closed on 401 without data', async () => {
      await page.locator('nav a[href="#/documents"]').click();
      await page.getByRole('heading',{name:'로그인',exact:true}).waitFor();
      assert.equal(await page.locator('input[type="file"]').count(),0);
      assert.equal(await page.locator('table').count(),0);
      assert.match(await page.locator('main').innerText(),/세션이 만료되었거나 취소/);
      await page.screenshot({path:path.join(artifacts,'documents-desktop.png'),fullPage:true});
    });
    await check('AI is preparation-only, no question action', async () => {
      await page.locator('nav a[href="#/ai"]').click();
      await page.waitForFunction(()=>document.querySelector('h1')?.textContent==='AI 업무 지원');
      assert.match(await page.locator('main').innerText(),/실제 AI 모델은 연결되지 않았으며/);
      assert.match(await page.locator('nav a[aria-current="page"]').innerText(),/준비 중/);
      assert.equal(await page.locator('main input,main textarea,main button,main form').count(),0);
    });
    await check('help keyboard disclosure', async () => {
      await page.locator('nav a[href="#/help"]').click();
      const details=page.locator('details').nth(1);
      await details.locator('summary').focus(); await page.keyboard.press('Enter');
      assert.equal(await details.getAttribute('open'),'');
    });
    await check('back navigation and reload deep link', async () => {
      await page.goBack(); await page.waitForFunction(()=>document.querySelector('h1')?.textContent==='AI 업무 지원');
      await page.reload(); assert.equal(await page.locator('h1').innerText(),'AI 업무 지원');
    });
    await check('unknown route recovery', async () => {
      await page.goto('http://127.0.0.1:4173/#/unknown');
      assert.equal(await page.locator('h1').innerText(),'화면을 찾을 수 없습니다');
      await page.locator('main a[href="#/home"]').click();
      await page.waitForFunction(()=>document.querySelector('h1')?.textContent==='업무 홈');
    });
    await check('320/375/768px all pages without horizontal overflow', async () => {
      for (const width of [320,375,768]) {
        await page.setViewportSize({width,height:900});
        for(const id of ['home','documents','ai','help']) {
          await page.goto('http://127.0.0.1:4173/#/'+id);
          await page.locator('h1').waitFor();
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width} ${id} overflows`);
          assert.ok(await page.locator('nav').isVisible());
        }
      }
      await page.setViewportSize({width:375,height:812});
      await page.goto('http://127.0.0.1:4173/#/home');
      await page.screenshot({path:path.join(artifacts,'home-mobile.png'),fullPage:true});
    });
    await check('200 percent text enlargement and reflow', async () => {
      await page.setViewportSize({width:720,height:900});
      for(const id of ['home','documents','ai','help']) {
        await page.goto('http://127.0.0.1:4173/#/'+id);
        await page.locator('h1').waitFor();
        await page.addStyleTag({content:'html {font-size:32px !important}'});
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${id} text enlargement overflows`);
      }
    });
    const pairs=[['body','#172b4d','#ffffff'],['muted','#475569','#f6f8fb'],['primary button','#ffffff','#1d4ed8'],['info','#1d4ed8','#e3edff'],['warning','#854d0e','#fef9e7'],['error','#b42318','#fff1f0']];
    await check('declared text contrast pairs >= 4.5 to 1',async()=>{for(const [name,fg,bg] of pairs)assert.ok(contrast(fg,bg)>=4.5,name);});
    await check('shared status/error/loading/button SSR contracts',async()=>{
      const {createServer}=await import(pathToFileURL(requireWeb.resolve('vite')).href);
      const server=await createServer({root:web,server:{middlewareMode:true,hmr:false},appType:'custom',cacheDir:path.join(root,'work/stage2/vite-test-cache')});
      try {
        const components=await server.ssrLoadModule('/src/components/UI.tsx');
        const React=requireWeb('react');const {renderToStaticMarkup}=requireWeb('react-dom/server');
        const render=(name,props)=>renderToStaticMarkup(React.createElement(components[name],props));
        assert.match(render('LoadingState',{}),/role="status"/);assert.match(render('ErrorState',{message:'연결 실패'}),/role="alert"/);
        assert.doesNotMatch(render('ErrorState',{message:'연결 실패'}),/<button/);
        assert.match(render('ErrorState',{message:'연결 실패',onRetry:()=>{}}),/다시 시도/);
        assert.match(render('Button',{disabled:true,children:'준비 중'}),/disabled/);
        assert.match(render('StatusBadge',{tone:'warning',children:'검토 필요'}),/검토 필요/);
      } finally { await server.close(); }
    });
    await check('no browser console or JS errors, no API/external requests',async()=>{
      assert.deepEqual(consoleErrors,[]);assert.deepEqual(pageErrors,[]);assert.deepEqual(external,[]);assert.deepEqual(api,[]);
    });
    const report={scope:'Stage2 Feature Gate; browser tests of production bundle via static response interception, not live HTTP deployment',
      browser:await page.evaluate(()=>navigator.userAgent),elapsed_seconds:(performance.now()-started)/1000,results,
      counts:{PASS:results.filter(x=>x.status==='PASS').length,FAIL:results.filter(x=>x.status==='FAIL').length,SKIP:0,BLOCKED:0},
      contrast:pairs.map(([name,fg,bg])=>({name,foreground:fg,background:bg,ratio:contrast(fg,bg)})),consoleErrors,pageErrors,external,api,
      not_run:['screen reader manual review','native browser toolbar zoom','full WCAG conformance audit','live HTTP browser loopback integration','real auth/API/AI/backend regression']};
    fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report.counts));console.log('seconds',report.elapsed_seconds);
    if(report.counts.FAIL)process.exitCode=1;
  } finally { await context?.close(); }
})().catch(error=>{console.error(error.message);process.exitCode=1});
