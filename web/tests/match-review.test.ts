import test from 'node:test';
import assert from 'node:assert/strict';
import * as model from '../src/match-review-model.ts';

const api=model as Record<string,(...args:any[])=>any>;

test('an unvalidated suggestion never becomes a classified attack or an editor default',()=>{
  assert.equal(typeof api.eventDraft,'function');
  const event={event_key:'a',text:'Original',field:0,possession:0,suggestion:{classification:'attack',att:'kick'}};
  assert.deepEqual(api.eventDraft(event),{classification:'unclassified',att:'',possession:'0',field:'0',learn:false});
  assert.equal(api.needsReview(event),true);
  assert.deepEqual(api.useSuggestion(api.eventDraft(event),event.suggestion),{classification:'attack',att:'kick',possession:'0',field:'0',learn:false});
  assert.equal(event.text,'Original');
});

test('manual non-attacks are excluded from unknowns, and incomplete attacks remain reviewable',()=>{
  assert.equal(typeof api.needsReview,'function');
  assert.equal(api.needsReview({annotation:{classification:'non_attack'}}),false);
  assert.equal(api.needsReview({att:'png',field:0,possession:0}),false);
  assert.equal(api.needsReview({att:'png',field:null,possession:0}),true);
  assert.equal(api.needsReview({att:'png',field:0,possession:null}),true);
  assert.equal(api.needsReview({annotation:{classification:'unclassified'},att:'kick',field:0,possession:0}),true);
});

test('saving a correction uses stable event identity, preserves zeros, and never invents missing context',()=>{
  assert.equal(typeof api.annotationChange,'function');
  assert.deepEqual(api.annotationChange('stable-a',{classification:'attack',att:'percu',possession:'0',field:'0',learn:true}),
    {event_key:'stable-a',classification:'attack',att:'percu',possession:0,field:0,learn:true});
  assert.deepEqual(api.annotationChange('stable-b',{classification:'non_attack',att:'kick',possession:'',field:'',learn:false}),
    {event_key:'stable-b',classification:'non_attack',att:null,possession:null,field:null,learn:false});
  assert.throws(()=>api.annotationChange('a',{classification:'attack',att:'',possession:'',field:'',learn:false}));
  assert.throws(()=>api.annotationChange('a',{classification:'attack',att:'kick',possession:'2',field:'9',learn:false}));
});

test('source time zero and exact original text survive a manual correction',()=>{
  assert.equal(typeof api.eventSource,'function');
  const original={text:'  Original\ncommentaire  ',minute:0,field:0,possession:0};
  assert.equal(api.eventText({text:'modified',source_event:original}),'  Original\ncommentaire  ');
  assert.equal(api.eventTime({minute:99,source_event:original},20),0);
  assert.equal(api.eventTime({source_event:{text:'No time'}},20),'—');
  assert.equal(api.eventTime({source_event:{minute:'',text:'Blank time'}},20),'—');
  assert.deepEqual(api.eventSource({source_event:original}),original);
});

test('search and bounded pages support 20,000 events including the last page and an empty filter',()=>{
  assert.equal(typeof api.reviewPage,'function');
  const events=Array.from({length:20000},(_,i)=>({event_key:String(i),text:i===19999?'Événement décisif':'Action',att:i%2?'png':undefined,possession:0,field:0}));
  const last=api.reviewPage(events,'all','',9999);
  assert.equal(last.page,399);assert.equal(last.total,20000);assert.equal(last.events.length,50);assert.equal(last.events[49].event_key,'19999');
  const result=api.reviewPage(events,'all',' evenement   decisif ',0);
  assert.equal(result.total,1);assert.equal(result.events[0].event_key,'19999');
  const empty=api.reviewPage(events,'corrected','',0);
  assert.equal(empty.total,0);assert.equal(empty.page,0);assert.equal(empty.pageCount,1);assert.deepEqual(empty.events,[]);
});
