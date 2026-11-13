#!/usr/bin/env node
'use strict';
/* Browser checks run only against an ephemeral loopback static server.
   External browser network requests are blocked; no Google indexing actions. */
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const assert = require('node:assert/strict');
const puppeteer = require('puppeteer');
const root = path.resolve(__dirname, '..');
const pages = [
 'blog-v2.html',
 'post-high-converting-websites.html',
 'post-small-business-security.html',
 'post-site-speed-revenue.html'
];
const contentTypes = {
 '.html':'text/html; charset=utf-8',
 '.css':'text/css; charset=utf-8',
 '.js':'text/javascript; charset=utf-8',
 '.png':'image/png',
 '.svg':'image/svg+xml',
 '.webp':'image/webp'
};
const server = http.createServer((req,res)=>{
  const url = new URL(req.url, 'http://localhost');
  const candidate = path.resolve(root, '.' + decodeURIComponent(url.pathname));
  if (!candidate.startsWith(root + path.sep)) {
    res.writeHead(403);res.end('Forbidden');return;
  }
  if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
    res.writeHead(404);res.end('Not found');return;
  }
  res.setHeader('Content-Type',contentTypes[path.extname(candidate)]||'application/octet-stream');
  fs.createReadStream(candidate).pipe(res);
});
let browser;
async function main() {
 await new Promise(resolve=>server.listen(0, '127.0.0.1', resolve));
 const base = 'http://127.0.0.1:' + server.address().port;
 browser=await puppeteer.launch({
   executablePath:'/usr/bin/chromium',
   headless:true,
   args:['--no-sandbox','--disable-dev-shm-usage']
 });
 let passed=0;
 for (const [width,height] of [[375,812],[768,1024],[1440,900]]) {
   for (const filename of pages) {
     const page=await browser.newPage();
     await page.setViewport({width,height});
     await page.setRequestInterception(true);
     page.on('request',req=>req.url().startsWith(base)?req.continue():req.abort());
     const response=await page.goto(base + '/' + filename,{waitUntil:'networkidle0'});
     assert.equal(response.status(),200,filename);
     await page.waitForSelector('header.site-header');
     const result=await page.evaluate(()=>({
       width:document.documentElement.scrollWidth,
       viewport:window.innerWidth,
       h1:document.querySelectorAll('h1').length,
       title:document.title,
       canonical:document.querySelector('link[rel=canonical]')?.href,
       mainText:document.querySelector('main')?.innerText?.trim().length || 0,
       stylesheet:document.styleSheets.length,
       logo:!!document.querySelector('header.site-header .logo'),
       footer:!!document.querySelector('#footer-slot footer'),
       articleLinks:[...document.querySelectorAll('main a[href^="post-"]')].map(x=>x.getAttribute('href'))
     }));
     assert.ok(result.width <= result.viewport + 1,filename+' '+width+' horizontal overflow '+JSON.stringify(result));
     assert.equal(result.h1,1,filename);
     assert.ok(result.title.length>10,filename);
     assert.equal(result.canonical,'https://dsdigitaldesigns.org/'+filename);
     assert.ok(result.mainText>300,filename);
     assert.ok(result.stylesheet>0,filename);
     assert.ok(result.logo && result.footer,filename);
     if(filename==='blog-v2.html') {
       for (const post of pages.slice(1))assert.ok(result.articleLinks.includes(post),post);
       if(width===375){
         await page.click('#menuBtn');
         assert.equal(await page.$eval('#menuBtn',x=>x.getAttribute('aria-expanded')),'true');
         await page.keyboard.press('Escape');
         assert.equal(await page.$eval('#menuBtn',x=>x.getAttribute('aria-expanded')),'false');
       }
     }
     console.log('PASS viewport='+width+' page='+filename);
     passed++;
     await page.close();
   }
 }
 // Google can see core article content and links even when JavaScript is disabled.
 const jsOff=await browser.newPage();
 await jsOff.setJavaScriptEnabled(false);
 const response=await jsOff.goto(base+'/blog-v2.html');
 assert.equal(response.status(),200);
 const staticLinks=await jsOff.$$eval('main a[href^="post-"]',nodes=>nodes.map(x=>x.getAttribute('href')));
 for (const post of pages.slice(1)) assert.ok(staticLinks.includes(post), post);
 const staticH1=await jsOff.$eval('h1',x=>x.textContent.trim());
 assert.ok(staticH1.length>10);
 await jsOff.close();
 console.log('PASS blog has crawlable content with JavaScript disabled');
 passed++;
 console.log('SUMMARY '+passed+' passed, 0 failed');
}
main().catch(error=>{console.error('FAIL',error.stack||error);process.exitCode=1;})
.finally(async()=>{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));});