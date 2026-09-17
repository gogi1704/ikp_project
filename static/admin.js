import {$,esc,date,rub,api,setCsrf,notify,field,messengerFields,wireMessengerFields,readMessengerFields,submissionDetail,linkActions,wireLinkCopyButtons} from './shared.js';
const app=$('#app');
let managers=[], activityGroups=[], activityCatalog=null;
const checks=(u={active:1,can_edit:1,can_publish:1})=>`<div class="access-options">${[['active','Доступ к панели'],['can_edit','Создание и редактирование КП'],['can_publish','Публикация и отзыв ссылок']].map(([k,label])=>`<label class="check"><input type="checkbox" name="${k}" ${u[k]?'checked':''}>${label}</label>`).join('')}</div>`;
const access=form=>Object.fromEntries(['active','can_edit','can_publish'].map(k=>[k,form.elements[k].checked]));
const defaultPhone='+7 (863) 322-67-66';
const defaultMessengerPhone='+7 (989) 506-74-60';
const profileFields=(user=null)=>{const u=user||{phone:defaultPhone,messengerPhone:defaultMessengerPhone};return `<div class="profile-fields"><div class="fields">${field('lastName','Фамилия',u.lastName||'','text','maxlength="150"')}${field('firstName','Имя',u.firstName||'','text','maxlength="150"')}${field('phone','Телефон для звонков',u.phone||'','tel','maxlength="150" placeholder="+7 (863) 322-67-66"')}${field('messengerPhone','Телефон для Telegram / MAX',u.messengerPhone||'','tel','maxlength="150" placeholder="+7 (989) 506-74-60"')}</div><div class="admin-photo"><img class="avatar" src="${u.photo||'/static/logo.png'}" alt="Фото менеджера"><label class="upload">Выбрать фото<input type="file" name="photoFile" accept="image/png,image/jpeg,image/webp"></label><small>PNG, JPEG или WebP · до 250 КБ</small></div><h3>Мессенджеры</h3>${messengerFields(u.messengers||[])}</div>`;};
async function fileData(file,current=''){
  if(!file||!file.size)return current;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>250000)throw new Error('Выберите фото PNG, JPEG или WebP размером до 250 КБ');
  return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Не удалось прочитать фото'));reader.readAsDataURL(file);});
}
async function profile(form,current=''){
  const values=new FormData(form),file=form.querySelector('[name="photoFile"]')?.files[0];
  return {firstName:String(values.get('firstName')||''),lastName:String(values.get('lastName')||''),phone:String(values.get('phone')||''),messengerPhone:String(values.get('messengerPhone')||''),photo:await fileData(file,current),messengers:readMessengerFields(form)};
}
function wirePhoto(form){const file=form.elements.photoFile,preview=form.querySelector('.admin-photo .avatar');file.onchange=()=>{const selected=file.files[0];if(!selected)return;if(!['image/png','image/jpeg','image/webp'].includes(selected.type)||selected.size>250000){file.value='';notify('Выберите фото PNG, JPEG или WebP размером до 250 КБ');return;}const reader=new FileReader();reader.onload=()=>preview.src=reader.result;reader.readAsDataURL(selected);};}
async function action(form,fn){const controls=[...form.querySelectorAll('input,button')];controls.forEach(c=>c.disabled=true);try{await fn();}catch(e){if(e.status===401)login('Сессия завершена. Войдите снова.');else notify(e.message);}finally{controls.forEach(c=>c.disabled=false);}}
function login(message=''){
  app.innerHTML=`<section class="login card"><span class="eyebrow">УПРАВЛЕНИЕ ДОСТУПОМ</span><h1>Вход администратора</h1><form id="login">${field('password','Пароль','','password','required autocomplete="current-password" maxlength="256"')}<p class="error" id="login-error" role="alert">${esc(message)}</p><button class="primary">Войти</button></form></section>`;
  $('#login').onsubmit=async e=>{e.preventDefault();const form=e.target,data={password:form.elements.password.value};await action(form,async()=>{try{await start(await api('/api/login','POST',data));}catch(err){$('#login-error').textContent=err.message;}});};
}
async function start(me){
  setCsrf(me.csrf);
  if(me.role!=='admin'){$('#account').innerHTML=`<span>${esc(me.login)}</span><button class="header-button" id="logout">Выйти</button>`;$('#logout').onclick=async()=>{try{await api('/api/logout','POST');location.reload();}catch(e){notify(e.message);}};app.innerHTML='<section class="empty card"><h1>Доступ ограничен</h1><p>Этот аккаунт не является администратором.</p><a href="/manager">Перейти в панель менеджера</a></section>';return;}
  $('#account').innerHTML=`<button class="header-button activity-header-button" id="global-activity">Статистика <b id="activity-summary"></b></button><span>${esc(me.login)}</span><button class="header-button" id="logout">Выйти</button>`;
  $('#logout').onclick=async()=>{try{await api('/api/logout','POST');location.reload();}catch(e){notify(e.message);}};
  app.innerHTML=`<div class="admin-wrap"><div class="page-title"><div><span class="eyebrow">АДМИНИСТРИРОВАНИЕ</span><h1>Менеджеры и права доступа</h1><p class="muted">Данные профиля автоматически подставляются в каждое новое предложение менеджера.</p></div></div><div class="admin-grid"><section class="card"><h2>Новый менеджер</h2><form id="create-manager">${field('login','Логин','','text','required maxlength="254" autocomplete="off"')}${field('password','Пароль','','password','required minlength="6" maxlength="256" autocomplete="new-password"')}<p class="muted small">От 6 символов. Передайте пароль менеджеру по защищённому каналу.</p><h3>Данные менеджера в КП</h3>${profileFields()}<h3>Права доступа</h3>${checks()}<button class="primary">Создать менеджера</button></form></section><section><div class="admin-toolbar"><label class="field">Найти менеджера<input id="search" type="search" placeholder="Логин или имя"></label><button class="secondary" id="refresh">Обновить</button></div><p class="muted small">Изменение данных, прав или пароля завершает текущие сессии менеджера. Уже опубликованные предложения не изменяются.</p><div id="managers">Загрузка…</div></section></div></div><dialog class="activity-dialog activity-dialog-wide" id="admin-activity-dialog"><section class="card"><div class="dialog-heading"><div><span class="eyebrow">СТАТИСТИКА</span><h2>Ссылки и заявки менеджеров</h2><p class="muted small">Все предложения, персональные ссылки и полученные заявки по всем менеджерам.</p></div><button type="button" class="dialog-close" id="close-admin-activity" aria-label="Закрыть">×</button></div><div class="admin-toolbar"><label class="field">Менеджер<select id="activity-manager"><option value="">Все менеджеры</option></select></label><label class="field">Найти предприятие, ИНН или менеджера<input id="activity-search" type="search" placeholder="Название, ИНН, логин…"></label></div><div id="admin-activity">Загрузка…</div><button class="secondary" id="activity-refresh">Обновить данные</button></section></dialog><dialog class="activity-dialog submission-dialog" id="submission-dialog"><section class="card"><div class="dialog-heading"><div><span class="eyebrow">ДЕТАЛИ ЗАЯВКИ</span><h2 id="submission-title">Заявка</h2><p class="muted small">Выбор клиента на момент отправки заявки.</p></div><button type="button" class="dialog-close" id="close-submission" aria-label="Закрыть">×</button></div><div id="submission-detail"></div></section></dialog>`;
  const create=$('#create-manager');wirePhoto(create);wireMessengerFields(create);
  create.onsubmit=async e=>{e.preventDefault();const form=e.target;try{const values=new FormData(form),body={login:String(values.get('login')||''),password:String(values.get('password')||''),...access(form),profile:await profile(form)};await action(form,async()=>{await api('/api/admin/managers','POST',body);form.reset();form.elements.phone.value=defaultPhone;form.elements.messengerPhone.value=defaultMessengerPhone;form.querySelector('.avatar').src='/static/logo.png';notify('Менеджер создан, данные профиля сохранены');await load();});}catch(error){notify(error.message);}};
  $('#search').oninput=renderList;$('#refresh').onclick=()=>load().catch(e=>notify(e.message));
  const activityDialog=$('#admin-activity-dialog');
  $('#global-activity').onclick=()=>{activityDialog.showModal();loadActivity().catch(e=>notify(e.message));};
  $('#close-admin-activity').onclick=()=>activityDialog.close();
  activityDialog.onclick=e=>{if(e.target===activityDialog)activityDialog.close();};
  const submissionDialog=$('#submission-dialog');
  $('#close-submission').onclick=()=>submissionDialog.close();
  submissionDialog.onclick=e=>{if(e.target===submissionDialog)submissionDialog.close();};
  $('#activity-manager').onchange=renderActivity;$('#activity-search').oninput=renderActivity;
  $('#activity-refresh').onclick=()=>loadActivity().catch(e=>notify(e.message));
  await load();
  await loadActivity().catch(e=>{$('#admin-activity').innerHTML=`<p class="error">${esc(e.message)}</p>`;});
}
async function load(){managers=await api('/api/admin/managers');renderList();populateManagerFilter();}
function populateManagerFilter(){
  const select=$('#activity-manager');if(!select)return;
  const current=select.value;
  select.innerHTML=`<option value="">Все менеджеры</option>${managers.map(u=>`<option value="${u.id}">${esc(u.login)}${u.firstName||u.lastName?' · '+esc([u.firstName,u.lastName].filter(Boolean).join(' ')):''}</option>`).join('')}`;
  select.value=managers.some(u=>u.id===current)?current:'';
}
async function loadActivity(){
  if(!activityCatalog)activityCatalog=await api('/static/catalog.json');
  const overview=await api('/api/admin/activity');
  activityGroups=overview.proposals;
  renderActivity();
}
function renderActivity(){
  const manager=$('#activity-manager').value, query=$('#activity-search').value.toLowerCase().trim();
  const filtered=activityGroups.filter(g=>(!manager||g.owner===manager)&&`${g.company} ${g.inn} ${g.lpr} ${g.ownerLogin} ${g.ownerName}`.toLowerCase().includes(query));
  $('#activity-summary').textContent=`${filtered.reduce((n,g)=>n+g.links.length,0)} ссылок · ${filtered.reduce((n,g)=>n+g.submissions.length,0)} заявок`;
  $('#admin-activity').innerHTML=filtered.map(group=>{
    const links=group.links.map(link=>`<div class="activity activity-row"><div><span class="pill ${link.revoked?'':'green'}">${link.revoked?'Отозвана':link.viewed?'Просмотрена':'Опубликована'}</span><small>Создана ${date(link.created)}${link.viewed?' · просмотрена '+date(link.viewed):' · ещё не просмотрена'}</small></div><div class="link-actions">${linkActions(link)}</div></div>`).join('');
    const submissions=group.submissions.map(item=>{const selected=['corp','health','addons'].reduce((total,g)=>total+activityCatalog[g].filter(o=>item.body[g]?.[o.code]?.on).length,0);return `<button type="button" class="receipt activity-receipt submission-open" data-proposal="${group.id}" data-submission="${item.id}"><span><strong>Заявка от ${date(item.created)}</strong><small>${item.body.count} сотрудников · ${selected} выбранных услуг</small></span><span><b>${rub(item.totals.total)}</b><small>Открыть полностью</small></span></button>`;}).join('');
    return `<section class="activity-proposal"><div class="activity-proposal-head"><div><h3>${esc(group.company||'Предложение без названия')}</h3><p>${group.inn?`ИНН ${esc(group.inn)} · `:''}${group.lpr?`Для ${esc(group.lpr)} · `:''}Менеджер: ${esc(group.ownerLogin)}${group.ownerName?' ('+esc(group.ownerName)+')':''}</p></div><span>${group.links.length} ссылок · ${group.submissions.length} заявок</span></div><div class="activity-columns"><div><h4>Ссылки</h4>${links||'<p class="muted small">Ссылки ещё не создавались</p>'}</div><div><h4>Заявки</h4>${submissions||'<p class="muted small">Заявок пока нет</p>'}</div></div></section>`;
  }).join('')||`<section class="empty activity-empty card">${activityGroups.length?'<h3>Ничего не найдено</h3>':'<h3>Предложений пока нет</h3>'}</section>`;
  wireLinkCopyButtons($('#admin-activity'));
  document.querySelectorAll('#admin-activity [data-submission]').forEach(button=>button.onclick=()=>openAdminSubmission(button.dataset.proposal,button.dataset.submission));
}
function openAdminSubmission(proposalId,submissionId){
  const group=activityGroups.find(item=>item.id===proposalId),submission=group?.submissions.find(item=>item.id===submissionId);
  if(!submission)return notify('Не удалось открыть заявку');
  $('#submission-title').textContent=`Заявка · ${group.company||submission.proposal?.company||'предприятие'}`;
  $('#submission-detail').innerHTML=submissionDetail(submission,activityCatalog);
  $('#submission-dialog').showModal();
}
function renderList(){
  const query=$('#search').value.toLowerCase().trim();
  const filtered=managers.filter(u=>`${u.login} ${u.firstName} ${u.lastName}`.toLowerCase().includes(query));
  $('#managers').innerHTML=filtered.map(u=>`<section class="card manager-access"><div class="page-title"><div class="manager-title"><img class="avatar" src="${u.photo||'/static/logo.png'}" alt=""><div><h2>${esc(u.login)}</h2><small>${esc([u.firstName,u.lastName].filter(Boolean).join(' ')||'Данные не заполнены')}</small></div></div><span class="pill ${u.active?'green':''}">${u.active?'Активен':'Заблокирован'}</span></div><form data-profile="${u.id}"><h3>Данные менеджера в КП</h3>${profileFields(u)}<div class="form-actions"><button class="secondary">Сохранить данные менеджера</button><span class="save-confirmation" role="status"></span></div></form><form data-access="${u.id}"><h3>Права доступа</h3>${checks(u)}<button class="secondary">Сохранить доступы</button></form><details class="password-reset"><summary>Сбросить пароль</summary><form data-password="${u.id}">${field('password','Новый пароль','','password','required minlength="6" maxlength="256" autocomplete="new-password"')}<button class="secondary">Установить пароль</button></form></details><div class="danger-zone"><button type="button" class="danger-link" data-delete-open="${u.id}">Удалить менеджера</button><div class="delete-confirm" data-delete-confirm="${u.id}" hidden><p>Удалить менеджера <b>${esc(u.login)}</b> и все его предложения, ссылки и заявки?</p><div><button type="button" class="danger" data-delete-yes="${u.id}">Да, удалить</button><button type="button" class="secondary compact" data-delete-no="${u.id}">Отмена</button></div></div></div></section>`).join('')||`<section class="card muted">${managers.length?'Ничего не найдено':'Менеджеров пока нет. Создайте первый аккаунт.'}</section>`;
  document.querySelectorAll('[data-profile]').forEach(form=>{const user=managers.find(u=>u.id===form.dataset.profile);wirePhoto(form);wireMessengerFields(form);form.onsubmit=async e=>{e.preventDefault();try{const data=await profile(form,user.photo);await action(form,async()=>{const saved=await api('/api/admin/managers/'+form.dataset.profile+'/profile','PUT',{profile:data});Object.assign(user,saved.profile);form.querySelector('.save-confirmation').textContent='Сохранено';notify('Данные менеджера сохранены');});}catch(error){notify(error.message);}};});
  document.querySelectorAll('[data-access]').forEach(form=>{form.onsubmit=async e=>{e.preventDefault();await action(form,async()=>{await api('/api/admin/managers/'+form.dataset.access,'PUT',access(form));notify('Доступы сохранены. Текущая сессия менеджера завершена');await load();});};});
  document.querySelectorAll('[data-password]').forEach(form=>form.onsubmit=async e=>{e.preventDefault();await action(form,async()=>{await api('/api/admin/managers/'+form.dataset.password+'/password','POST',{password:form.elements.password.value});form.reset();notify('Пароль изменён. Текущие сессии менеджера завершены');});});
  document.querySelectorAll('[data-delete-open]').forEach(button=>button.onclick=()=>{button.hidden=true;document.querySelector(`[data-delete-confirm="${button.dataset.deleteOpen}"]`).hidden=false;});
  document.querySelectorAll('[data-delete-no]').forEach(button=>button.onclick=()=>{const box=button.closest('.delete-confirm');box.hidden=true;box.previousElementSibling.hidden=false;});
  document.querySelectorAll('[data-delete-yes]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{await api('/api/admin/managers/'+button.dataset.deleteYes,'DELETE');notify('Менеджер удалён');await load();}catch(error){button.disabled=false;notify(error.message);}});
}
try{await start(await api('/api/me'));}catch(e){if(e.status===401)login();else app.textContent=e.message;}
