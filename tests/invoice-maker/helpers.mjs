import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
export const base=process.env.INVOICE_BASE_URL||'http://127.0.0.1:8765';
export const out=path.resolve('test-results/invoice-maker');
export const launch=()=>chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
export async function ready(page){await page.goto(base+'/tools/invoice-maker/');await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='Saved on this device');await page.waitForSelector('#side-preview svg',{state:'attached'});}
export async function idle(page){await page.waitForFunction(()=>document.querySelector('#workspace').getAttribute('aria-busy')!=='true');}
export async function go(page,n){await page.getByRole('button',{name:new RegExp(`^${n}\\.`)}).click();await idle(page);await page.waitForFunction(n=>document.querySelector('#step-label').textContent===`${n} of 6`,n);}
export async function saved(page){await page.waitForFunction(()=>document.querySelector('#save-status').textContent==='Saved on this device');}
export async function hashes(){const list=['app.js','model.js','storage.js','document.js','styles.css','index.html'];return Object.fromEntries(await Promise.all(list.map(async f=>[f,crypto.createHash('sha256').update(await fs.readFile('tools/invoice-maker/'+f)).digest('hex')])));}
export async function report(name,data){await fs.mkdir(out,{recursive:true});await fs.writeFile(path.join(out,name+'.json'),JSON.stringify({at:new Date().toISOString(),base,hashes:await hashes(),...data},null,2));}
