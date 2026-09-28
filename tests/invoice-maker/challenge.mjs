import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {launch,ready,out,report,base,saved} from './helpers.mjs';
const b=await launch();await fs.mkdir(out,{recursive:true});const results=[];
try{
 const c=await b.newContext(),p=await c.newPage();p.on('dialog',d=>d.accept());await ready(p);
 // Invalid restore must reject before any write. Compare every store before/after.
 const storage=await p.evaluate(async()=>{const s=await import('./storage.js');const before=await s.snapshot();const bad=structuredClone(before);bad.stores.drafts[0][1].items[0].description={html:'invalid'};let rejected=false;try{await s.restore(bad);}catch{rejected=true;}const after=await s.snapshot();const ids=await Promise.all(Array.from({length:12},()=>s.createInvoice()));return {rejected,unchanged:JSON.stringify(before.stores)===JSON.stringify(after.stores),numbers:ids.map(i=>i.number)};});assert(storage.rejected&&storage.unchanged);assert.equal(new Set(storage.numbers).size,12);results.push('atomic invalid restore rejection; concurrent numbering unique');
 // No silently lost draft when another tab opens.
 const second=await c.newPage();await second.goto(base+'/tools/invoice-maker/');await second.getByText('Already open in another tab',{exact:true}).waitFor();await second.close();results.push('second editor tab blocked without overwriting draft');
 // Incomplete numeric drafts must survive backup / restore.
 assert(await p.evaluate(async()=>{const s=await import('./storage.js'),m=await import('./model.js');const d=m.demoInvoice();d.items[0].rate='';await s.saveDraft(d,3);const b=await s.snapshot();await s.restore(b);return (await s.load()).invoice.items[0].rate==='';}));results.push('unfinished draft round trip');
 // Generate a real multipage PDF with long descriptions and many rows for every design.
 for(const design of ['classic','clean','minimal']){
  const result=await p.evaluate(async design=>{const {demoInvoice}=await import('./model.js');const {layout,generatePDF}=await import('./document.js');const d=demoInvoice();d.design=design;d.items[0].description='Long service detail: '+('Inspect and clean the complete office including all fixtures and floors. '.repeat(65))+' END_LONG_DESCRIPTION';for(let i=0;i<42;i++)d.items.push({id:'extra-'+i,date:'2026-09-28',description:'Additional fictional service '+i,quantity:'1.5',rate:'10.10'});d.tax='7.25';d.discount='25';d.message='FINAL_MESSAGE_MARKER';d.payment='PAYMENT_INSTRUCTIONS_MARKER';const model=await layout(d);const {blob}=await generatePDF(d);return {pages:model.pages,textBounds:model.pages.flatMap((page,index)=>page.filter(o=>o.type==='text').map(o=>({...o,page:index}))),bytes:Array.from(new Uint8Array(await blob.arrayBuffer()))};},design);
  assert(result.pages.length>=3);for(const op of result.textBounds){assert(op.x>=40&&op.x+op.width<=573,`horizontal text bounds ${design}: ${op.text}`);assert(op.y>=30&&op.y<=765,`vertical text bounds ${design}: ${op.text}`);}
  const file=path.join(out,`long-${design}.pdf`);await fs.writeFile(file,Buffer.from(result.bytes));const info=execFileSync('pdfinfo',[file],{encoding:'utf8'});assert.match(info,/612 x 792 pts/);const text=execFileSync('pdftotext',['-layout',file,'-'],{encoding:'utf8'});for(const marker of ['END_LONG_DESCRIPTION','Additional fictional service 41','FINAL_MESSAGE_MARKER','PAYMENT_INSTRUCTIONS_MARKER'])assert(text.includes(marker),`${design}: missing ${marker}`);assert(!/Next|Back|Saved invoices|Your Information/.test(text));assert.match(text,/\$923\.74/);results.push(`${design}: ${result.pages.length} US Letter pages, text, margins, totals, pagination`);
 }
 // Deliberately extreme valid text and amounts must remain inside the document.
 for(const design of ['classic','clean','minimal']){
  const ops=await p.evaluate(async design=>{const {demoInvoice}=await import('./model.js'),{layout}=await import('./document.js');const d=demoInvoice();d.design=design;d.number='W'.repeat(60);d.sender.name='Example Business '.repeat(7);d.customer.name='Example Client '.repeat(8);d.items[0].rate='9999999';d.items[0].quantity='1';return (await layout(d)).pages.flat();},design);
  for(const o of ops.filter(o=>o.type==='text'))assert(o.x>=40&&o.x+o.width<=573&&o.y<=765,`extreme bounds ${design}: ${o.text}`);
 }
 results.push('long contact names, invoice numbers and large amounts stay inside margins');
 // User text stays inert when rendered in forms and SVG.
 await p.evaluate(async()=>{const s=await import('./storage.js'),m=await import('./model.js');const d=m.demoInvoice();d.sender.name='<img src=x onerror=alert(1)>';await s.saveDraft(d,0);});
 await p.reload();await saved(p);assert.equal(await p.locator('[data-field="sender.name"]').inputValue(),'<img src=x onerror=alert(1)>');assert.equal(await p.locator('#side-preview img').count(),0);results.push('HTML-like user content remains inert');
 // Every real UI-generated PDF has exact demo totals and clean content.
 for(const width of [390,430,1280])for(const d of ['classic','clean','minimal']){const f=path.join(out,`${d}-${width}.pdf`);const info=execFileSync('pdfinfo',[f],{encoding:'utf8'});assert.match(info,/Pages:\s+1/);assert.match(info,/612 x 792 pts/);const text=execFileSync('pdftotext',['-layout',f,'-'],{encoding:'utf8'});assert(text.includes('Blue Ridge Cleaning Co.'));assert(text.includes('Example Client LLC'));assert(text.includes('$250.00'));assert(!/Next|Back|Saved invoices|Your Information/.test(text));}
 results.push('nine UI-downloaded PDFs: correct page size, demo, total, no application UI');
 // Positive control confirms a forbidden UI text detector can actually fail.
 assert(/Next|Back|Saved invoices|Your Information/.test('Next →'));results.push('PDF unwanted-text positive control');
 // Storage failure leaves a usable recovery export.
 const blocked=await b.newContext();await blocked.addInitScript(()=>{Object.defineProperty(window,'indexedDB',{get(){throw new Error('Simulated unavailable storage');}});});const q=await blocked.newPage();await q.goto(base+'/tools/invoice-maker/');await q.getByText('Storage unavailable',{exact:true}).waitFor();await q.getByRole('button',{name:'Backup and storage settings'}).click();const dl=q.waitForEvent('download');await q.getByRole('button',{name:'Export Backup',exact:true}).click();const backup=await dl;const f=path.join(out,'recovery.json');await backup.saveAs(f);const payload=JSON.parse(await fs.readFile(f));assert.equal(payload.stores.drafts[0][1].sender.name,'Blue Ridge Cleaning Co.');await blocked.close();results.push('blocked storage is visible and current draft recovery exports');
 await c.close();await report('challenge',{status:'passed',results});console.log('CHALLENGE ACCEPTANCE PASSED: '+results.join('; '));
}finally{await b.close();}
