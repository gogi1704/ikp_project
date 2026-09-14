export const $ = (s) => document.querySelector(s);
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const rub = v => new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',minimumFractionDigits:0,maximumFractionDigits:0}).format(Math.round(v/100));
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
    t[group]+=Math.round((group==='addons'?p.addons?.[o.code]?.price??o.price:p[group][o.code].price)*100)*qty;
  }
  t.total=t.base+t.corp+t.health+t.addons;return t;
}
export function sumHtml(t,n){ return `<div class="sum-row"><span>Медицинский осмотр</span><b>${rub(t.base)}</b></div><div class="sum-row"><span>Дополнительные услуги к медосмотру</span><b>${rub(t.addons)}</b></div><div class="sum-row"><span>Корпоративные преимущества</span><b>${rub(t.corp)}</b></div><div class="sum-row"><span>Здоровье сотрудников</span><b>${rub(t.health)}</b></div><div class="grand"><span>Итого по предложению</span><strong>${rub(t.total)}</strong><small>${rub(t.total/n)} / сотрудника</small></div>`; }
export function optionDetails(o,includeLink=false){return `${o.spoiler?`<p class="option-description">${esc(o.spoiler)}</p>`:''}${includeLink&&o.link?`<a class="service-download" href="${esc(o.link.href)}" download="${esc(o.link.download||'')}"><span aria-hidden="true">↓</span>${esc(o.link.text)}</a>`:''}${o.consiliumTrial?'<small class="consilium-trial-note">После отправки заявки вы получите персональную ссылку на пятидневный тестовый доступ к сервису «Консилиум».</small>':''}`;}
const messengerTypes=[['telegram','Telegram'],['whatsapp','WhatsApp'],['max','MAX'],['other','Другая ссылка']];
function messengerRow(item={type:'telegram',value:''}){return `<div class="messenger-edit-row"><select aria-label="Мессенджер">${messengerTypes.map(([value,label])=>`<option value="${value}" ${item.type===value?'selected':''}>${label}</option>`).join('')}</select><input type="text" value="${esc(item.value||'')}" maxlength="300" placeholder="@имя, номер или ссылка" aria-label="Аккаунт или ссылка"><button type="button" class="messenger-remove" aria-label="Удалить мессенджер">×</button></div>`;}
export function messengerFields(items=[]){return `<div class="messenger-editor"><div class="messenger-list" data-messenger-list>${items.map(messengerRow).join('')}</div><button type="button" class="messenger-add">+ Добавить мессенджер</button><p class="muted small messenger-help">Telegram: @имя или t.me · WhatsApp: номер или wa.me · MAX: ссылка max.ru</p></div>`;}
export function wireMessengerFields(root,onChange=()=>{}){
  const editor=root.querySelector('.messenger-editor');if(!editor)return;
  editor.addEventListener('click',event=>{
    if(event.target.closest('.messenger-add')){if(editor.querySelectorAll('.messenger-edit-row').length>=8){notify('Можно добавить не более 8 аккаунтов');return;}editor.querySelector('[data-messenger-list]').insertAdjacentHTML('beforeend',messengerRow());onChange();}
    if(event.target.closest('.messenger-remove')){event.target.closest('.messenger-edit-row').remove();onChange();}
  });
  editor.addEventListener('input',onChange);
  editor.addEventListener('change',onChange);
}
export function readMessengerFields(root){return [...root.querySelectorAll('.messenger-edit-row')].map(row=>({type:row.querySelector('select').value,value:row.querySelector('input').value.trim()})).filter(item=>item.value);}
