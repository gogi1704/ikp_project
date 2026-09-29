import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildProposalDocument} from '../static/proposal-document.js';

const catalog={
  addons:[{code:'lmk',name:'Новая ЛМК',price:650}],
  corp:[{code:'manager',name:'Персональный менеджер',defaultPrice:0,spoiler:'Сопровождение компании'}],
  health:[{code:'aiAssist',name:'ИИ-ассистент',defaultPrice:20,spoiler:'Анализ анкеты'}],
  doctors:['терапевт'],
};
const proposal={
  company:'АО «Пример» <script>',inn:'1234567890',lpr:'Иванова Ивана Ивановича',count:10,basePrice:2500,
  mopFirstName:'Анна',mopLastName:'Петрова',mopPhone:'+7 800 000-00-00',mopMessengerPhone:'+7 900 000-00-00',
  addons:{lmk:{price:650}},corp:{manager:{price:0}},health:{aiAssist:{price:20}},
};
const selection={
  count:10,address:'Ростов-на-Дону',dates:'10 октября',comments:'Позвонить заранее',
  addons:{lmk:{on:true,qty:3}},corp:{manager:{on:true,qty:10}},health:{aiAssist:{on:true,qty:10}},
};
const html=buildProposalDocument(proposal,selection,catalog,'https://example.test');
assert.match(html,/Коммерческое предложение/);
assert.match(html,/АО «Пример» &lt;script&gt;/);
assert.doesNotMatch(html,/<script>/);
assert.match(html,/25 000 ₽/);
assert.match(html,/1 950 ₽/);
assert.match(html,/27 150 ₽/);
assert.match(html,/Печатать документ/);
assert.match(html,/Скачать PDF/);
assert.match(html,/id="download-document"/);
assert.match(html,/static\/vendor\/html2canvas\.min\.js/);
assert.match(html,/static\/vendor\/jspdf\.umd\.min\.js/);
assert.match(html,/https:\/\/example\.test\/static\/logo\.png/);
assert.match(html,/https:\/\/example\.test\/static\/proposal-document\.css\?v=13/);
assert.doesNotMatch(html,/<style>/);
assert.match(html,/Оперативное оформление всей необходимой документации/);
assert.match(html,/Предлагаем заключить договор/);
assert.match(html,/Приложение 1\. Состав медицинского осмотра/);
assert.match(html,/Готовы зафиксировать цену и согласовать даты выезда/);
assert.match(html,/Условия данного коммерческого предложения действительны в течение 1 месяца/);
assert.match(html,/Руководитель отдела продаж/);
assert.match(html,/Лариса Захарченко/);
assert.match(html,/static\/signature-larisa\.png/);
assert.match(html,/class="signature-mark"/);
assert.match(html,/Дата формирования ИКП:/);
assert.match(html,/Стоимость для предприятия: 200 ₽/);
assert.equal((html.match(/class="page-break"/g)||[]).length,3);
assert.doesNotMatch(html,/Мы проводим коллективные медосмотры более 10 лет/);
const styles=readFileSync(new URL('../static/proposal-document.css',import.meta.url),'utf8');
assert.match(styles,/\.appendix-grid\{display:block\}/);
const source=readFileSync(new URL('../static/proposal-document.js',import.meta.url),'utf8');
assert.match(source,/pdf\.save\(`КП_\$\{filenamePart\(p\.company\)\}\.pdf`\)/);
assert.match(source,/setTimeout\(\(\)=>attachWhenReady/);
assert.match(source,/for\(const block of sheet\.children\)/);
assert.match(source,/blockHeight<=printableHeight/);
assert.match(source,/pdf\.output\('blob'\)/);
console.log('Printable proposal: passed');
