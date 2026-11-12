#!/usr/bin/env node
'use strict';
/* Full HTML preview tests for a *fictional* local record.
   No external requests, no GitHub push, and no public publishing. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const cp = require('node:child_process');
const puppeteer = require('puppeteer');
const root=path.resolve(__dirname,'..');
const buildPath=path.join(root,'build','checkpoint-002-browser');
const tempDir=fs.mkdtempSync(path.join(os.tmpdir(),'ds-local-synthetic-'));
let server,browser;
const mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.png':'image/png','.svg':'image/svg+xml','.xml':'application/xml'};
async function main(){
  const fixture=path.join(tempDir,'fixture.json');
  const run=cp.spawnSync('python3',['-c',"import json,sys;sys.path.insert(0,'tests');from test_local_stories import synthetic_story;print(json.dumps({'schema_version':1,'stories':[synthetic_story()]}))"],{cwd:root,encoding:'utf8'});
  if(run.status!==0)throw new Error(run.stderr);
  fs.writeFileSync(fixture,run.stdout);
  const build=cp.spawnSync('python3',['scripts/build_local_stories.py','--input',fixture,'--output',buildPath],{cwd:root,encoding:'utf8'});
  if(build.status!==0)throw new Error(build.stderr);
  const serverCallback=(req,res)=>{
    const file=path.resolve(buildPath,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
    if(!file.startsWith(buildPath+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){
      res.writeHead(404);res.end('Not found');return;
    }
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  };
  server=http.createServer(serverCallback);
  await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
  const origin='http://127.0.0.1:'+server.address().port;
  browser=await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  let passed=0;
  const test=async(label,fn)=>{
    await fn();passed++;console.log('PASS',label);
  };
  for(const width of [390,768,1440]){
    const page=await browser.newPage();
    await page.setViewport({width,height:width===390?844:900});
    await page.setRequestInterception(true);
    page.on('request',r=>r.url().startsWith(origin)?r.continue():r.abort());
    await page.goto(origin+'/blog-v2.html',{waitUntil:'networkidle0'});
    await page.waitForSelector('header.site-header');
    await test('blog '+width+'px: no horizontal overflow and 4 cards',async()=>{
      assert.equal(await page.$$eval('.lb-card',xs=>xs.length),4);
      const dims=await page.evaluate(()=>({viewport:innerWidth,doc:document.documentElement.scrollWidth}));
      assert.ok(dims.doc<=dims.viewport+1,JSON.stringify(dims));
    });
    await test('blog '+width+'px: local category shows one synthetic record',async()=>{
      await page.click('[data-blog-filter="local"]');
      assert.equal(await page.$$eval('.lb-card:not([hidden])',xs=>xs.length),1);
      assert.match(await page.$eval('.lb-card:not([hidden]) h3',x=>x.textContent),/SYNTHETIC TEST/);
    });
    await page.goto(origin+'/greeneville/synthetic-test-public-meeting.html',{waitUntil:'networkidle0'});
    await test('article '+width+'px: source, canonical, stylesheet and layout',async()=>{
      const dims=await page.evaluate(()=>({viewport:innerWidth,doc:document.documentElement.scrollWidth}));
      assert.ok(dims.doc<=dims.viewport+1,JSON.stringify(dims));
      assert.equal(await page.$eval('link[rel=canonical]',x=>x.href),'https://dsdigitaldesigns.org/greeneville/synthetic-test-public-meeting.html');
      assert.ok((await page.$eval('h1',x=>x.textContent)).includes('SYNTHETIC TEST'));
      assert.match(await page.$eval('.lb-article-meta',x=>x.textContent),/Proposed/);
      assert.ok(await page.$('a[href="https://example.org/synthetic-test-document"]'));
      assert.equal(await page.$eval('header.site-header .logo',x=>!!x),true);
      const color=await page.$eval('.lb-article-content p',x=>getComputedStyle(x).color);
      assert.ok(color);
    });
    await page.close();
  }
  console.log('Summary:',passed,'passed; 0 failed.');
}
main().catch(e=>{console.error('FAIL',e.stack||e);process.exitCode=1})
.finally(async()=>{
  if(browser)await browser.close();
  if(server)await new Promise(ok=>server.close(ok));
  fs.rmSync(tempDir,{recursive:true,force:true});
  if(buildPath.startsWith(path.join(root,'build')+path.sep))fs.rmSync(buildPath,{recursive:true,force:true});
});