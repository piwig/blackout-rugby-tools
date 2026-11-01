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

test('source contexts excluded from server statistics stay visible in the incomplete-event queue',()=>{
  // The server accepts only stripped single digits: possession 0–1, field 0–5.
  // Number coercion must not turn a blank, alternate notation or container into a side or zone.
  const invalid=[null,undefined,'',' ','\t\n','00','02','2e0','2.0','0.0','0x0','+0','-0','\ufeff0\ufeff','\x1c0\x1c',true,false,[],[0],{},0.5,-1,6,NaN,Infinity];
  for(const key of ['possession','field'])for(const value of invalid){
    const event={event_key:'incomplete',att:'percu',possession:'0',field:'2',[key]:value};
    const label=`${key}: ${String(value)}`;
    assert.equal(api.eventDraft(event)[key],'',label);
    assert.equal(api.needsReview(event),true,label);
    assert.deepEqual(api.reviewPage([event],'unknown','',0).events,[event],label);
  }
  assert.equal(api.needsReview({att:'percu',possession:'2',field:'2'}),true);
});

test('canonical source contexts retain the full valid ranges including zero and surrounding whitespace',()=>{
  for(const [possession,field,wantSide,wantZone] of [[0,0,'0','0'],['0','0','0','0'],[1,5,'1','5'],[' \t1\n',' 5 ','1','5'],['\u00850\u0085','2','0','2'],['0','3','0','3']]){
    const event={att:'percu',possession,field};
    assert.deepEqual(api.eventDraft(event),{classification:'attack',att:'percu',possession:wantSide,field:wantZone,learn:false});
    assert.equal(api.needsReview(event),false);
    assert.equal(api.reviewPage([event],'unknown','',0).total,0);
  }
});

test('saving a malformed context cannot silently replace it with a numeric side or zone',()=>{
  for(const key of ['possession','field'])for(const value of [' ','02','2e0','2.0','0.0',[],[0],true]){
    assert.throws(()=>api.annotationChange('event',{classification:'attack',att:'percu',possession:'0',field:'2',learn:false,[key]:value}));
  }
});

test('saving context with server-supported whitespace emits finite canonical numbers',()=>{
  assert.deepEqual(api.annotationChange('canonical',{classification:'attack',att:'percu',possession:'\u00850\u0085',field:' 2 ',learn:false}),
    {event_key:'canonical',classification:'attack',att:'percu',possession:0,field:2,learn:false});
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
