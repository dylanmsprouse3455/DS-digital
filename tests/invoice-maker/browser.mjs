import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {launch,ready,go,saved,idle,out,report,base} from './helpers.mjs';
await fs.mkdir(out,{recursive:true});const b=await launch();const results=[];
try{
 for(const width of [390,430,1280]){
  const context=await b.newContext({viewport:{width,height:900},acceptDownloads:true,isMobile:width<500,hasTouch:width<500});const p=await context.newPage();const errors=[],foreign=[];
  p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});p.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('blob:'))foreign.push(r.url());});p.on('dialog',d=>d.accept());
  await ready(p);assert.equal(await p.locator('[data-field="sender.name"]').inputValue(),'Blue Ridge Cleaning Co.');
  await p.screenshot({path:path.join(out,`sender-${width}.png`),fullPage:true});
  for(let n=1;n<=6;n++){
   await go(p,n);if(n===5)await p.waitForSelector('#mini-minimal svg');
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow step ${n}, ${width}`);
   if(n===4||n===5||n===6)await p.screenshot({path:path.join(out,`step-${n}-${width}.png`),fullPage:true});
  }
  await p.getByRole('button',{name:'← Back',exact:true}).click();await idle(p);assert.equal(await p.locator('#step-label').textContent(),'5 of 6');await p.getByRole('button',{name:'Preview →',exact:true}).click();await idle(p);
  // Save demo; export each design using the real download control.
  await p.getByRole('button',{name:'Save invoice',exact:true}).click();await idle(p);assert.equal(await p.locator('#saved-count').textContent(),'1');
  for(const design of ['Classic','Clean','Minimal']){
   await go(p,5);await p.waitForSelector('#mini-minimal svg');await p.locator(`[data-action="design"][data-design="${design.toLowerCase()}"]`).click();await idle(p);await saved(p);await go(p,6);
   const download=p.waitForEvent('download');await p.getByRole('button',{name:'Download PDF ↓',exact:true}).click();await idle(p);const d=await download;await d.saveAs(path.join(out,`${design.toLowerCase()}-${width}.pdf`));assert.equal(await d.failure(),null);
  }
  // New invoice, real editing, autosave and reload.
  await p.locator('.toolbar-buttons [data-action="new"]').click();await idle(p);assert.equal(await p.locator('[data-field="sender.name"]').inputValue(),'');await p.locator('[data-field="sender.name"]').fill('Example Studio');await p.locator('[data-field="sender.email"]').fill('billing@example.com');await saved(p);await p.reload();await saved(p);assert.equal(await p.locator('[data-field="sender.name"]').inputValue(),'Example Studio');
  await go(p,2);await p.locator('[data-field="customer.name"]').fill('Example Client Two');await p.locator('[data-field="customer.address"]').fill('789 Example Avenue\nExample City, TN 37000');
  await go(p,3);const firstNumber=await p.locator('[data-field="number"]').inputValue();assert.match(firstNumber,/INV-\d{4}-0001/);
  await go(p,4);const long='Detailed cleaning of the reception area, shared workspaces, floors, windows and fixtures. '.repeat(8);await p.locator('[data-field="items.0.description"]').fill(long);await p.locator('[data-field="items.0.rate"]').fill('125');await p.locator('[data-field="items.0.quantity"]').fill('2');await p.getByRole('button',{name:'＋ Add service',exact:true}).click();await idle(p);await p.locator('[data-field="items.1.description"]').fill('Additional service');await p.locator('[data-field="items.1.rate"]').fill('50');await p.locator('[data-action="remove-service"][data-index="1"]').click();await idle(p);assert.equal(await p.locator('.service').count(),1);
  await p.locator('summary').filter({hasText:'Tax & discount'}).click();await idle(p);await p.locator('[data-field="tax"]').fill('7.25');await p.locator('[data-field="discountType"]').selectOption('percent');await p.locator('[data-field="discount"]').fill('10');assert.match(await p.locator('.totals').textContent(),/\$241\.31/);await saved(p);
  assert.equal(await p.locator('[data-field="items.0.description"]').evaluate(e=>e.scrollHeight<=e.clientHeight+3),true,'description truncated');
  await go(p,6);await p.getByRole('button',{name:'Save invoice',exact:true}).click();await idle(p);assert.equal(await p.locator('#saved-count').textContent(),'2');
  await p.locator('.toolbar-buttons [data-action="new"]').click();await idle(p);assert.equal(await p.locator('[data-field="sender.name"]').inputValue(),'Example Studio');await go(p,2);await p.locator('#reuse-customer').selectOption('0');await p.waitForFunction(()=>document.querySelector('[data-field="customer.name"]').value==='Example Client Two');assert.equal(await p.locator('[data-field="customer.name"]').inputValue(),'Example Client Two');await go(p,3);assert.match(await p.locator('[data-field="number"]').inputValue(),/0002$/);
  await p.getByRole('button',{name:/Saved invoices/}).click();await idle(p);const row=p.locator('.library-row').filter({hasText:firstNumber});await row.getByRole('button',{name:'Duplicate',exact:true}).click();await idle(p);await go(p,3);const dupNumber=await p.locator('[data-field="number"]').inputValue();assert.match(dupNumber,/0003$/);await go(p,6);await p.getByRole('button',{name:'Save invoice',exact:true}).click();await idle(p);assert.equal(await p.locator('#saved-count').textContent(),'3');
  // Backup, deletion, restore, reopened content and design/step persistence.
  await p.getByRole('button',{name:'Backup and storage settings'}).click();await idle(p);const backupDownload=p.waitForEvent('download');await p.getByRole('button',{name:'Export Backup',exact:true}).click();await idle(p);const backup=await backupDownload;const backupFile=path.join(out,`backup-${width}.json`);await backup.saveAs(backupFile);const payload=JSON.parse(await fs.readFile(backupFile,'utf8'));assert.equal(payload.stores.invoices.length,3);
  await p.getByRole('button',{name:'Close dialog'}).click();await idle(p);await p.getByRole('button',{name:/Saved invoices/}).click();await idle(p);await p.locator('.library-row').filter({hasText:dupNumber}).getByRole('button',{name:'Delete',exact:true}).click();await idle(p);assert.equal(await p.locator('#saved-count').textContent(),'2');await p.getByRole('button',{name:'Close dialog'}).click();await idle(p);await p.locator('#restore-file').setInputFiles(backupFile);await p.waitForFunction(()=>document.querySelector('#notice').textContent.startsWith('Backup restored'));assert.equal(await p.locator('#saved-count').textContent(),'3');await p.reload();await saved(p);assert.equal(await p.locator('#step-label').textContent(),'6 of 6');
  await p.getByRole('button',{name:/Saved invoices/}).click();await idle(p);await p.locator('.library-row').filter({hasText:firstNumber}).getByRole('button',{name:'Open',exact:true}).click();await idle(p);await go(p,4);assert.equal(await p.locator('[data-field="items.0.description"]').inputValue(),long);assert.match(await p.locator('.totals').textContent(),/241\.31/);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[],`console ${width}`);assert.deepEqual(foreign,[],`external invoice request ${width}`);results.push({width,allFlows:'passed',consoleErrors:errors,externalRequests:foreign});await context.close();
 }
 await report('browser',{status:'passed',results});console.log('BROWSER ACCEPTANCE PASSED: 390px, 430px, desktop; all wizard, lifecycle, persistence, backup and PDF flows');
}finally{await b.close();}
