export const $ = (s) => document.querySelector(s);
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const rub = v => new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(v/100);
export const date = v => new Date(v*1000).toLocaleDateString('ru-RU');
let csrf = '';
export function setCsrf(v){ csrf = v; }
export async function api(path, method='GET', data){
  const r = await fetch(path,{method,credentials:'same-origin',headers:method==='GET'?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:method==='GET'?undefined:JSON.stringify(data??{})});
  const body = await r.json();
  if(!r.ok){ const e=new Error(body.error||'Не удалось выполнить запрос'); e.status=r.status; throw e; }
  return body;
}
export function notify(message){ $('#notice').textContent=message; $('#notice').classList.add('visible'); clearTimeout(notify.timer); notify.timer=setTimeout(()=>$('#notice').classList.remove('visible'),6000); }
export function field(name,label,value,type='text',extra=''){return `<label class="field">${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;}
export function totals(p,s,catalog){
  const t={base:Math.round(p.basePrice*100)*s.count,corp:0,health:0,addons:0};
  for(const group of ['corp','health','addons']) for(const o of catalog[group]){
    const st=s[group]?.[o.code]; if(!st?.on)continue;
    const qty=group==='addons'?st.qty:o.type==='qty'?Math.max(0,st.qty-2):s.count;
    t[group]+=Math.round((group==='addons'?o.price:p[group][o.code].price)*100)*qty;
  }
  t.total=t.base+t.corp+t.health+t.addons;return t;
}
export function sumHtml(t,n){ return `<div class="sum-row"><span>Медицинский осмотр</span><b>${rub(t.base)}</b></div><div class="sum-row"><span>Дополнительные исследования</span><b>${rub(t.addons)}</b></div><div class="sum-row"><span>Корпоративные преимущества</span><b>${rub(t.corp)}</b></div><div class="sum-row"><span>Здоровье сотрудников</span><b>${rub(t.health)}</b></div><div class="grand"><span>Итого по предложению</span><strong>${rub(t.total)}</strong><small>${rub(t.total/n)} / сотрудника</small></div>`; }
export function optionDetails(o){return o.spoiler?`<p class="option-description">${esc(o.spoiler)}</p>`:'';}
