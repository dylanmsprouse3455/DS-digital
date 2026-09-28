export const DESIGNS = ['classic', 'clean', 'minimal'];
export const money = cents => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format((cents||0)/100);
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
export const uid = () => crypto.randomUUID();
export const dateLabel = s => s ? new Date(s+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '';
export function decimal(value, places=2) {
  const str=String(value).trim();
  if (!new RegExp(`^\\d{1,8}(?:\\.\\d{1,${places}})?$`).test(str)) throw new Error('Enter a positive number with up to two decimal places.');
  const [whole,frac='']=str.split('.');
  return Number(whole)*10**places+Number(frac.padEnd(places,'0'));
}
export function totals(invoice) {
  const rows=invoice.items.map(x=>Math.round(decimal(x.rate)*decimal(x.quantity)/100));
  const subtotal=rows.reduce((a,b)=>a+b,0);
  const discount=invoice.discountType==='percent' ? Math.round(subtotal*decimal(invoice.discount)/10000) : decimal(invoice.discount);
  if(discount>subtotal) throw new Error('Discount cannot exceed the subtotal.');
  const tax=Math.round((subtotal-discount)*decimal(invoice.tax)/10000);
  const total=subtotal-discount+tax;
  if(!Number.isSafeInteger(total)||total>99999999999) throw new Error('Invoice total is too large.');
  return {rows,subtotal,discount,tax,total};
}
export const blankPerson=()=>({name:'',detail:'',email:'',phone:'',address:''});
export function newInvoice(number, profile=blankPerson(), design='clean') {
  return {id:uid(),number,date:today(),due:'Due on receipt',reference:'',sender:{...profile},customer:blankPerson(),items:[{id:uid(),date:today(),description:'',quantity:'1',rate:'0.00'}],tax:'0',discount:'0',discountType:'amount',message:'Thank you for your business!',payment:'Payment due upon receipt.',design,demo:false,updatedAt:new Date().toISOString()};
}
export function demoInvoice() {
  const d=newInvoice('INV-2026-0042');
  return {...d,id:'demo-invoice',date:'2026-09-28',demo:true,sender:{name:'Blue Ridge Cleaning Co.',detail:'',phone:'(555) 014-7284',email:'hello@example.com',address:'123 Main Street\nGreeneville, TN 37743'},customer:{name:'Example Client LLC',detail:'Johnson City Office',phone:'',email:'',address:'456 Market Street\nJohnson City, TN 37601'},items:[{id:'demo-1',date:'2026-09-14',description:'Office Cleaning Service',quantity:'1',rate:'125.00'},{id:'demo-2',date:'2026-09-28',description:'Office Cleaning Service',quantity:'1',rate:'125.00'}]};
}
function string(v,max){return typeof v==='string'&&v.length<=max&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(v);}
export function validPerson(p){return p&&['name','detail','email','phone','address'].every(k=>string(p[k],k==='address'?400:120));}
export function validDate(v){return /^\d{4}-\d{2}-\d{2}$/.test(v)&&!Number.isNaN(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;}
export function validateInvoice(d, final=false, draft=false) {
  if(!d||!string(d.id,80)||!d.id||!string(d.number,60)||!(validDate(d.date)||(draft&&d.date===''))||!string(d.due,120)||!string(d.reference,120)||!validPerson(d.sender)||!validPerson(d.customer)||!DESIGNS.includes(d.design)||typeof d.demo!=='boolean'||!string(d.updatedAt,40)) throw new Error('Invoice data is invalid.');
  if(!string(d.message,2000)||!string(d.payment,2000)||!['amount','percent'].includes(d.discountType)||!Array.isArray(d.items)||d.items.length<1||d.items.length>200) throw new Error('Use between 1 and 200 services and keep notes under 2,000 characters.');
  for(const x of d.items){if(!string(x.id,80)||!string(x.description,6000)||!(validDate(x.date)||(draft&&x.date===''))||!string(x.quantity,12)||!string(x.rate,12)||(!draft&&(decimal(x.quantity)<=0||decimal(x.quantity)>1000000||decimal(x.rate)>1000000000))) throw new Error('Check each service date, quantity and rate.');}
  if(!string(d.tax,12)||!string(d.discount,12))throw new Error('Invalid adjustment data.');
  if(!draft&&(decimal(d.tax)>10000||(d.discountType==='percent'&&decimal(d.discount)>10000)))throw new Error('Tax and percentage discounts must be between 0 and 100.');
  if(!draft)totals(d);
  if(final&&(!d.sender.name.trim()||!d.customer.name.trim()||!d.number.trim()||d.items.some(x=>!x.description.trim())))throw new Error('Add your name, a customer, an invoice number and a description for every service.');
  return d;
}
