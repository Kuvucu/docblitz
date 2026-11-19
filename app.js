const $ = id => document.getElementById(id);
const LS = {get:(k,d)=>{try{return JSON.parse(localStorage.getItem(k))??d}catch{return d}}, set:(k,v)=>localStorage.setItem(k,JSON.stringify(v))};
const TYPES = {kp:'Коммерческое предложение', invoice:'Счёт на оплату', act:'Акт выполненных работ'};
const FREE_LIMIT = 5;
const sellerFields = ['sName','sInn','sPhone','sEmail','sBank'];

let state = {type:'kp', items:[{name:'',qty:1,price:0}]};

function rub(n){return n.toLocaleString('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2})}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

function plural(n,f){n=Math.abs(n)%100;const n1=n%10;if(n>10&&n<20)return f[2];if(n1>1&&n1<5)return f[1];if(n1==1)return f[0];return f[2]}
function triadWords(n,fem){
  const u=fem?['','одна','две','три','четыре','пять','шесть','семь','восемь','девять']:['','один','два','три','четыре','пять','шесть','семь','восемь','девять'];
  const t=['десять','одиннадцать','двенадцать','тринадцать','четырнадцать','пятнадцать','шестнадцать','семнадцать','восемнадцать','девятнадцать'];
  const d=['','','двадцать','тридцать','сорок','пятьдесят','шестьдесят','семьдесят','восемьдесят','девяносто'];
  const h=['','сто','двести','триста','четыреста','пятьсот','шестьсот','семьсот','восемьсот','девятьсот'];
  const r=[h[Math.floor(n/100)]];const dd=n%100;
  if(dd>=10&&dd<20)r.push(t[dd-10]);else{r.push(d[Math.floor(dd/10)]);r.push(u[dd%10])}
  return r.filter(Boolean).join(' ');
}
function amountInWords(sum){
  const rubles=Math.floor(sum+1e-9), kop=Math.round((sum-rubles)*100);
  if(rubles===0){return `Ноль рублей ${String(kop).padStart(2,'0')} ${plural(kop,['копейка','копейки','копеек'])}`}
  const orders=[[['',''],false,['рубль','рубля','рублей']],[0,true,['тысяча','тысячи','тысяч']],[0,false,['миллион','миллиона','миллионов']],[0,false,['миллиард','миллиарда','миллиардов']]];
  let n=rubles,i=0,parts=[];
  while(n>0&&i<orders.length){const tr=n%1000;if(tr||i===0){const w=triadWords(tr,orders[i][1]);parts.unshift((w?w+' ':'')+(i===0?'':plural(tr,orders[i][2])))}n=Math.floor(n/1000);i++}
  let s=parts.join(' ').replace(/\s+/g,' ').trim()+' '+plural(rubles,['рубль','рубля','рублей']);
  s+=` ${String(kop).padStart(2,'0')} ${plural(kop,['копейка','копейки','копеек'])}`;
  return s.charAt(0).toUpperCase()+s.slice(1);
}

function calc(){
  const sub=state.items.reduce((a,i)=>a+(+i.qty||0)*(+i.price||0),0);
  const disc=sub*Math.min(Math.max(+$('discount').value||0,0),100)/100;
  const base=sub-disc;const vat=$('vat').value;
  let vatSum=0,total=base;
  if(vat==='20in')vatSum=base*20/120;
  if(vat==='20top'){vatSum=base*0.2;total=base+vatSum}
  return {sub,disc,vatSum,total,vat};
}

function renderItems(){
  $('items').innerHTML='';
  state.items.forEach((it,idx)=>{
    const row=document.createElement('div');row.className='item';
    row.innerHTML=`<input placeholder="Услуга или товар" value="${esc(it.name)}"><input type="number" min="0" step="any" value="${it.qty}"><input type="number" min="0" step="any" value="${it.price}"><button class="btn danger" title="Удалить">✕</button>`;
    const [n,q,p,del]=row.children;
    n.oninput=e=>{it.name=e.target.value;render()};
    q.oninput=e=>{it.qty=e.target.value;render()};
    p.oninput=e=>{it.price=e.target.value;render()};
    del.onclick=()=>{state.items.splice(idx,1);if(!state.items.length)state.items.push({name:'',qty:1,price:0});renderItems();render()};
    $('items').appendChild(row);
  });
}

function isPro(){return LS.get('pro',false)}
function monthKey(){const d=new Date();return `cnt_${d.getFullYear()}_${d.getMonth()}`}
function usedThisMonth(){return LS.get(monthKey(),0)}

function render(){
  const c=calc();const d=$('date').value?new Date($('date').value).toLocaleDateString('ru-RU'):'';
  const logo=LS.get('logo',null);
  const rows=state.items.filter(i=>i.name||+i.price).map((i,k)=>`<tr><td>${k+1}</td><td>${esc(i.name)}</td><td class="num">${esc(i.qty)}</td><td class="num">${rub(+i.price||0)}</td><td class="num">${rub((+i.qty||0)*(+i.price||0))}</td></tr>`).join('')||'<tr><td colspan="5" style="color:#999;text-align:center">Добавьте позиции слева</td></tr>';
  const sellerLabel=state.type==='kp'?'Исполнитель':state.type==='invoice'?'Поставщик':'Исполнитель';
  const clientLabel=state.type==='invoice'?'Покупатель':'Заказчик';
  $('doc').innerHTML=`
    <div class="head">
      <div><h1>${TYPES[state.type]} № ${esc($('number').value)}</h1><div class="meta">от ${d}</div></div>
      ${logo?`<img src="${logo}" alt="logo">`:''}
    </div>
    <div class="parties">
      <div><b>${sellerLabel}</b>${esc($('sName').value)||'—'}<br>${$('sInn').value?'ИНН '+esc($('sInn').value)+'<br>':''}${esc($('sPhone').value)} ${esc($('sEmail').value)}${$('sBank').value?'<br>'+esc($('sBank').value):''}</div>
      <div><b>${clientLabel}</b>${esc($('cName').value)||'—'}<br>${esc($('cInfo').value)}</div>
    </div>
    <table><thead><tr><th>№</th><th>Наименование</th><th class="num">Кол-во</th><th class="num">Цена, ₽</th><th class="num">Сумма, ₽</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="totals">
      ${c.disc?`<div><span>Сумма:</span><span>${rub(c.sub)}</span></div><div><span>Скидка:</span><span>−${rub(c.disc)}</span></div>`:''}
      ${c.vat==='none'?'<div><span>НДС:</span><span>не облагается</span></div>':`<div><span>${c.vat==='20in'?'В т.ч. НДС 20%':'НДС 20%'}:</span><span>${rub(c.vatSum)}</span></div>`}
      <div class="grand"><span>Итого:</span><span>${rub(c.total)} ₽</span></div>
    </div>
    <div class="words">Всего к оплате: ${amountInWords(Math.round(c.total*100)/100)}</div>
    ${$('note').value?`<div class="note">${esc($('note').value)}</div>`:''}
    ${state.type!=='kp'?`<div class="sign"><div>${sellerLabel}</div><div>${clientLabel}</div></div>`:`<div class="sign"><div>${sellerLabel}</div><div style="border:0"></div></div>`}
    ${isPro()?'':'<div class="watermark">Сделано в DocBlitz — генератор документов</div>'}`;
  sellerFields.forEach(f=>LS.set(f,$(f).value));
  $('planBadge').textContent=isPro()?'Тариф Pro':`Бесплатно: ${usedThisMonth()}/${FREE_LIMIT} документов в этом месяце`;
}

function snapshot(){
  const fields=['number','date','cName','cInfo','vat','discount','note'];
  const o={type:state.type,items:JSON.parse(JSON.stringify(state.items)),total:calc().total,savedAt:Date.now()};
  fields.forEach(f=>o[f]=$(f).value);return o;
}
function load(o){
  state.type=o.type;state.items=JSON.parse(JSON.stringify(o.items));
  ['number','date','cName','cInfo','vat','discount','note'].forEach(f=>$(f).value=o[f]??'');
  setTab();renderItems();render();
}
function renderHistory(){
  const h=LS.get('history',[]);
  $('history').innerHTML=h.length?'':'<div style="color:var(--muted);font-size:14px">Пока пусто</div>';
  h.forEach((o,i)=>{
    const el=document.createElement('div');el.className='history-item';
    el.innerHTML=`<span>${TYPES[o.type]} № ${esc(o.number)} · ${esc(o.cName)||'без клиента'} · <b>${rub(o.total)} ₽</b></span><span><button class="btn ghost">Открыть</button><button class="btn danger">✕</button></span>`;
    const [open,del]=el.querySelectorAll('button');
    open.onclick=()=>load(o);
    del.onclick=()=>{h.splice(i,1);LS.set('history',h);renderHistory()};
    $('history').appendChild(el);
  });
}
function nextNumber(){const n=LS.get('seq',0)+1;return String(n)}
function setTab(){document.querySelectorAll('#typeTabs button').forEach(b=>b.classList.toggle('active',b.dataset.type===state.type))}

function canCreate(){
  if(isPro())return true;
  if(usedThisMonth()>=FREE_LIMIT){
    $('limitBox').style.display='block';
    $('limitBox').innerHTML=`Лимит бесплатного тарифа (${FREE_LIMIT} документов в месяц) исчерпан. <a href="#pro" id="goPro">Подключите Pro за 299 ₽/мес</a>, чтобы снять ограничения.`;
    return false;
  }
  return true;
}
function countUse(){if(!isPro())LS.set(monthKey(),usedThisMonth()+1);LS.set('seq',Math.max(LS.get('seq',0),parseInt($('number').value)||0));render()}

$('pdf').onclick=()=>{if(!canCreate())return;countUse();window.print()};
$('save').onclick=()=>{const h=LS.get('history',[]);h.unshift(snapshot());LS.set('history',h.slice(0,100));renderHistory()};
$('newDoc').onclick=()=>{state.items=[{name:'',qty:1,price:0}];['cName','cInfo','note'].forEach(f=>$(f).value='');$('discount').value=0;$('number').value=nextNumber();$('date').valueAsDate=new Date();renderItems();render()};
$('addItem').onclick=()=>{state.items.push({name:'',qty:1,price:0});renderItems();render()};
document.querySelectorAll('#typeTabs button').forEach(b=>b.onclick=()=>{state.type=b.dataset.type;setTab();render()});
['number','date','cName','cInfo','vat','discount','note',...sellerFields].forEach(f=>$(f).addEventListener('input',render));
$('logo').onchange=e=>{const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=()=>{LS.set('logo',r.result);render()};r.readAsDataURL(f)};
$('removeLogo').onclick=()=>{localStorage.removeItem('logo');$('logo').value='';render()};

function fillDemo(){
  if(!$('sName').value){$('sName').value='ИП Петров Алексей Сергеевич';$('sInn').value='771234567890';$('sPhone').value='+7 900 123-45-67';$('sEmail').value='petrov@mail.ru';$('sBank').value='р/с 40802810000000000001, АО «Тинькофф Банк», БИК 044525974'}
  $('cName').value='ООО «Ромашка»';$('cInfo').value='ИНН 7701234567, info@romashka.ru';
  state.items=[{name:'Разработка лендинга',qty:1,price:25000},{name:'Настройка рекламы в Яндекс.Директ',qty:1,price:12000},{name:'Поддержка сайта, месяц',qty:3,price:3500}];
  $('discount').value=5;$('note').value='Срок выполнения: 10 рабочих дней.\nПредоплата 50%, остаток после сдачи работ.';
  renderItems();render();
}
$('demo').onclick=fillDemo;

function checkPro(){
  if(location.hash==='#pro'&&!isPro()){
    if(confirm('Оплата Pro пока в демо-режиме. Включить Pro для теста?')){LS.set('pro',true);$('limitBox').style.display='none'}
    history.replaceState(null,'',location.pathname);render();
  }
}
window.addEventListener('hashchange',checkPro);

sellerFields.forEach(f=>$(f).value=LS.get(f,''));
$('number').value=nextNumber();$('date').valueAsDate=new Date();
renderItems();render();renderHistory();checkPro();
if(location.search.includes('demo'))fillDemo();
