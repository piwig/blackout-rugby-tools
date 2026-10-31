import test from 'node:test';
import assert from 'node:assert/strict';
import {navigationItems,navigationGroups,visibleNavigationGroups,isClubOnly,readNavigationExpansion,revealNavigationGroup,saveNavigationExpansion} from '../src/navigation.ts';

test('all fifteen destinations are unique and assigned exactly once',()=>{
  const expected=['home','optimization','season','progression','academy','squad','matches','training','stadium','market','vacation','profile','settings','contact','guide'].sort();
  assert.deepEqual(navigationItems.map(item=>item.id).sort(),expected);
  assert.deepEqual(['home',...navigationGroups.flatMap(group=>group.items)].sort(),expected);
});

test('national selections retain every shared route and no club-only or empty group',()=>{
  const groups=visibleNavigationGroups(true),ids=['home',...groups.flatMap(group=>group.items)];
  assert.ok(groups.every(group=>group.items.length>0));
  assert.equal(groups.some(group=>group.id==='club'),false);
  assert.deepEqual(groups.find(group=>group.id==='development')?.items,['progression']);
  assert.deepEqual(ids.sort(),navigationItems.filter(item=>!isClubOnly(item.id)).map(item=>item.id).sort());
  assert.equal(visibleNavigationGroups(false).flatMap(group=>group.items).length,14);
});

test('a saved collapsed group reopens for direct navigation without resetting other choices',()=>{
  const storage={getItem:()=>JSON.stringify({match:false,development:false,club:false,account:false}),setItem(){}};
  const expanded=readNavigationExpansion(storage,'manager-one','profile');
  assert.deepEqual(expanded,{match:false,development:false,club:false,account:true});
  assert.deepEqual(revealNavigationGroup(expanded,'academy'),{match:false,development:true,club:false,account:true});
  assert.equal(revealNavigationGroup(expanded,'home'),expanded);
});

test('malformed, missing, partial and denied preference storage never blocks access',()=>{
  for(const value of ['{bad','null','[]','false','"private"']){
    assert.deepEqual(readNavigationExpansion({getItem:()=>value,setItem(){}},'manager','home'),{match:true,development:true,club:true,account:false});
  }
  assert.deepEqual(readNavigationExpansion({getItem:()=>'{"match":false,"account":"yes","club":null}',setItem(){}},'manager','home'),{match:false,development:true,club:true,account:false});
  const denied={getItem():string|null{throw Error('denied')},setItem(){throw Error('denied')}};
  assert.equal(readNavigationExpansion(denied,'manager','settings').account,true);
  assert.doesNotThrow(()=>saveNavigationExpansion(denied,'manager',{match:true,development:true,club:true,account:false}));
  assert.equal(readNavigationExpansion(undefined,'manager','squad').match,true);
});

test('preferences use the requested manager key and persist disclosure booleans only',()=>{
  const entries=new Map<string,string>(),storage={getItem:(key:string)=>entries.get(key)??null,setItem:(key:string,value:string)=>{entries.set(key,value)}};
  saveNavigationExpansion(storage,'manager-one',{match:false,development:false,club:false,account:true});
  assert.deepEqual(JSON.parse(entries.get('manager-one')!),{match:false,development:false,club:false,account:true});
  assert.equal(readNavigationExpansion(storage,'manager-two','home').match,true);
});
