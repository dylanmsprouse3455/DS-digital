import {totals,money,dateLabel,validateInvoice} from './model.js';
const FONTS=[['LiberationSans-Regular.ttf','InvoiceSans','normal'],['LiberationSans-Bold.ttf','InvoiceSans','bold'],['LiberationSerif-Regular.ttf','InvoiceSerif','normal'],['LiberationSerif-Bold.ttf','InvoiceSerif','bold']];
let fontData;
async function fonts(){return fontData ||= Promise.all(FONTS.map(async ([file,family,weight])=>{const r=await fetch(new URL('./vendor/'+file,import.meta.url));if(!r.ok)throw new Error('The invoice fonts could not load. Please reload.');const bytes=new Uint8Array(await r.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return {file,family,weight,data:btoa(binary)};})).catch(e=>{fontData=null;throw e;});}
async function pdf(){const d=new window.jspdf.jsPDF({unit:'pt',format:'letter',compress:true,putOnlyUsedFonts:true});for(const f of await fonts()){d.addFileToVFS(f.file,f.data);d.addFont(f.file,f.family,f.weight);}return d;}
export async function layout(invoice, design=invoice.design){
 validateInvoice(invoice);const metric=await pdf();const pages=[[]];let ops=pages[0];
 const classic=design==='classic',minimal=design==='minimal';const ink=classic?'#18242d':minimal?'#262421':'#152d45';const accent=classic?'#455e69':minimal?'#71644f':'#2563eb';const muted='#52616e';const family=classic?'InvoiceSerif':'InvoiceSans';
 const text=(value,x,y,size=10,weight='normal',color=ink,font='InvoiceSans',align='left')=>{metric.setFont(font,weight);metric.setFontSize(size);const width=metric.getTextWidth(String(value));ops.push({type:'text',text:String(value),x:align==='right'?x-width:x,y,size,weight,color,font,width});};
 function fit(value,x,y,size,maxWidth,weight='normal',color=ink,font='InvoiceSans',align='left'){metric.setFont(font,weight);metric.setFontSize(size);const width=metric.getTextWidth(String(value));text(value,x,y,Math.min(size,size*maxWidth/Math.max(width,1)),weight,color,font,align);}
 const rect=(x,y,w,h,color)=>ops.push({type:'rect',x,y,w,h,color});
 const line=(x,y,x2,color='#dce2e7',width=.6)=>ops.push({type:'line',x,y,x2,color,width});
 function wrap(value,width,size=10,font='InvoiceSans',weight='normal'){
  metric.setFont(font,weight);metric.setFontSize(size);
  // Split long words as well as paragraphs; jsPDF measures the embedded font.
  return String(value).replace(/\r/g,'').split('\n').flatMap(p=>metric.splitTextToSize(p||' ',width));
 }
 function block(value,x,y,width,size=10,font='InvoiceSans',weight='normal',color=ink){const lines=wrap(value,width,size,font,weight);for(const s of lines){text(s,x,y,size,weight,color,font);y+=size*1.45;}return y;}
 const party=(p,x,y,w)=>{y=block(p.name||'Business name',x,y,w,12,family,'bold');if(p.detail)y=block(p.detail,x,y,w,10);const details=[p.address,p.email,p.phone].filter(Boolean).join('\n');return details?block(details,x,y+4,w,10,'InvoiceSans','normal',muted):y;};
 const total=totals(invoice);
 let y;
 if(classic){
  metric.setFont('InvoiceSerif','normal');metric.setFontSize(34);text('INVOICE',(612-metric.getTextWidth('INVOICE'))/2,72,34,'normal',ink,'InvoiceSerif');
  line(44,94,568,ink,1);fit(invoice.number,44,116,10,330,'bold');text(dateLabel(invoice.date),568,116,10,'normal',muted,'InvoiceSans','right');
  text('FROM',44,153,8,'bold',accent);text('BILL TO',326,153,8,'bold',accent);
  y=Math.max(party(invoice.sender,44,174,240),party(invoice.customer,326,174,242))+18;
  y=block('TERMS  '+invoice.due+(invoice.reference?'   /   REFERENCE  '+invoice.reference:''),44,y,524,9,'InvoiceSans','normal',muted)+20;
 }else if(minimal){
  rect(44,42,32,4,accent);text('Invoice',44,107,51,'normal',ink,'InvoiceSerif');
  y=block(invoice.number,352,64,216,11,'InvoiceSans','bold');y=block(dateLabel(invoice.date)+'\n'+invoice.due+(invoice.reference?'\nRef: '+invoice.reference:''),352,y+8,216,10,'InvoiceSans','normal',muted);
  const top=Math.max(160,y+26);text('ISSUED BY',44,top,8,'bold',accent);text('PREPARED FOR',310,top,8,'bold',accent);
  y=Math.max(party(invoice.sender,44,top+23,238),party(invoice.customer,310,top+23,258))+32;
 }else{
  rect(0,0,612,9,accent);text('INVOICE',44,65,30,'bold',ink);text('AMOUNT DUE',568,45,8,'bold',muted,'InvoiceSans','right');text(money(total.total),568,80,26,'bold',accent,'InvoiceSans','right');
  y=block(invoice.number+'  ·  '+dateLabel(invoice.date),44,91,300,10,'InvoiceSans','normal',muted);line(44,119,568);
  text('FROM',44,148,8,'bold',accent);text('BILL TO',320,148,8,'bold',accent);
  y=Math.max(party(invoice.sender,44,170,242),party(invoice.customer,320,170,248))+18;
  y=block('DUE  '+invoice.due+(invoice.reference?'   /   REFERENCE  '+invoice.reference:''),44,y,524,9,'InvoiceSans','normal',muted)+18;
 }
 const cols=minimal?{date:44,desc:44,qty:438,rate:502,end:568}:{date:52,desc:150,qty:436,rate:502,end:560};
 function tableHeader(){
  if(y>660)newPage(false);
  if(classic){line(44,y-15,568,ink,1);line(44,y+8,568,ink,.5);}else if(!minimal)rect(44,y-16,524,30,'#edf3fc');else line(44,y+9,568,ink,1);
  if(!minimal)text('DATE',cols.date,y,8,'bold',accent);text(minimal?'SERVICES':'SERVICE / DESCRIPTION',cols.desc,y,8,'bold',accent);text('QTY',cols.qty,y,8,'bold',accent,'InvoiceSans','right');text('RATE',cols.rate,y,8,'bold',accent,'InvoiceSans','right');text('AMOUNT',cols.end,y,8,'bold',accent,'InvoiceSans','right');y+=32;
 }
 function newPage(withHeader=true){ops=[];pages.push(ops);fit('INVOICE  /  '+invoice.number,44,43,10,420,'bold',ink,family);text('CONTINUED',568,43,8,'normal',muted,'InvoiceSans','right');line(44,58,568);y=85;if(withHeader)tableHeader();}
 tableHeader();
 invoice.items.forEach((item,index)=>{
  const desc=wrap(item.description||'Service description',minimal?350:258,10);
  const height=Math.max(desc.length*14,28)+(minimal?31:15);
  if(y+height>694&&height<530)newPage();
  let first=true;
  for(let n=0;n<desc.length;n++){
   if(y>686){newPage();first=false;if(!minimal)text('(continued)',cols.date,y,8,'normal',muted);}
   if(first){if(!minimal)text(dateLabel(item.date),cols.date,y,8,'normal',muted);fit(item.quantity,cols.qty,y,9,30,'normal',ink,'InvoiceSans','right');fit(money(Math.round(Number(item.rate)*100)),cols.rate,y,9,56,'normal',ink,'InvoiceSans','right');fit(money(total.rows[index]),cols.end,y,10,55,'bold',ink,'InvoiceSans','right');first=false;}
   text(desc[n],cols.desc,y,10);y+=14;
  }
  if(minimal){if(y>690)newPage();text(dateLabel(item.date),cols.date,y+2,8,'normal',muted);y+=17;}
  y+=13;line(44,y-3,568);y+=17;
 });
 // Keep totals intact. Notes are allowed to flow to subsequent pages.
 if(y+144>701)newPage(false);
 const tx=minimal?310:350;
 for(const [label,value]of [['Subtotal',total.subtotal],['Discount',-total.discount],[`Tax (${invoice.tax}%)`,total.tax]]){text(label,tx,y,10,'normal',muted);text(money(value),568,y,10,'normal',ink,'InvoiceSans','right');y+=22;}
 if(!minimal)rect(tx-12,y-7,580-tx,43,classic?'#f0f3f3':'#edf3fc');else line(tx,y-7,568,ink,1);
 text('TOTAL DUE',tx,y+19,10,'bold',accent);text(money(total.total),568,y+20,22,'bold',ink,minimal?'InvoiceSerif':'InvoiceSans','right');y+=65;
 for(const [label,value]of [['PAYMENT',invoice.payment],['',invoice.message]]){if(!value)continue;if(y>640)newPage(false);if(label){text(label,44,y,8,'bold',accent);y+=19;}for(const s of wrap(value,524,label?10:12,label?'InvoiceSans':family)){if(y>695)newPage(false);text(s,44,y,label?10:12,'normal',label?muted:ink,label?'InvoiceSans':family);y+=17;}y+=18;}
 pages.forEach((p,i)=>{ops=p;line(44,741,568);fit(invoice.number,44,760,8,440,'normal',muted);text(`${i+1} / ${pages.length}`,568,760,8,'normal',muted,'InvoiceSans','right');});
 return {pages,design,number:invoice.number};
}
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function svg(page){return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 612 792" role="img" aria-label="Invoice document preview"><rect width="612" height="792" fill="white"/>${page.map(o=>o.type==='text'?`<text x="${o.x}" y="${o.y}" font-size="${o.size}" font-family="${o.font}" font-weight="${o.weight==='bold'?700:400}" fill="${o.color}" xml:space="preserve">${esc(o.text)}</text>`:o.type==='rect'?`<rect x="${o.x}" y="${o.y}" width="${o.w}" height="${o.h}" fill="${o.color}"/>`:`<line x1="${o.x}" y1="${o.y}" x2="${o.x2}" y2="${o.y}" stroke="${o.color}" stroke-width="${o.width}"/>`).join('')}</svg>`;}
export async function generatePDF(invoice){validateInvoice(invoice,true);const model=await layout(invoice);const d=await pdf();d.setProperties({title:`Invoice ${invoice.number}`,subject:'Invoice',author:invoice.sender.name,creator:'DS Digital Designs Free Invoice Maker'});model.pages.forEach((page,i)=>{if(i)d.addPage('letter');for(const o of page){if(o.type==='text'){d.setFont(o.font,o.weight);d.setFontSize(o.size);d.setTextColor(o.color);d.text(o.text,o.x,o.y);}else if(o.type==='rect'){d.setFillColor(o.color);d.rect(o.x,o.y,o.w,o.h,'F');}else{d.setDrawColor(o.color);d.setLineWidth(o.width);d.line(o.x,o.y,o.x2,o.y);}}});return {blob:d.output('blob'),model};}
