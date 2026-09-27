import {esc,rub,totals} from './shared.js';

const DEFAULT_PHONE='+7 (863) 322-67-66';
const DEFAULT_MESSENGER='+7 (989) 506-74-60';
const EXAM_COMPOSITION=[
  'Осмотр дерматовенеролога','Осмотр нарколога','Осмотр оториноларинголога','Осмотр психиатра',
  'Осмотр стоматолога','Осмотр терапевта','Осмотр акушера-гинеколога','Осмотр хирурга',
  'Клинический анализ мочи','Определение группы здоровья','Определение уровня общего холестерина',
  'Осмотр невролога','Осмотр офтальмолога','Измерение уровня глюкозы в крови',
  'Измерение артериального давления','Индекс массы тела','Исследование крови на ОРСИ',
  'Исследование на гельминтозы','Общий анализ крови','Флюорография лёгких',
  'Электрокардиография в покое','Ультразвуковое исследование органов малого таза',
];

function selectedServices(group,p,s,catalog){
  return catalog[group].filter(item=>s[group]?.[item.code]?.on).map(item=>{
    const state=s[group][item.code];
    const price=group==='addons'?p.addons?.[item.code]?.price??item.price:p[group]?.[item.code]?.price??item.defaultPrice??0;
    const quantity=group==='addons'?state.qty:item.type==='qty'?Math.max(0,state.qty-2):s.count;
    const quantityLabel=group==='addons'?`${state.qty} сотр.`:item.type==='qty'?`${state.qty} шт. (2 бесплатно)`:`${s.count} сотр.`;
    return {...item,price,quantity,quantityLabel,total:Math.round(price*100)*quantity};
  });
}

function serviceTable(title,items){
  if(!items.length)return '';
  return `<section><h2>${esc(title)}</h2><table><thead><tr><th>Услуга</th><th>Количество</th><th>Цена</th><th>Стоимость</th></tr></thead><tbody>${items.map(item=>`<tr><td><strong>${esc(item.name)}</strong>${item.spoiler?`<small>${esc(item.spoiler)}</small>`:''}</td><td>${esc(item.quantityLabel)}</td><td>${Math.round(item.price).toLocaleString('ru-RU')} ₽</td><td><strong>${rub(item.total)}</strong></td></tr>`).join('')}</tbody></table></section>`;
}

function benefitCards(title,items){
  if(!items.length)return '';
  return `<section><h2>${esc(title)}</h2><div class="benefits">${items.map(item=>`<article><h3>${esc(item.name)}</h3><p>${esc(item.spoiler||'Услуга включена в предложение.')}</p></article>`).join('')}</div></section>`;
}

function safeText(value,fallback='Не указано'){return esc(String(value||'').trim()||fallback);}

