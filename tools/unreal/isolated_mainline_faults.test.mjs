import test from 'node:test';
import assert from 'node:assert/strict';
import { MainlineFaultSequence } from './isolated_mainline_faults.mjs';
const path='/api/rebuild/v1/profiles/11111111-1111-1111-1111-111111111111/mainline/settlements';
const post={method:'POST',path,status:200,replayed:false,requestId:'ue-mainline-battle',bodySha256:'a'.repeat(64),revision:1,battleId:'battle'};
const get={method:'GET',path:path.replace(/\/settlements$/,''),status:200,revision:1};
test('faults are opt-in and never affect preparation reads or a rejected commit',()=>{
  const off=new MainlineFaultSequence();assert.equal(off.inspect(post),null);assert.equal(off.snapshot().passed,true);
  const on=new MainlineFaultSequence(true);assert.equal(on.inspect(get),null);
  assert.equal(on.inspect({...post,status:409}),null);assert.equal(on.snapshot().checks.droppedAfterCommit,false);
});
test('commit loss then identical replay then one read loss requires a final GET without another POST',()=>{
  const sequence=new MainlineFaultSequence(true);
  assert.equal(sequence.inspect(post),'truncate-commit');
  assert.equal(sequence.inspect(get),null);
  assert.equal(sequence.inspect({...post,replayed:true}),null);
  assert.equal(sequence.inspect({...get,path:get.path.replace('11111111','22222222')}),null);
  assert.equal(sequence.inspect(get),'truncate-confirmed-get');
  assert.equal(sequence.snapshot().passed,false);
  assert.equal(sequence.inspect(get),null);
  assert.equal(sequence.snapshot().settlementPosts,2);assert.equal(sequence.snapshot().passed,true);
  assert.equal(sequence.inspect(get),null);
});
test('changed payload, request identity, path or receipt cannot arm the confirmed read fault',()=>{
  for(const changed of [{bodySha256:'b'.repeat(64)},{requestId:'new-command'},{revision:2},{battleId:'different-battle'},
    {path:path.replace('11111111','22222222')},{replayed:false}]) {
    const sequence=new MainlineFaultSequence(true);sequence.inspect(post);sequence.inspect({...post,replayed:true,...changed});
    assert.equal(sequence.inspect(get),null);assert.equal(sequence.snapshot().checks.replaySamePayload,false);assert.equal(sequence.snapshot().passed,false);
  }
});
test('a third POST after confirmed GET failure cannot pass the recovery sequence',()=>{
  const sequence=new MainlineFaultSequence(true);sequence.inspect(post);sequence.inspect({...post,replayed:true});
  assert.equal(sequence.inspect(get),'truncate-confirmed-get');
  sequence.inspect({...post,replayed:true});sequence.inspect(get);
  assert.equal(sequence.snapshot().checks.retriedConfirmedReadWithoutPost,false);assert.equal(sequence.snapshot().passed,false);
});
