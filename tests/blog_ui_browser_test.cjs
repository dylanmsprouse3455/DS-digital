#!/usr/bin/env node
'use strict';
/* Loopback-only browser tests. Requires Puppeteer and a system Chromium.
   Run: NODE_PATH=/opt/kali-ai-runtime/app/node_modules node tests/blog_ui_browser_test.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const puppeteer = require('puppeteer');
const root = path.resolve(__dirname, '..');
const mime = {'.html':'text/html','.css':'text/css','.js':'text/javascript','.png':'image/png','.svg':'image/svg+xml'};
const server = http.createServer((req,res) => {
  const file = path.resolve(root, '.' + decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404);res.end('Not found');return;
  }
  res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
  fs.createReadStream(file).pipe(res);
});
async function main(){
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  const browser=await puppeteer.launch({
    executablePath:process.env.CHROME_BINARY || '/usr/bin/chromium',
    headless:true, args:['--no-sandbox','--disable-dev-shm-usage']
  });
  let passes=0,errors=[];
  const check=async(name, fn)=>{
    try{await fn();passes++;console.log('PASS',name);}
    catch(e){errors.push(name+': '+e.message);console.error('FAIL',name,e.message);}
  };
  const makePage=async(w,h)=>{
    const p=await browser.newPage();
    await p.setViewport({width:w,height:h,deviceScaleFactor:1});
    await p.setRequestInterception(true);
    p.on('request',req=>req.url().startsWith(origin)?req.continue():req.abort());
    await p.goto(origin+'/blog-v2.html',{waitUntil:'networkidle0'});
    await p.waitForSelector('header.site-header');
    return p;
  };
  try{
    for(const [w,h] of [[390,844],[768,1024],[1440,900]]){
      const p=await makePage(w,h);
      await check('viewport '+w+'px no horizontal overflow',async()=>{
        const stats=await p.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,hero:!!document.querySelector('#blog-title'),search:!!document.querySelector('#local-blog-search')}));
        assert.ok(stats.width<=stats.viewport+1,JSON.stringify(stats));assert.ok(stats.hero&&stats.search);
      });
      if(w===390){
        await check('mobile site menu opens and closes',async()=>{
          await p.click('#menuBtn');
          assert.equal(await p.$eval('#menuBtn',x=>x.getAttribute('aria-expanded')),'true');
          await p.keyboard.press('Escape');
          assert.equal(await p.$eval('#menuBtn',x=>x.getAttribute('aria-expanded')),'false');
        });
      }
      if(w===1440){
        await check('all original posts preserved',async()=>{
          assert.equal(await p.$$eval('[data-blog-article]:not([hidden])',xs=>xs.length),3);
          for(const a of ['post-high-converting-websites.html','post-small-business-security.html','post-site-speed-revenue.html']){
            assert.equal(await p.$$eval('.lb-card a[href="'+a+'"]',xs=>xs.length),1);
            assert.ok(fs.existsSync(path.join(root,a)),a+' missing');
          }
        });
        await check('search filters and reset',async()=>{
          await p.type('#local-blog-search','security');
          assert.equal(await p.$$eval('[data-blog-article]:not([hidden])',xs=>xs.length),1);
          assert.match(await p.$eval('.lb-card:not([hidden]) h3',x=>x.textContent),/security/i);
          await p.click('#local-blog-search');
          await p.keyboard.down('Control');
          await p.keyboard.press('KeyA');
          await p.keyboard.up('Control');
          await p.keyboard.press('Backspace');
          assert.equal(await p.$$eval('[data-blog-article]:not([hidden])',xs=>xs.length),3);
          await p.type('#local-blog-search','not-a-story-xyz');
          assert.equal(await p.$$eval('[data-blog-article]:not([hidden])',xs=>xs.length),0);
          assert.equal(await p.$eval('#local-blog-empty',x=>x.hidden),false);
          await p.click('#local-blog-search');
          await p.keyboard.down('Control');
          await p.keyboard.press('KeyA');
          await p.keyboard.up('Control');
          await p.keyboard.press('Backspace');
        });
        await check('local category honestly empty; DS articles visible',async()=>{
          await p.click('[data-blog-filter=local]');
          assert.equal(await p.$$eval('[data-blog-article]:not([hidden])',xs=>xs.length),0);
          assert.match(await p.$eval('#local-blog-empty',x=>x.textContent),/No published articles/);
          await p.click('[data-blog-filter=insights]');
          assert.equal(await p.$$eval('[data-blog-article]:not([hidden])',xs=>xs.length),3);
          assert.equal(await p.$eval('[data-blog-filter=insights]',x=>x.getAttribute('aria-pressed')),'true');
        });
        await check('brand shell, canonical, no fabricated local news',async()=>{
          assert.equal(await p.$$eval('header.site-header .logo',xs=>xs.length),1);
          assert.equal(await p.$$eval('#footer-slot footer',xs=>xs.length),1);
          assert.equal(await p.$eval('a[aria-current=page][href="blog-v2.html"]',x=>x.getAttribute('href')),'blog-v2.html');
          assert.equal(await p.$eval('link[rel=canonical]',x=>x.getAttribute('href')),'https://dsdigitaldesigns.org/blog-v2.html');
          assert.equal(await p.$$eval('[data-blog-article][data-region=greeneville]',xs=>xs.length),0);
        });
      }
      await p.close();
    }
    console.log('\nSummary:',passes,'passed;',errors.length,'failed.');
    if(errors.length)process.exitCode=1;
  }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;server.close();});