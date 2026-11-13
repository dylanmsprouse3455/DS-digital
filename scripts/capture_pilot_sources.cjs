#!/usr/bin/env node
'use strict';
/* One-time owner-authorized official page evidence capture.
 * No crawling beyond the two fixed municipal pages, no site writes,
 * and no storage inside the public DS-digital repository.
 */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const puppeteer=require('puppeteer');

const output=path.resolve(process.argv[2]||'');
if(!output.startsWith('/var/lib/kali-ai-remote/ds-blog-pilot-evidence-006'))
  throw new Error('Output must stay in the isolated private pilot evidence directory');
const sources=[
 {id:'town-events',url:'https://www.greenevilletn.gov/events',
  requires:['Historic Zoning Commission Meeting','The item will be on the Nov. 17 meeting agenda.','Greeneville Energy Authority']},
 {id:'historic-zoning-commission',url:'https://www.greenevilletn.gov/page/historic-zoning-commission',
  requires:['Historic Zoning Commission','first and third Tuesdays','G. Thomas Love']}
];
async function run(){
 fs.mkdirSync(output,{recursive:true,mode:0o700});
 fs.chmodSync(output,0o700);
 const browser=await puppeteer.launch({executablePath:'/usr/bin/chromium',headless:true,
                                      args:['--no-sandbox','--disable-dev-shm-usage']});
 const results=[];
 try{
  for(const item of sources){
   const p=await browser.newPage();
   try{
    await p.setViewport({width:1280,height:800});
    const resp=await p.goto(item.url,{waitUntil:'domcontentloaded',timeout:25000});
    if(resp.status()!==200||p.url()!==item.url)
      throw new Error('Official source HTTP/URL mismatch '+item.id);
    await p.waitForFunction(
      required=>required.every(term=>document.body.innerText.includes(term)),
      {timeout:20000},item.requires
    );
    const text=await p.evaluate(()=>document.body.innerText);
    if(text.length<400||text.length>350000)throw Error('Unexpected document size');
    for(const term of item.requires)
      if(!text.includes(term))throw Error('Expected exact primary-source evidence is absent: '+term);
    const sha=crypto.createHash('sha256').update(Buffer.from(text)).digest('hex');
    const file=path.join(output,item.id+'.txt');
    if(fs.existsSync(file)){
      const existing=fs.readFileSync(file);
      if(crypto.createHash('sha256').update(existing).digest('hex')!==sha)
        throw Error('Previously captured source changed; requires separate new revision');
    }else{
      fs.writeFileSync(file,text,{flag:'wx',mode:0o600});
    }
    results.push({id:item.id,url:item.url,http_status:200,title:await p.title(),
                  captured_at:new Date().toISOString(),sha256:sha,raw_bytes:Buffer.byteLength(text),
                  mode:'rendered official public web page visible text',
                  source_text_path:file});
    console.log('VERIFIED',item.id,'sha256',sha.slice(0,16),'bytes',Buffer.byteLength(text));
   }finally{await p.close()}
  }
  const f=path.join(output,'capture-metadata.json');
  fs.writeFileSync(f,JSON.stringify({schema_version:1,notes:'Official public sources only; private provenance, not permission to republish raw text.',sources:results},null,2),{flag:'wx',mode:0o600});
  console.log('SAVED_PRIVATE_SOURCE_EVIDENCE',f);
 }finally{await browser.close()}
}
run().catch(e=>{console.error('PILOT_CAPTURE_BLOCKED:',e.message);process.exitCode=1});