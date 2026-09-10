import assert from 'node:assert/strict';
import fs from 'node:fs';
import {totals} from '../static/shared.js';
const catalog=JSON.parse(fs.readFileSync(new URL('../static/catalog.json',import.meta.url)));
const p={basePrice:2500,count:10};
const s={count:10,addons:{}};
for(const group of ['corp','health']){
  p[group]=Object.fromEntries(catalog[group].map(o=>[o.code,{on:true,price:o.defaultPrice}]));
  s[group]=Object.fromEntries(catalog[group].map(o=>[o.code,{on:true,qty:2}]));
}
s.health.liverKidney.qty=5;s.addons.sanmin={on:true,qty:4};
assert.equal(totals(p,s,catalog).total,3850000);
s.health.liverKidney.qty=1;
assert.equal(totals(p,s,catalog).health,220000);
console.log('Frontend pricing: passed');