export function buildProposalDocument(p,s,catalog,assetRoot=''){
  const t=totals(p,s,catalog);
  const addons=selectedServices('addons',p,s,catalog);
  const selectedAddons=addons.filter(item=>item.quantity>0);
  const corporate=selectedServices('corp',p,s,catalog);
  const health=selectedServices('health',p,s,catalog);
  const manager=[p.mopFirstName,p.mopLastName].filter(Boolean).join(' ')||'Персональный менеджер';
  const phone=p.mopPhone||DEFAULT_PHONE;
  const messenger=p.mopMessengerPhone||DEFAULT_MESSENGER;
  const perEmployee=t.total/(s.count||1);
  const preparedDate=new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric'}).format(new Date());
  const aiIsFree=Boolean(s.health?.aiAssist?.on)&&Number(p.health?.aiAssist?.price||0)===0;
  const corporateTitle=t.corp===0?'Корпоративные преимущества (включены бесплатно)':'Корпоративные преимущества';
  const organizationDetails=s.address||s.dates||s.comments?`<div class="organization"><div><small>Адрес проведения</small>${safeText(s.address)}</div><div><small>Предпочтительные даты</small>${safeText(s.dates)}</div><div><small>Комментарий</small>${safeText(s.comments,'Нет комментария')}</div></div>`:'';
  const appendixPrices=catalog.addons.map(item=>{
    const price=p.addons?.[item.code]?.price??item.price;
    return `<li><strong>${esc(item.name)}</strong> — ${Math.round(price).toLocaleString('ru-RU')} руб.</li>`;
  }).join('');

  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Коммерческое предложение · ${esc(p.company)}</title><link rel="stylesheet" href="${esc(assetRoot)}/static/proposal-document.css?v=4"><script src="${esc(assetRoot)}/static/vendor/html2canvas.min.js"></script><script src="${esc(assetRoot)}/static/vendor/jspdf.umd.min.js"></script></head><body>
  <div class="print-toolbar"><button type="button" id="print-document">Печатать документ</button><button type="button" id="download-document" class="secondary">Скачать PDF</button></div>
  <main class="sheet">
    <header class="brand"><img src="${esc(assetRoot)}/static/logo.png" alt=""><b>ЧЕЛОВЕК</b><span>Корпоративная медицина</span></header>
    <section class="hero"><p class="eyebrow">КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ</p><h1>Специальное предложение для ${safeText(p.company,'вашей компании')}</h1><p class="subtitle">Выездной медосмотр ${s.count.toLocaleString('ru-RU')} сотрудников по ${Math.round(p.basePrice).toLocaleString('ru-RU')} ₽${aiIsFree?' с бесплатным ИИ-ассистентом':''}</p><div class="parties"><div class="party"><small>ПОДГОТОВЛЕНО ДЛЯ</small><strong>${safeText(p.company)}</strong><span>${safeText(p.lpr,'Руководитель не указан')}</span>${p.inn?`<span>ИНН ${esc(p.inn)}</span>`:''}</div><div class="party"><small>ПЕРСОНАЛЬНЫЙ МЕНЕДЖЕР</small><strong>${esc(manager)}</strong><span>Группа компаний «Человек»</span><span>${esc(phone)} · Telegram / MAX: ${esc(messenger)}</span></div></div></section>

    <section><h2>О компании</h2><p class="lead">Группа Компаний «Человек» работает на рынке медицинских услуг 13 лет и является лидером Юга России по количеству выездных медосмотров. Мы проводим коллективные медосмотры более 10 лет и гарантируем быстрое, качественное и удобное проведение медицинского осмотра с выездом на ваше предприятие.</p><p><strong>Наши преимущества:</strong></p><ul class="feature-list"><li>Выездная медицинская бригада — осмотр без остановки производственного процесса.</li><li>Оперативное оформление всей необходимой документации.</li></ul><p class="review-link">➚ Ознакомьтесь с отзывами наших клиентов в Telegram: <a href="https://t.me/gkchelovek">t.me/gkchelovek</a></p></section>

    <section><h2>Предложение</h2><p>Предлагаем заключить договор на проведение предварительных и периодических медицинских осмотров ваших сотрудников согласно Приказу Министерства здравоохранения РФ от 28.01.2021 № 29н.</p><p><strong>Количество сотрудников:</strong> ${s.count.toLocaleString('ru-RU')} &nbsp;·&nbsp; <strong>Формат:</strong> выездной медосмотр на территории предприятия.</p></section>

    <section><h2>Стоимость</h2><div class="price-card"><div><small>СПЕЦИАЛЬНАЯ ЦЕНА ДЛЯ ${safeText(String(p.company||'вашей компании').toUpperCase())}</small><strong>${Math.round(p.basePrice).toLocaleString('ru-RU')} ₽ за одного сотрудника</strong></div><b>${rub(t.base)}</b></div><p class="included"><strong>В стоимость включено:</strong> выезд, все осмотры, оформление документов, заключение профпатолога и продление ЛМК.</p><p><strong>Важно:</strong> дополнительные платные услуги не входят в базовую стоимость и рассчитываются отдельно. Подробный состав осмотра и условия по ЛМК — в Приложениях 1 и 2.</p></section>

    ${benefitCards(corporateTitle,corporate)}
    ${benefitCards('Забота о здоровье сотрудников',health)}

    <section><h2>Организация медосмотра</h2><p>Вам не нужно ничего заполнять или организовывать. Мы приезжаем сами и привозим всё необходимое оборудование.</p><p>Единственное, что потребуется с вашей стороны — помещение с доступом к электричеству 220 В. Остальные детали (даты, время, логистику) менеджер согласует с Вами отдельно.</p>${organizationDetails}</section>

    ${serviceTable('Выбранные дополнительные услуги к медицинскому осмотру',selectedAddons)}

    <section><h2>Смета</h2><table class="estimate"><tbody><tr><td>Медицинский осмотр (${s.count.toLocaleString('ru-RU')} чел. × ${Math.round(p.basePrice).toLocaleString('ru-RU')} руб.)</td><td>${rub(t.base)}</td></tr><tr><td>Дополнительные услуги к медосмотру</td><td>${rub(t.addons)}</td></tr><tr><td>Корпоративные преимущества</td><td>${rub(t.corp)}</td></tr><tr><td>Здоровье сотрудников</td><td>${rub(t.health)}</td></tr><tr class="total"><td>Итого по предложению</td><td>${rub(t.total)}</td></tr><tr class="per-person"><td>Стоимость на одного сотрудника</td><td>${rub(perEmployee)}</td></tr></tbody></table></section>

    <section class="contacts"><h2>Контакты и реквизиты</h2><div class="contacts-grid"><div><p><strong>ГК «Человек» · Корпоративная медицина</strong></p><p>344065, г. Ростов-на-Дону, ул. 50-летия Ростсельмаша, зд. 6в, этаж 3, помещ. 9А</p><p>Тел.: +7 (863) 322-67-66, +7 (863) 322-69-79 доб. 932</p><p>Email: sales-q-team@chelovekmed.ru · Telegram: t.me/gkchelovek</p><p>ИНН 6166083531, КПП 616601001 · Лицензия № Л041-01050-61/00339366 от 03.10.2018 г.</p></div><div><p><strong>Персональный менеджер: ${esc(manager)}</strong></p><p>${esc(phone)}</p><p>Telegram / MAX: ${esc(messenger)}</p></div></div><p class="document-date">Документ сформирован ${esc(preparedDate)} на основании текущего выбора в индивидуальном предложении.</p></section>

    <section class="cta"><h3>Готовы зафиксировать цену и согласовать даты выезда?</h3><p><strong>Персональный менеджер: ${esc(manager)}.</strong> Позвоните или напишите прямо сейчас — менеджер ответит на все вопросы и подготовит договор.</p></section><p class="signature">С уважением и наилучшими пожеланиями,<br>Группа компаний «Человек»</p>

    <div class="page-break"></div>
    <section><h2>Приложение 1. Состав медицинского осмотра (в зависимости от производственных факторов)</h2><p>В базовый состав входят осмотры врачей и исследования:</p><ul class="doctor-list">${EXAM_COMPOSITION.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></section>

    <section><h2>Приложение 2. Дополнительные платные услуги (не входят в базовую стоимость)</h2><ul class="appendix-list">${appendixPrices}</ul></section>

    <section><h2>Важно! Условия оформления санминимума</h2><ul class="note-list"><li>Необходимо наличие зарегистрированной ЛМК в «Едином реестре выданных ЛМК». Перед заказом услуги необходимо самостоятельно проверить её регистрацию: <a href="https://lmk.cgon.ru">lmk.cgon.ru</a>.</li><li>На стр. 28 в ЛМК — не более 3 голограмм о прохождении санминимума, так как программа ГИГтест даёт пройти под одну ЛМК только 4 раза санминимум. При наличии 4 и более печатей с голограммами требуется замена ЛМК.</li><li>Фамилия в ЛМК и сотрудника, заявленного на проведение санминимума, должны быть идентичны. При смене фамилии требуется замена ЛМК перед прохождением санминимума.</li><li>Обязательно наличие БАК-исследований, проводимых по организации, заявленной на проведение санминимума: тиф и кишечная инфекция — для всех сотрудников; стафилококк — для работников пищевой отрасли и медицинских работников. Также требуется актуальная фотография 3 × 4 на матовой бумаге с указанием ФИО и даты.</li></ul></section>

    <section><h2>Вакцинация (для справки)</h2><ul class="note-list"><li><strong>Столбняк</strong> — ревакцинация проводится 1 раз в 10 лет (допускаются документы по АКДС, АДС-М или АС-анатоксину).</li><li><strong>Гепатит В</strong> — обязательно наличие завершённого курса вакцинации.</li><li><strong>Корь</strong> — подтверждение обязательно для всех.</li><li><strong>Краснуха</strong> — подтверждение требуется только для женщин.</li></ul></section>
  </main></body></html>`;
}

function filenamePart(value){
  return String(value||'предприятие').trim().replace(/[<>:"/\\|?*\u0000-\u001f]/g,' ').replace(/\s+/g,' ').slice(0,80)||'предприятие';
}

async function waitForPdfLibraries(popup){
  for(let attempt=0;attempt<100;attempt+=1){
    if(popup.html2canvas&&popup.jspdf?.jsPDF)return;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  throw new Error('Модуль PDF не загрузился. Обновите страницу и повторите попытку.');
}

async function downloadProposalPdf(popup,p){
  const button=popup.document.querySelector('#download-document');
  const originalLabel=button?.textContent;
  if(button){button.disabled=true;button.textContent='Создаём PDF…';}
  try{
    await waitForPdfLibraries(popup);
    await popup.document.fonts?.ready;
    const sheet=popup.document.querySelector('.sheet');
    const {jsPDF}=popup.jspdf;
    const pdf=new jsPDF({orientation:'portrait',unit:'mm',format:'a4',compress:true});
    const margin=10;
    const gap=6;
    const pageWidth=pdf.internal.pageSize.getWidth();
    const pageHeight=pdf.internal.pageSize.getHeight();
    const imageWidth=pageWidth-margin*2;
    const printableHeight=pageHeight-margin*2;
    let y=margin;
    const nextPage=()=>{pdf.addPage();y=margin;};
    for(const block of sheet.children){
      if(block.classList.contains('page-break')){
        if(y>margin)nextPage();
        continue;
      }
      const canvas=await popup.html2canvas(block,{backgroundColor:'#ffffff',scale:1.5,useCORS:true,logging:false});
      if(!canvas.width||!canvas.height)continue;
      const blockHeight=canvas.height*imageWidth/canvas.width;
      if(blockHeight<=printableHeight){
        if(y>margin&&y+blockHeight>pageHeight-margin)nextPage();
        pdf.addImage(canvas.toDataURL('image/jpeg',0.94),'JPEG',margin,y,imageWidth,blockHeight,undefined,'FAST');
        y+=blockHeight+gap;
        continue;
      }
      if(y>margin)nextPage();
      const pixelsPerMm=canvas.width/imageWidth;
      let sourceY=0;
      while(sourceY<canvas.height){
        const availableMm=pageHeight-margin-y;
        const sourceHeight=Math.min(canvas.height-sourceY,Math.max(1,Math.floor(availableMm*pixelsPerMm)));
        const slice=popup.document.createElement('canvas');
        slice.width=canvas.width;
        slice.height=sourceHeight;
        slice.getContext('2d').drawImage(canvas,0,sourceY,canvas.width,sourceHeight,0,0,canvas.width,sourceHeight);
        const sliceHeight=sourceHeight/pixelsPerMm;
        pdf.addImage(slice.toDataURL('image/jpeg',0.94),'JPEG',margin,y,imageWidth,sliceHeight,undefined,'FAST');
        sourceY+=sourceHeight;
        y+=sliceHeight;
        if(sourceY<canvas.height)nextPage();
      }
      y+=gap;
    }
    pdf.save(`КП_${filenamePart(p.company)}.pdf`);
  }finally{
    if(button){button.disabled=false;button.textContent=originalLabel;}
  }
}

export function openProposalDocument(p,s,catalog){
  const popup=window.open('about:blank','_blank');
  if(!popup)return false;
  popup.opener=null;
  popup.document.open();
  popup.document.write(buildProposalDocument(p,s,catalog,location.origin));
  popup.document.close();
  const attachControls=()=>{
    const printButton=popup.document.querySelector('#print-document');
    const downloadButton=popup.document.querySelector('#download-document');
    if(!printButton||!downloadButton)return false;
    printButton.onclick=()=>popup.print();
    downloadButton.onclick=()=>downloadProposalPdf(popup,p).catch(error=>{
      downloadButton.disabled=false;
      downloadButton.textContent='Скачать PDF';
      window.alert(error.message||'Не удалось сформировать PDF');
    });
    return true;
  };
  const attachWhenReady=(attempt=0)=>{
    if(attachControls()||attempt>=100)return;
    setTimeout(()=>attachWhenReady(attempt+1),50);
  };
  attachWhenReady();
  return true;
}
