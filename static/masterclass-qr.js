import {esc} from './shared.js';

const masterclasses=[1,2,3,4,5].map(number=>({code:`masterclass_${number}`,name:`Мастер-класс ${number}`}));

function ensureDialog(popup,api,notify){
  const targetDocument=popup.document;
  const query=selector=>targetDocument.querySelector(selector);
  if(query('#masterclass-dialog'))return query('#masterclass-dialog');
  const dialog=targetDocument.createElement('dialog');
  dialog.id='masterclass-dialog';
  dialog.className='activity-dialog masterclass-dialog';
  dialog.innerHTML=`<section class="card"><div class="dialog-heading"><div><span class="eyebrow">МАСТЕР-КЛАССЫ</span><h2>QR-код для предприятия</h2><p class="muted small">QR ведёт на отдельную страницу «Консилиума». Переходы и новые пользователи сохраняются по предприятию и мастер-классу.</p></div><button type="button" class="dialog-close" id="close-masterclass" aria-label="Закрыть">×</button></div><form id="masterclass-form"><div class="fields"><label class="field">ИНН<input name="inn" inputmode="numeric" maxlength="12" required placeholder="10 или 12 цифр"></label><label class="field">Название предприятия<input name="company" maxlength="300" required placeholder="ООО «Предприятие»"></label></div><label class="field">Мастер-класс<select name="masterclassCode">${masterclasses.map(item=>`<option value="${item.code}">${item.name}</option>`).join('')}</select></label><p class="error" id="masterclass-error" role="alert"></p><button class="primary" id="generate-masterclass-qr">Создать QR-код</button></form><div id="masterclass-result"></div></section>`;
  targetDocument.body.append(dialog);
  query('#close-masterclass').onclick=()=>dialog.close();
  dialog.onclick=event=>{if(event.target===dialog)dialog.close();};
  query('#masterclass-form').onsubmit=async event=>{
    event.preventDefault();
    const button=query('#generate-masterclass-qr');
    const error=query('#masterclass-error');
    button.disabled=true;error.textContent='';
    try{
      const form=Object.fromEntries(new popup.FormData(event.target));
      const result=await api('/api/masterclasses/qr','POST',form);
      query('#masterclass-result').innerHTML=`<div class="masterclass-qr-result"><img src="${result.qrDataUrl}" alt="QR-код: ${esc(result.masterclassName)} для ${esc(result.company)}"><div><span class="eyebrow">QR-КОД ГОТОВ</span><h3>${esc(result.masterclassName)}</h3><p>${esc(result.company)} · ИНН ${esc(result.inn)}</p><label class="field">Ссылка<input id="masterclass-url" readonly value="${esc(result.url)}"></label><div class="masterclass-result-actions"><button type="button" class="secondary" id="copy-masterclass-url">Скопировать ссылку</button><a class="secondary masterclass-download" download="QR_${esc(result.inn)}_${esc(result.masterclassCode)}.png" href="${result.qrDataUrl}">Скачать QR</a></div></div></div>`;
      query('#copy-masterclass-url').onclick=async()=>{try{await popup.navigator.clipboard.writeText(result.url);notify('Ссылка скопирована');}catch{query('#masterclass-url').select();notify('Скопируйте выделенную ссылку');}};
      notify('QR-код создан');
    }catch(problem){error.textContent=problem.message;}finally{button.disabled=false;}
  };
  return dialog;
}

export function openMasterclassQr(popup,proposal,api,notify){
  const dialog=ensureDialog(popup,api,notify);
  const form=popup.document.querySelector('#masterclass-form');
  form.elements.inn.value=proposal.inn||'';
  form.elements.company.value=proposal.company||'';
  popup.document.querySelector('#masterclass-error').textContent='';
  popup.document.querySelector('#masterclass-result').innerHTML='';
  dialog.showModal();
}
