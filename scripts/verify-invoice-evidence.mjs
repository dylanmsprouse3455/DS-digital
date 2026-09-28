import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {hashes} from '../tests/invoice-maker/helpers.mjs';
const current=await hashes();
const reports=[];
for(const name of ['browser','challenge','regression']){const r=JSON.parse(await fs.readFile(`test-results/invoice-maker/${name}.json`));assert.equal(r.status,'passed');assert.deepEqual(r.hashes,current,`${name}: evidence is stale`);reports.push({name,at:r.at,results:r.results});}
assert.deepEqual(reports[0].results.map(x=>x.width),[390,430,1280]);assert(reports[0].results.every(x=>x.consoleErrors.length===0&&x.externalRequests.length===0));
assert(reports[1].results.length>=10);
console.log(JSON.stringify({status:'passed',sourceHashes:current,reports,limits:['Chromium mobile emulation; physical iPhone and Safari not tested','Existing pages request a pre-existing missing chat-widget.js','Production deployment not established by these local reports']},null,2));
console.log('CURRENT MACHINE EVIDENCE VERIFIED');
