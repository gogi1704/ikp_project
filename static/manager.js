import {$,esc,rub,date,api,setCsrf,notify,field,totals,sumHtml,optionDetails,messengerFields,wireMessengerFields,readMessengerFields} from './shared.js';
let rights={can_edit:true,can_publish:true};
let catalog, rows=[], current=null, managerProfile={}, dirty=false, busy=false, saving=false;
const app=$('#app');
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
function login(){
  app.innerHTML=`<section class="login card"><span class="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО</span><h1>Вход для менеджера</h1><p class="muted">Подготовка предложений и заявки предприятий</p><form id="login">${field('login','Логин','','text','required autocomplete="username"')}${field('password','Пароль','','password','required autocomplete="current-password"')}<p id="login-error" class="error" role="alert"></p><button class="primary">Войти</button></form></section>`;
  $('#login').onsubmit=async e=>{e.preventDefault(); const b=e.target.querySelector('button'); b.disabled=true;try{const me=await api('/api/login','POST',Object.fromEntries(new FormData(e.target)));setCsrf(me.csrf);await start(me);}catch(err){$('#login-error').textContent=err.message;}finally{b.disabled=false;}};
}
async function start(me){
  if(me.role==='admin'){location.replace('/admin');return;}
  rights=me;managerProfile=me.profile||{};
  setCsrf(me.csrf);catalog=await api('/static/catalog.json');rows=await api('/api/proposals');
  $('#account').innerHTML=`<button class="header-button activity-header-button" id="global-activity">Ссылки и заявки <b id="activity-summary"></b></button><button class="header-button" id="profile-open">Мой профиль</button><span>${esc(me.login)}</span> <button class="header-button" id="logout">Выйти</button>`;
  $('#logout').onclick=async()=>{if(dirty&&!confirm('Выйти без сохранения изменений?'))return;await api('/api/logout','POST');dirty=false;location.reload();};
  current=rows[0]||null;render();
}
async function fileData(file,current=''){
  if(!file||!file.size)return current;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>250000)throw new Error('Выберите фото PNG, JPEG или WebP размером до 250 КБ');
  return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Не удалось прочитать фото'));reader.readAsDataURL(file);});
}
function profileDialogHtml(){
  const p=managerProfile;
  return `<dialog class="activity-dialog profile-dialog" id="profile-dialog"><section class="card"><div class="dialog-heading"><div><span class="eyebrow">ЛИЧНЫЕ ДАННЫЕ</span><h2>Мой профиль</h2><p class="muted small">Эти контакты автоматически добавляются в новые предложения.</p></div><button type="button" class="dialog-close" id="profile-close" aria-label="Закрыть">×</button></div><form id="profile-form"><div class="fields">${field('lastName','Фамилия',p.lastName||'','text','maxlength="150"')}${field('firstName','Имя',p.firstName||'','text','maxlength="150"')}${field('phone','Телефон для звонков',p.phone||'','tel','maxlength="150" placeholder="+7 (900) 000-00-00"')}${field('messengerPhone','Дополнительный телефон',p.messengerPhone||'','tel','maxlength="150" placeholder="+7 (900) 000-00-00"')}</div><div class="photo-row"><img class="avatar profile-photo-preview" src="${p.photo||'/static/logo.png'}" alt="Фото менеджера"><label class="upload">Выбрать фото<input type="file" name="photoFile" accept="image/png,image/jpeg,image/webp"></label><small>PNG, JPEG или WebP · до 250 КБ</small></div><h3>Мессенджеры</h3>${messengerFields(p.messengers||[])}<div class="profile-actions"><button class="primary" type="submit">Сохранить профиль</button><button class="secondary" type="submit" name="applyCurrent" value="1" ${current&&rights.can_edit?'':'disabled'}>Сохранить и применить к текущему КП</button></div></form></section></dialog>`;
}
function profileToProposal(body,profile){
  body.mopFirstName=profile.firstName;body.mopLastName=profile.lastName;body.mopPhone=profile.phone;body.mopMessengerPhone=profile.messengerPhone;body.mopPhoto=profile.photo;body.mopMessengers=structuredClone(profile.messengers);
}
function wireProfileDialog(){
  const dialog=$('#profile-dialog'),form=$('#profile-form');
  $('#profile-open').onclick=()=>dialog.showModal();
  $('#profile-close').onclick=()=>dialog.close();
  dialog.onclick=e=>{if(e.target===dialog)dialog.close();};
  wireMessengerFields(form);
  const file=form.elements.photoFile,preview=form.querySelector('.profile-photo-preview');
  file.onchange=()=>{const selected=file.files[0];if(!selected)return;if(!['image/png','image/jpeg','image/webp'].includes(selected.type)||selected.size>250000){file.value='';notify('Выберите фото PNG, JPEG или WebP размером до 250 КБ');return;}const reader=new FileReader();reader.onload=()=>preview.src=reader.result;reader.readAsDataURL(selected);};
  form.onsubmit=async e=>{
    e.preventDefault();const applyCurrent=e.submitter?.name==='applyCurrent',controls=[...form.querySelectorAll('input,select,button')];controls.forEach(control=>control.disabled=true);
    try{
      const values=new FormData(form),profile={firstName:String(values.get('firstName')||''),lastName:String(values.get('lastName')||''),phone:String(values.get('phone')||''),messengerPhone:String(values.get('messengerPhone')||''),photo:await fileData(file.files[0],managerProfile.photo||''),messengers:readMessengerFields(form)};
      managerProfile=(await api('/api/profile','PUT',{profile})).profile;
      if(applyCurrent&&current){
        const body=structuredClone(current.body);profileToProposal(body,managerProfile);
        const saved=await api(`/api/proposals/${current.id}`,'PUT',{body,version:current.version});
        Object.assign(current,saved);const index=rows.findIndex(item=>item.id===saved.id);if(index>=0)rows[index]=structuredClone(saved);dirty=false;render();notify('Профиль сохранён и применён к текущему КП');return;
      }
      controls.forEach(control=>control.disabled=false);dialog.close();notify('Профиль сохранён');
    }catch(error){notify(error.message);controls.forEach(control=>control.disabled=false);}
  };
}
function selection(p){return {count:p.count,corp:p.corp,health:Object.fromEntries(Object.entries(p.health).map(([k,v])=>[k,{...v,qty:2}])),addons:{}};}
function managerOption(g,o,p){
  const st=p[g][o.code], enabled=Boolean(st.on);
  return `<div class="option manager-option"><div class="option-line"><label class="check"><input class="service-toggle" type="checkbox" name="${g}.${o.code}.on" ${enabled?'checked':''}><span>${esc(o.name)}</span></label><label class="price-input"><input type="number" name="${g}.${o.code}.price" value="${st.price}" min="0" max="10000000" step="0.01" required aria-label="Цена: ${esc(o.name)}"><small>₽ / ${o.priceUnit}</small></label></div><div class="option-controls"><label class="option-control fixed-control"><input class="fixed-toggle" type="checkbox" name="${g}.${o.code}.fixed" ${st.fixed?'checked':''} ${enabled?'':'disabled'}><span class="control-icon" aria-hidden="true">🔒</span><span><b>Зафиксировать</b><small>Клиент не сможет отключить</small></span></label><label class="option-control recommend-control ${st.recommended?'selected':''}"><input class="recommend-toggle" type="checkbox" name="${g}.${o.code}.recommended" ${st.recommended?'checked':''} ${enabled?'':'disabled'}><span class="recommend-star" aria-hidden="true">★</span><span><b>Рекомендовать</b><small>Выделить для клиента</small></span></label></div>${o.type==='qty'?'<p class="muted">Первые 2 чек-апа включены бесплатно</p>':''}${optionDetails(o)}</div>`;
}
function syncOptionControls(option){
  const service=option.querySelector('.service-toggle');
  option.querySelectorAll('.fixed-toggle,.recommend-toggle').forEach(input=>input.disabled=!service.checked||!rights.can_edit);
  option.querySelector('.recommend-control')?.classList.toggle('selected',option.querySelector('.recommend-toggle')?.checked);
}
function render(){
  if(current)current=structuredClone(current);
  const p=current?.body;
  app.innerHTML=`<div class="workspace"><aside class="rail"><div class="rail-title">Предложения <span>${rows.length}</span></div><button class="primary" id="new">+ Новое предложение</button><label class="search"><input id="search" placeholder="Найти предприятие" aria-label="Поиск предложений"></label><div id="list">${rows.map(r=>`<button class="proposal ${r.id===current?.id?'selected':''}" data-id="${r.id}"><strong>${esc(r.body.company||'Новое предприятие')}</strong><span>${r.body.count} сотрудников · ${date(r.updated||Date.now()/1000)}</span></button>`).join('')}</div></aside><section class="editor">${p?`<div class="page-title"><div><span class="eyebrow">КОНСТРУКТОР ПРЕДЛОЖЕНИЯ</span><h1>${esc(p.company||'Новое предложение')}</h1></div><span class="pill" id="save-status">Сохранено</span></div><form id="proposal-form"><section class="card"><div class="section-heading"><span class="number">01</span><h2>Предприятие</h2></div><div class="fields"><label class="field inn-field">ИНН<input id="inn-input" name="inn" type="text" value="${esc(p.inn)}" inputmode="numeric" maxlength="12" autocomplete="off" role="combobox" aria-autocomplete="list" aria-controls="inn-suggestions" aria-expanded="false" placeholder="Начните вводить ИНН"><div id="inn-suggestions" class="suggestions" role="listbox"></div><small class="field-hint">Введите минимум 4 цифры</small></label>${field('company','Название предприятия',p.company,'text','required maxlength="300"')}${field('count','Количество сотрудников',p.count,'number','min="1" max="100000" required')}${field('lpr','ФИО руководителя',p.lpr,'text','required maxlength="300"')}</div></section><section class="card"><div class="section-heading"><span class="number">02</span><h2>Персональный менеджер</h2></div><p class="muted small">Данные подставлены из профиля менеджера. Изменения применятся только к этому КП.</p><div class="fields">${field('mopLastName','Фамилия',p.mopLastName,'text','maxlength="300"')}${field('mopFirstName','Имя',p.mopFirstName,'text','maxlength="300"')}${field('mopPhone','Телефон для звонков',p.mopPhone,'tel','maxlength="300"')}${field('mopMessengerPhone','Телефон для Telegram / MAX',p.mopMessengerPhone,'tel','maxlength="300"')}</div><div class="photo-row"><img class="avatar" id="photo-preview" src="${p.mopPhoto||'/static/logo.png'}" alt="Фото менеджера"><label class="upload">Загрузить фото <input id="photo" type="file" accept="image/png,image/jpeg,image/webp"></label><small>PNG, JPEG, WebP · до 250 КБ</small></div><h3>Мессенджеры в этом КП</h3>${messengerFields(p.mopMessengers||[])}</section><section class="card"><div class="section-heading"><span class="number">03</span><h2>Медицинский осмотр</h2></div><p class="muted">Обязательная основа предложения. Стоимость на одного сотрудника.</p>${field('basePrice','Цена, ₽ / сотрудника',p.basePrice,'number','min="0" max="10000000" step="0.01" required')}</section>${['corp','health'].map((g,i)=>`<section class="card"><div class="section-heading"><span class="number">0${i+4}</span><h2>${g==='corp'?'Корпоративные преимущества':'Забота о здоровье сотрудников'}</h2></div>${catalog[g].map(o=>managerOption(g,o,p)).join('')}</section>`).join('')}</form>`:`<div class="empty card"><span class="eyebrow">НАЧНИТЕ РАБОТУ</span><h1>Первое предложение</h1><p>Создайте предложение, настройте услуги и отправьте предприятию персональную ссылку.</p></div>`}</section>${p?`<aside class="summary"><section class="card sticky"><span class="eyebrow">ПРЕДВАРИТЕЛЬНАЯ СМЕТА</span><div id="sum"></div><button class="secondary" id="save">Сохранить изменения</button><button class="primary" id="publish">Сформировать ссылку</button><p class="muted small">Ссылка фиксирует текущие цены и состав услуг.</p><div id="published"></div><div class="proposal-delete"><button type="button" class="danger-link" id="delete-open">Удалить предложение</button><div class="delete-confirm" id="delete-confirm" hidden><p>Удалить это предложение, все его ссылки и полученные заявки?</p><div><button type="button" class="danger" id="delete-yes">Да, удалить</button><button type="button" class="secondary compact" id="delete-no">Отмена</button></div></div></div></section></aside>`:''}</div><dialog class="activity-dialog activity-dialog-wide" id="activity-dialog"><section class="card"><div class="dialog-heading"><div><span class="eyebrow">ВСЕ ПРЕДЛОЖЕНИЯ</span><h2>Ссылки и заявки</h2><p class="muted small">Просмотры ссылок и полученные заявки по всем вашим предложениям.</p></div><button type="button" class="dialog-close" id="close-activity" aria-label="Закрыть">×</button></div><div id="activity">Загрузка…</div><button class="secondary" id="refresh">Обновить данные</button></section></dialog>`;
  app.insertAdjacentHTML('beforeend',profileDialogHtml());
  wireProfileDialog();
  $('#new').onclick=async()=>{if(saving||busy)return;if(dirty&&!confirm('Создать новое предложение без сохранения изменений?'))return;try{current=await api('/api/proposals','POST',{});rows.unshift(current);dirty=false;render();}catch(e){notify(e.message);}};
  $('#search').oninput=e=>document.querySelectorAll('.proposal').forEach(b=>b.hidden=!b.textContent.toLowerCase().includes(e.target.value.toLowerCase()));
  document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{if(saving||busy)return;if(dirty&&!confirm('Перейти без сохранения изменений?'))return;current=rows.find(r=>r.id===b.dataset.id);dirty=false;render();});
  if(!rights.can_edit)$('#new').disabled=true;
  const activityDialog=$('#activity-dialog');
  $('#global-activity').onclick=()=>{allActivity();activityDialog.showModal();};
  $('#close-activity').onclick=()=>activityDialog.close();
  activityDialog.onclick=e=>{if(e.target===activityDialog)activityDialog.close();};
  $('#refresh').onclick=allActivity;
  allActivity();
  if(!p)return;
  $('#proposal-form').oninput=e=>{
    if(e.target.id==='photo')return;
    if(e.target.classList.contains('service-toggle')){
      const option=e.target.closest('.manager-option');
      if(!e.target.checked)option.querySelectorAll('.fixed-toggle,.recommend-toggle').forEach(input=>input.checked=false);
      syncOptionControls(option);
    }
    if(e.target.classList.contains('recommend-toggle')){
      if(e.target.checked)document.querySelectorAll('.recommend-toggle').forEach(input=>{
        if(input!==e.target){input.checked=false;syncOptionControls(input.closest('.manager-option'));}
      });
      syncOptionControls(e.target.closest('.manager-option'));
    }
    readForm();dirty=true;$('#save-status').textContent='Есть изменения';updateSum();
  };
  wireMessengerFields($('#proposal-form'),()=>{readForm();dirty=true;$('#save-status').textContent='Есть изменения';});
  setupInnSuggestions();
  $('#photo').onchange=async e=>{const f=e.target.files[0];if(!f)return;if(!['image/png','image/jpeg','image/webp'].includes(f.type)||f.size>250000){notify('Выберите изображение до 250 КБ');return;}const reader=new FileReader();reader.onload=()=>{p.mopPhoto=reader.result;$('#photo-preview').src=reader.result;dirty=true;$('#save-status').textContent='Есть изменения';};reader.readAsDataURL(f);};
  $('#save').onclick=()=>save().catch(e=>notify(e.message));
  $('#publish').onclick=async()=>{if(busy)return;busy=true;$('#publish').disabled=true;try{if(rights.can_edit)await save();const r=await api(`/api/proposals/${current.id}/publish`,'POST');$('#published').innerHTML=`<label class="field">Персональная ссылка<input id="public-url" readonly value="${esc(r.url)}"></label><button class="secondary" id="copy">Скопировать ссылку</button>`;$('#copy').onclick=async()=>{try{await navigator.clipboard.writeText(r.url);notify('Ссылка скопирована');}catch{$('#public-url').select();notify('Скопируйте выделенную ссылку');}};await allActivity();notify('Предложение опубликовано');}catch(e){notify(e.message);}finally{busy=false;$('#publish').disabled=false;}};
  updateSum();
  $('#delete-open').onclick=()=>{$('#delete-open').hidden=true;$('#delete-confirm').hidden=false;};
  $('#delete-no').onclick=()=>{$('#delete-confirm').hidden=true;$('#delete-open').hidden=false;};
  $('#delete-yes').onclick=async()=>{const button=$('#delete-yes');button.disabled=true;try{await api(`/api/proposals/${current.id}`,'DELETE');rows=rows.filter(item=>item.id!==current.id);current=rows[0]||null;dirty=false;notify('Предложение удалено');render();}catch(error){button.disabled=false;notify(error.message);}};
  if(!rights.can_edit){$('#proposal-form').querySelectorAll('input').forEach(el=>el.disabled=true);$('#save').disabled=true;$('#save-status').textContent='Только просмотр';}
  if(!rights.can_publish)$('#publish').disabled=true;
}
function setupInnSuggestions(){
  const input=$('#inn-input'), list=$('#inn-suggestions'), company=document.querySelector('[name="company"]');
  if(!input||!rights.can_edit)return;
  let timer, request=0, active=-1, items=[];
  const close=()=>{items=[];active=-1;list.innerHTML='';list.classList.remove('open');input.setAttribute('aria-expanded','false');};
  const choose=item=>{input.value=item.inn;company.value=item.name;close();readForm();dirty=true;$('#save-status').textContent='Есть изменения';updateSum();company.focus();};
  const paint=()=>{list.innerHTML=items.map((item,i)=>`<button type="button" class="suggestion ${i===active?'active':''}" role="option" aria-selected="${i===active}" data-index="${i}"><strong>${esc(item.inn)}</strong><span>${esc(item.name)}</span></button>`).join('');list.classList.toggle('open',items.length>0);input.setAttribute('aria-expanded',String(items.length>0));list.querySelectorAll('[data-index]').forEach(button=>button.onmousedown=e=>{e.preventDefault();choose(items[Number(button.dataset.index)]);});};
  input.onkeydown=e=>{if(!items.length)return;if(e.key==='ArrowDown'){e.preventDefault();active=(active+1)%items.length;paint();}else if(e.key==='ArrowUp'){e.preventDefault();active=(active-1+items.length)%items.length;paint();}else if(e.key==='Enter'&&active>=0){e.preventDefault();choose(items[active]);}else if(e.key==='Escape')close();};
  input.addEventListener('input',()=>{clearTimeout(timer);const query=input.value.replace(/\D/g,'');if(input.value!==query){input.value=query;readForm();}if(query.length<4){close();return;}const id=++request;list.innerHTML='<div class="suggestion-state">Ищем организацию…</div>';list.classList.add('open');input.setAttribute('aria-expanded','true');timer=setTimeout(async()=>{try{const result=await api('/api/company-suggestions','POST',{query});if(id!==request)return;items=result.suggestions||[];active=-1;if(items.length)paint();else{list.innerHTML='<div class="suggestion-state">Совпадений не найдено</div>';setTimeout(()=>{if(id===request)close();},1400);}}catch(error){if(id!==request)return;items=[];active=-1;list.innerHTML=`<div class="suggestion-state error-state">${esc(error.message)}</div>`;list.classList.add('open');input.setAttribute('aria-expanded','true');}},280);});
  input.addEventListener('blur',()=>setTimeout(close,160));
}
function readForm(){const form=$('#proposal-form'),p=current.body;for(const input of form.querySelectorAll('input[name]')){const parts=input.name.split('.');const val=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;if(parts.length===3)p[parts[0]][parts[1]][parts[2]]=val;else p[input.name]=val;}p.mopMessengers=readMessengerFields(form);}
function updateSum(){const p=current.body;$('#sum').innerHTML=sumHtml(totals(p,selection(p),catalog),p.count||1);}
async function save(){
  if(saving)throw new Error('Дождитесь завершения сохранения');
  readForm();saving=true;
  const inputs=[...$('#proposal-form').querySelectorAll('input')];inputs.forEach(input=>input.disabled=true);
  try{
    const r=await api(`/api/proposals/${current.id}`,'PUT',{body:current.body,version:current.version});
    Object.assign(current,r);const index=rows.findIndex(item=>item.id===r.id);
    if(index>=0)rows[index]=structuredClone(current);
    dirty=false;$('#save-status').textContent='Сохранено';notify('Изменения сохранены');
  }finally{
    saving=false;
    inputs.forEach(input=>input.disabled=!rights.can_edit);
    document.querySelectorAll('.manager-option').forEach(syncOptionControls);
  }
}
async function allActivity(){
  try{
    const overview=await api('/api/activity');
    const summary=$('#activity-summary');
    if(summary)summary.textContent=`${overview.linkCount} ссылок · ${overview.submissionCount} заявок`;
    const html=overview.proposals.map(group=>{
      const links=group.links.map(link=>`<div class="activity activity-row"><div><span class="pill ${link.revoked?'':'green'}">${link.revoked?'Отозвана':link.viewed?'Просмотрена':'Опубликована'}</span><small>Создана ${date(link.created)}${link.viewed?' · просмотрена '+date(link.viewed):' · ещё не просмотрена'}</small></div>${!link.revoked&&rights.can_publish?`<button class="text-button" data-revoke="${link.id}" data-proposal="${group.id}">Отозвать</button>`:''}</div>`).join('');
      const submissions=group.submissions.map(item=>`<details class="receipt activity-receipt"><summary>Заявка от ${date(item.created)} · ${item.body.count} сотрудников</summary><strong>${rub(item.totals.total)}</strong>${item.body.address?`<p><b>Адрес:</b> ${esc(item.body.address)}</p>`:''}${item.body.dates?`<p><b>Даты:</b> ${esc(item.body.dates)}</p>`:''}${item.body.comments?`<p><b>Комментарий:</b> ${esc(item.body.comments)}</p>`:''}<div class="application-services">${['corp','health','addons'].map(g=>catalog[g].filter(o=>item.body[g][o.code].on).map(o=>`<p>✓ ${esc(o.name)}${g==='addons'||o.type==='qty'?' · '+item.body[g][o.code].qty+' шт.':''}</p>`).join('')).join('')}</div><small>Номер заявки: ${esc(item.id)}</small></details>`).join('');
      return `<section class="activity-proposal"><div class="activity-proposal-head"><div><h3>${esc(group.company||'Предложение без названия')}</h3>${group.lpr?`<p>Для ${esc(group.lpr)}</p>`:''}</div><span>${group.links.length} ссылок · ${group.submissions.length} заявок</span></div><div class="activity-columns"><div><h4>Ссылки</h4>${links||'<p class="muted small">Ссылки ещё не создавались</p>'}</div><div><h4>Заявки</h4>${submissions||'<p class="muted small">Заявок пока нет</p>'}</div></div></section>`;
    }).join('');
    $('#activity').innerHTML=html||'<section class="empty activity-empty"><h3>Предложений пока нет</h3><p class="muted">Создайте предложение и сформируйте первую ссылку.</p></section>';
    document.querySelectorAll('[data-revoke]').forEach(button=>button.onclick=async()=>{try{await api(`/api/proposals/${button.dataset.proposal}/revoke`,'POST',{id:button.dataset.revoke});await allActivity();notify('Ссылка отозвана');}catch(error){notify(error.message);}});
  }catch(error){$('#activity').innerHTML=`<p class="error">${esc(error.message)}</p>`;}
}
try{await start(await api('/api/me'));}catch(e){if(e.status===401)login();else{app.textContent=e.message;}}
