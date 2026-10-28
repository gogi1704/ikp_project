import assert from 'node:assert/strict';
import {activityMetricCount,activityStatsHtml,activityCompanyListHtml} from '../static/shared.js';

const groups=[{
  id:'proposal-1',company:'ООО «Альфа»',inn:'1234567890',lpr:'Иванова Ивана',ownerLogin:'manager',ownerName:'Мария Менеджер',
  links:[
    {id:'link-1',created:100,viewed:200,revoked:false},
    {id:'link-2',created:300,viewed:null,revoked:false},
    {id:'link-3',created:400,viewed:null,revoked:true},
  ],
  submissions:[{id:'submission-1',created:500},{id:'submission-2',created:600}],
}];

assert.equal(activityMetricCount(groups,'sent'),3);
assert.equal(activityMetricCount(groups,'viewed'),1);
assert.equal(activityMetricCount(groups,'unviewed'),2);
assert.equal(activityMetricCount(groups,'applications'),2);
const stats=activityStatsHtml(groups);
assert.match(stats,/data-activity-metric="unviewed"/);
assert.match(stats,/>2<\/strong>/);
const companies=activityCompanyListHtml(groups,'unviewed',{showManager:true});
assert.match(companies,/ООО «Альфа»/);
assert.match(companies,/ИНН 1234567890/);
assert.match(companies,/отозвано: 1/);
assert.match(companies,/Мария Менеджер/);
assert.match(activityCompanyListHtml(groups,'viewed'),/1 просмотр/);
assert.match(activityCompanyListHtml([], 'applications'),/Предприятий нет/);
console.log('Activity statistics: passed');
