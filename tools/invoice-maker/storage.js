import {demoInvoice,newInvoice,validateInvoice,validPerson,DESIGNS} from './model.js';
const NAME='ds-digital-invoices';
const STORES=['profiles','customers','invoices','drafts','preferences','numbering'];
let connection;
export function openDB(){
 if(connection)return Promise.resolve(connection);
 return new Promise((resolve,reject)=>{const r=indexedDB.open(NAME,1);r.onupgradeneeded=()=>{for(const s of STORES)r.result.createObjectStore(s);};r.onerror=()=>reject(r.error);r.onblocked=()=>reject(new Error('Close other Invoice Maker tabs to finish opening storage.'));r.onsuccess=()=>{connection=r.result;connection.onversionchange=()=>{connection.close();connection=null;};resolve(connection);};});
}
async function transaction(names,mode,work){const db=await openDB();return new Promise((resolve,reject)=>{const t=db.transaction(names,mode);let result;try{result=work(t);}catch(e){t.abort();reject(e);return;}t.oncomplete=()=>resolve(typeof result==='function'?result():result);t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error||new Error('Storage transaction failed.'));});}
export const get=(store,key)=>transaction([store],'readonly',t=>{let value;const r=t.objectStore(store).get(key);r.onsuccess=()=>value=r.result;return()=>value;});
export const all=store=>transaction([store],'readonly',t=>{let value;const r=t.objectStore(store).getAll();r.onsuccess=()=>value=r.result;return()=>value;});
export async function saveDraft(d,step){return transaction(['drafts','profiles','preferences'],'readwrite',t=>{t.objectStore('drafts').put(d,'active');t.objectStore('preferences').put({design:d.design,step},'ui');if(!d.demo)t.objectStore('profiles').put(d.sender,'sender');});}
export async function saveInvoice(d){validateInvoice(d,true);const existing=await all('invoices');if(existing.some(x=>x.id!==d.id&&x.number.trim().toLowerCase()===d.number.trim().toLowerCase()))throw new Error('That invoice number is already saved. Use a different number.');return transaction(['invoices','customers','profiles'],'readwrite',t=>{t.objectStore('invoices').put(d,d.id);if(!d.demo){t.objectStore('profiles').put(d.sender,'sender');const key=[d.customer.name,d.customer.address,d.customer.email].join('|').toLocaleLowerCase();t.objectStore('customers').put(d.customer,key);}});}
export async function removeInvoice(id){return transaction(['invoices','drafts'],'readwrite',t=>{t.objectStore('invoices').delete(id);const r=t.objectStore('drafts').get('active');r.onsuccess=()=>{if(r.result?.id===id)t.objectStore('drafts').delete('active');};});}
export async function createInvoice(){const profile=await get('profiles','sender');const pref=await get('preferences','ui');return transaction(['numbering','invoices','drafts'],'readwrite',t=>{let result;const year=new Date().getFullYear();const r=t.objectStore('numbering').get(year);r.onsuccess=()=>{let n=(r.result||0)+1;const q=t.objectStore('invoices').getAll();q.onsuccess=()=>{const used=new Set(q.result.map(d=>d.number));let number;do{number=`INV-${year}-${String(n++).padStart(4,'0')}`;}while(used.has(number));result=newInvoice(number,profile,pref?.design);t.objectStore('numbering').put(n-1,year);t.objectStore('drafts').put(result,'active');};};return()=>result;});}
export async function snapshot(){return transaction(STORES,'readonly',t=>{const data={format:'ds-digital-invoices',version:1,createdAt:new Date().toISOString(),stores:{}};for(const s of STORES){const entries=[];data.stores[s]=entries;const r=t.objectStore(s).openCursor();r.onsuccess=()=>{const c=r.result;if(c){entries.push([c.key,c.value]);c.continue();}};}return data;});}
export function validateBackup(b){
 if(!b||b.format!=='ds-digital-invoices'||b.version!==1||!b.stores||Object.keys(b.stores).sort().join()!==STORES.slice().sort().join())throw new Error('This is not a supported Invoice Maker backup.');
 for(const s of STORES){if(!Array.isArray(b.stores[s])||b.stores[s].length>10000)throw new Error('Backup has too many records.');const keys=new Set();for(const pair of b.stores[s]){if(!Array.isArray(pair)||pair.length!==2)throw new Error('Invalid backup record.');const [k,v]=pair;if(!['string','number'].includes(typeof k)||String(k).length>1000||keys.has(String(k)))throw new Error('Invalid or duplicate record key.');keys.add(String(k));
 if(s==='invoices'||s==='drafts'){validateInvoice(v,s==='invoices',s==='drafts');if(s==='invoices'&&k!==v.id)throw new Error('Invoice key mismatch.');if(s==='drafts'&&k!=='active')throw new Error('Invalid draft key.');}
 if((s==='profiles'||s==='customers')&&!validPerson(v))throw new Error('Invalid contact data.');
 if(s==='profiles'&&k!=='sender')throw new Error('Invalid profile key.');
 if(s==='numbering'&&(!Number.isInteger(k)||k<1900||k>9999||!Number.isSafeInteger(v)||v<0||v>99999999))throw new Error('Invalid invoice numbering.');
 if(s==='preferences'&&(k!=='ui'||!DESIGNS.includes(v?.design)||!Number.isInteger(v.step)||v.step<0||v.step>5))throw new Error('Invalid preferences.');
 }}return b;
}
export async function restore(b){validateBackup(b);return transaction(STORES,'readwrite',t=>{for(const s of STORES){const store=t.objectStore(s);store.clear();for(const [k,v]of b.stores[s])store.put(v,k);}});}
export async function load(){return {invoice:await get('drafts','active')||demoInvoice(),step:(await get('preferences','ui'))?.step||0};}
