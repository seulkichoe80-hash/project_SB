// Local-only standalone browser probe. Never deploys, installs, or changes old evidence.
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const root=process.cwd();const output=path.join(root,'work/repository-foundation/browser');fs.mkdirSync(output,{recursive:true});
const target=path.join(output,`result-${Date.now()}.json`);
let browser;let server;let log;let result;
try{
  if(!process.env.PLAYWRIGHT_MODULE)throw Error('Set PLAYWRIGHT_MODULE to a reviewed local Playwright entry path; no auto-install');
  const require=createRequire(import.meta.url);const {chromium}=require(path.resolve(process.env.PLAYWRIGHT_MODULE));
  const cwd=path.join(root,'work/phase1/frontend');
  const vite=path.join(cwd,'node_modules/vite/bin/vite.js');if(!fs.existsSync(vite))throw Error('Preserved Vite spike dependency missing');
  log=fs.openSync(path.join(output,'preview.log'),'a');
  server=spawn(process.execPath,[vite,'preview','--host','127.0.0.1','--port','4189','--strictPort'],{cwd,windowsHide:true,stdio:['ignore',log,log]});
  let ready=false;for(let i=0;i<50;i++){if(server.exitCode!==null)throw Error('Preview server exited or port unavailable');try{if((await fetch('http://127.0.0.1:4189')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}if(!ready)throw Error('Preview not ready');
  browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge',timeout:20000});
  const page=await browser.newPage();const errors=[];const external=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{if(new URL(route.request().url()).hostname==='127.0.0.1')return route.continue();external.push(route.request().url());return route.abort();});
  await page.goto('http://127.0.0.1:4189');await page.waitForSelector('.react-flow__node',{timeout:10000});
  const count=await page.locator('.react-flow__node').count();if(count!==2)throw Error('Incorrect node count');
  await page.locator('.react-flow__node').filter({hasText:'1. 신청서 작성'}).click();
  const selected=await page.getByTestId('selected').innerText();if(selected!=='section0/p[1]')throw Error('Incorrect selected evidence');
  if(errors.length||external.length)throw Error('Browser errors or external requests');
  await page.screenshot({path:path.join(output,'screenshot.png'),fullPage:true});
  result={status:'PASS',scope:'local preserved two-node spike only',nodes:count,selected,external_requests:external.length};
}catch(e){result={status:'BLOCKED',scope:'browser execution',error:String(e)};process.exitCode=1;}
finally{if(browser)await browser.close();if(server&&server.exitCode===null){server.kill();await new Promise(r=>server.once('exit',r));}if(log!==undefined)fs.closeSync(log);}
fs.writeFileSync(target,JSON.stringify(result,null,2));console.log(JSON.stringify({resultFile:target,...result}));
