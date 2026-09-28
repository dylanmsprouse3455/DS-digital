import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {launch,base,report} from './helpers.mjs';
const baselinePath=process.env.INVOICE_BASELINE;
const preserved=['index.html','qr/index.html','qr/app.js','assets/css/theme.css','assets/js/shell.js','assets/js/load-components.js','components/nav.html'];
const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const baseline=baselinePath?JSON.parse(await fs.readFile(baselinePath)):{sha256:Object.fromEntries(preserved.map(f=>[f,digest(execFileSync('git',['show','350772349c11065471045397cdf2d70cf9f02a86:'+f]))]))};
for(const [f,h]of Object.entries(baseline.sha256))assert.equal(digest(await fs.readFile(f)),h,'Existing work changed: '+f);
const b=await launch(),results=[];
try{const p=await b.newPage({viewport:{width:390,height:844}});for(const route of ['/','/free-tools.html','/qr/','/services-v2.html','/tools/website-clarity-snapshot/']){const errors=[];const listener=m=>{if(m.type()==='error')errors.push(m.text());};p.on('console',listener);const response=await p.goto(base+route,{waitUntil:'domcontentloaded'});assert.equal(response.status(),200);assert(await p.locator('body').innerText());await p.waitForTimeout(400);p.off('console',listener);results.push({route,status:response.status(),console:errors});}
 await p.goto(base+'/free-tools.html',{waitUntil:'domcontentloaded'});await p.locator('a[href="/tools/invoice-maker/"]').waitFor();await p.locator('#menuBtn').click();assert(await p.locator('#menu').evaluate(e=>e.classList.contains('active')));assert(await p.locator('#menu a[href="free-tools.html"]').count());await p.keyboard.press('Escape');await p.locator('a[href="/tools/invoice-maker/"]').click();assert(p.url().endsWith('/tools/invoice-maker/'));
 await report('regression',{status:'passed',preservedFiles:Object.keys(baseline.sha256),results});console.log('REGRESSION ACCEPTANCE PASSED: existing file hashes preserved, five pages respond, shared menu and invoice discovery work; existing console messages recorded separately');
}finally{await b.close();}
