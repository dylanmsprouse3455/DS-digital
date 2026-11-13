#!/usr/bin/env node
'use strict';
/* Simulates full private intake->review->staging->mock-HTTP->email preview,
 * then verifies generated HTML at mobile, tablet and desktop widths.
 * No public website writes, outbound email, or external browser requests.
 */
const assert = require('node:assert/strict');
const cp = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const puppeteer = require('puppeteer');

const root=path.resolve(__dirname,'..');
const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'ds-blog-full-browser-'));
let server,browser,stage;
const mime={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.xml':'application/xml',
 '.png':'image/png','.jpg':'image/jpeg','.svg':'image/svg+xml','.webp':'image/webp'};
async function main(){
  const prepare=cp.spawnSync('python3',['tests/prepare_browser_fixture.py',scratch],
                             {cwd:root,encoding:'utf8'});
  if(prepare.status!==0)throw new Error('Fixture creation failed: '+prepare.stderr);
  const lines=prepare.stdout.trim().split('\n');
  const report=JSON.parse(lines[lines.length-1]);
  stage=report.stage.preview_root;
  assert.equal(report.verification.live_published,false);
  assert.equal(report.verification.mock_http,200);
  assert.equal(report.verification.email_status,'NOT_SENT');
  assert.equal(report.status.actual_emails_sent,0);
  assert.equal(report.stage.file_count,3);
  server=http.createServer((req,res)=>{
    const loc=new URL(req.url,'http://localhost').pathname;
    const file=path.resolve(stage,'.'+decodeURIComponent(loc));
    if(!file.startsWith(stage+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){
      res.writeHead(404);res.end('Missing');return;
    }
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
  const base='http://127.0.0.1:'+server.address().port;
  browser=await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:true,
    args:['--no-sandbox','--disable-dev-shm-usage']});
  let tests=0;
  async function check(label,fn){await fn();tests++;console.log('PASS '+label);}
  for(const width of [375,768,1440]){
    const page=await browser.newPage();
    await page.setViewport({width,height:width===375?812:950,deviceScaleFactor:1});
    await page.setRequestInterception(true);
    page.on('request',req=>req.url().startsWith(base)?req.continue():req.abort());
    const response=await page.goto(base+'/blog-v2.html',{waitUntil:'networkidle0'});
    await page.waitForSelector('header.site-header');
    await check('blog '+width+'px layout and 4 total cards',async()=>{
      assert.equal(response.status(),200);
      assert.equal(await page.$$eval('.lb-card',xs=>xs.length),4);
      assert.ok(await page.$eval('body',el=>el.scrollWidth <= innerWidth+1));
      for(const old of ['post-high-converting-websites.html','post-small-business-security.html','post-site-speed-revenue.html']){
        assert.equal(await page.$$eval('a[href="'+old+'"]',xs=>xs.length),1);
      }
    });
    await check('blog '+width+'px category filter isolates only fictional local story',async()=>{
      await page.click('[data-blog-filter="local"]');
      assert.equal(await page.$$eval('.lb-card:not([hidden])',xs=>xs.length),1);
      assert.match(await page.$eval('.lb-card:not([hidden]) h3',e=>e.textContent),/FICTIONAL TEST/);
    });
    if(width===375){
      await check('original mobile nav opens and closes',async()=>{
        await page.click('#menuBtn');
        assert.equal(await page.$eval('#menuBtn',x=>x.getAttribute('aria-expanded')),'true');
        await page.keyboard.press('Escape');
        assert.equal(await page.$eval('#menuBtn',x=>x.getAttribute('aria-expanded')),'false');
      });
    }
    const article=await page.goto(base+'/greeneville/proposed-synthetic-test-trail-1.html',{waitUntil:'networkidle0'});
    await check('article '+width+'px shows source and metadata',async()=>{
      assert.equal(article.status(),200);
      assert.ok(await page.$eval('body',el=>el.scrollWidth <= innerWidth+1));
      assert.match(await page.$eval('h1',e=>e.textContent),/FICTIONAL TEST/);
      assert.match(await page.$eval('.lb-article-meta',e=>e.textContent),/Proposed/);
      assert.equal(await page.$eval('link[rel=canonical]',e=>e.href),
                   'https://dsdigitaldesigns.org/greeneville/proposed-synthetic-test-trail-1.html');
      assert.ok(await page.$('a[href="https://www.greenevilletn.gov/o/tog/page/board-commission-agendas"]'));
      assert.ok(await page.$('header.site-header'));
      assert.ok(await page.$('#footer-slot footer'));
      assert.ok(await page.$('script[type="application/ld+json"]'));
    });
    await page.close();
  }
  const fixture=JSON.parse(fs.readFileSync(path.join(scratch,'private','manifests',
                       path.basename(stage).replace('release-','')+'.release-bundle.json'),'utf8'));
  await check('release delta excludes site replacement and lists only 3 files',async()=>{
    assert.equal(fixture.paths.length,3);
    assert.deepEqual(fixture.paths.map(x=>x.path),
      ['blog-v2.html','sitemap.xml','greeneville/proposed-synthetic-test-trail-1.html']);
    assert.equal(fixture.mode,'SIMULATION_ONLY');
  });
  await check('email simulation status remains NOT_SENT',async()=>{
    assert.equal(report.status.notification_previews_not_sent,1);
    assert.equal(report.status.actual_emails_sent,0);
  });
  console.log('SUMMARY '+tests+' browser/integration checks passed; zero actual emails; zero live publishing.');
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1})
.finally(async()=>{
  if(browser)await browser.close();
  if(server)await new Promise(ok=>server.close(ok));
  fs.rmSync(scratch,{recursive:true,force:true});
  if(stage&&stage.startsWith(path.join(root,'build')+path.sep))
    fs.rmSync(stage,{recursive:true,force:true});
});