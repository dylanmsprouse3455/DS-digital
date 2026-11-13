#!/usr/bin/env node
'use strict';
/* Browser audit of a private candidate assembled against actual main.
   No public writes; browser requests never leave loopback. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const assert=require('node:assert/strict');
const puppeteer=require('puppeteer');

const candidate=path.resolve(process.argv[2]||'');
if(!candidate.includes('/ds-blog-release-candidate-demo-005/git'))
  throw new Error('Refusing to inspect an unrecognized candidate checkout');
let server,browser;
const files=[
 'blog-v2.html',
 'greeneville/proposed-synthetic-test-trail-1.html',
 'post-high-converting-websites.html',
 'post-small-business-security.html',
 'post-site-speed-revenue.html'
];
const mime={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.png':'image/png',
 '.xml':'application/xml','.svg':'image/svg+xml','.webp':'image/webp'};
async function run(){
  server=http.createServer((req,res)=>{
    const p=path.resolve(candidate,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
    if(!p.startsWith(candidate+path.sep)||!fs.existsSync(p)||!fs.statSync(p).isFile()){
      res.writeHead(404);res.end('Missing');return;
    }
    res.setHeader('Content-Type',mime[path.extname(p)]||'application/octet-stream');
    fs.createReadStream(p).pipe(res);
  });
  await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
  const url='http://127.0.0.1:'+server.address().port;
  browser=await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:true,
                                  args:['--no-sandbox','--disable-dev-shm-usage']});
  let passed=0;
  for(const width of [375,768,1440]){
    const page=await browser.newPage();
    await page.setViewport({width,height:width===375?812:900});
    await page.setRequestInterception(true);
    page.on('request',req=>req.url().startsWith(url)?req.continue():req.abort());
    const resp=await page.goto(url+'/blog-v2.html',{waitUntil:'networkidle0'});
    assert.equal(resp.status(),200);
    await page.waitForSelector('header.site-header');
    const summary=await page.evaluate(()=>({
      overflow:document.documentElement.scrollWidth-window.innerWidth,
      cards:document.querySelectorAll('.lb-card').length,
      style:getComputedStyle(document.querySelector('.lb-hero')).backgroundImage,
      searchScript:typeof document.querySelector('#local-blog-search') !== 'undefined',
      footer:!!document.querySelector('#footer-slot footer')
    }));
    assert.ok(summary.overflow<=1,width+' overflow');
    assert.equal(summary.cards,4);
    assert.ok(summary.style.includes('gradient'));
    assert.ok(summary.footer);
    passed++;console.log('PASS candidate blog layout '+width);
    await page.click('[data-blog-filter=local]');
    assert.equal(await page.$$eval('.lb-card:not([hidden])',n=>n.length),1);
    await page.type('#local-blog-search','SYNTHETIC');
    assert.equal(await page.$$eval('.lb-card:not([hidden])',n=>n.length),1);
    passed++;console.log('PASS candidate search and local filter '+width);
    const r=await page.goto(url+'/greeneville/proposed-synthetic-test-trail-1.html',{waitUntil:'networkidle0'});
    assert.equal(r.status(),200);
    assert.ok(await page.$eval('body',e=>e.scrollWidth <= innerWidth+1));
    assert.match(await page.$eval('h1',e=>e.innerText),/FICTIONAL TEST/);
    assert.equal(await page.$eval('link[rel=canonical]',e=>e.href),
                 'https://dsdigitaldesigns.org/greeneville/proposed-synthetic-test-trail-1.html');
    assert.ok(await page.$('header.site-header'));
    assert.ok(await page.$('#footer-slot footer'));
    passed++;console.log('PASS candidate story article '+width);
    await page.close();
  }
  const page=await browser.newPage();
  await page.setRequestInterception(true);
  page.on('request',req=>req.url().startsWith(url)?req.continue():req.abort());
  for(const file of files.slice(2)){
    const r=await page.goto(url+'/'+file);
    assert.equal(r.status(),200);
    passed++;console.log('PASS preserved article '+file);
  }
  const css=await page.goto(url+'/assets/css/blog-local.css');assert.equal(css.status(),200);passed++;
  const js=await page.goto(url+'/assets/js/blog-local.js');assert.equal(js.status(),200);passed++;
  console.log('PASS two new blog assets are accessible');
  await page.close();
  console.log('SUMMARY: '+passed+' passed, 0 failed; private candidate only');
}
run().catch(e=>{console.error(e.stack||e);process.exitCode=1}).finally(async()=>{
  if(browser)await browser.close();
  if(server)await new Promise(ok=>server.close(ok));
});