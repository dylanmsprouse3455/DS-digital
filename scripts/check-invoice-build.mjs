import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const root=process.cwd(),tool=path.join(root,'tools/invoice-maker');
const required=['index.html','styles.css','app.js','model.js','storage.js','document.js','vendor/jspdf.umd.min.js','vendor/JSPDF-LICENSE.txt','vendor/FONTS-LICENSE.txt','vendor/LiberationSans-Regular.ttf','vendor/LiberationSans-Bold.ttf','vendor/LiberationSerif-Regular.ttf','vendor/LiberationSerif-Bold.ttf'];
for(const f of required)assert((await fs.stat(path.join(tool,f))).size>0,f);
for(const f of required.filter(f=>f.endsWith('.js')))execFileSync(process.execPath,['--check',path.join(tool,f)]);
const html=await fs.readFile(path.join(tool,'index.html'),'utf8');
for(const m of html.matchAll(/(?:src|href)="([^"#]+)"/g)){const url=m[1];if(url.startsWith('https:'))continue;await fs.access(path.resolve(url.startsWith('/')?root:tool,url.replace(/^\//,'')));}
assert(!/googletagmanager|analytics|chat-widget/.test(html));
assert((await fs.readFile('free-tools.html','utf8')).includes('href="/tools/invoice-maker/"'));
assert((await fs.readFile('sitemap.xml','utf8')).includes('https://dsdigitaldesigns.org/tools/invoice-maker/'));
const hash=x=>createHash('sha256').update(x).digest('hex');
assert.equal(hash(await fs.readFile(path.join(tool,'vendor/jspdf.umd.min.js'))),hash(await fs.readFile('node_modules/jspdf/dist/jspdf.umd.min.js')),'vendored PDF version');
console.log('STATIC BUILD VERIFIED: complete static output, valid scripts, local assets, tool listing, sitemap, pinned PDF dependency');
