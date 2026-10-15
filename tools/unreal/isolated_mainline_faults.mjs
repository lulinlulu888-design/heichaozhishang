// Test-only response fault sequence. Called after the real backend transaction;
// it never edits payloads, receipts, campaign state or production behavior.
const SETTLEMENT=/^\/api\/rebuild\/v1\/profiles\/[0-9a-f-]{36}\/mainline\/settlements$/;
export class MainlineFaultSequence {
  constructor(enabled=false) {
    this.enabled=enabled;this.posts=0;this.first=null;this.replayed=false;
    this.checks={droppedAfterCommit:false,replaySamePayload:false,droppedConfirmedRead:false,retriedConfirmedReadWithoutPost:false};
  }
  inspect(event) {
    if(!this.enabled)return null;
    if(event.method==='POST'&&SETTLEMENT.test(event.path)) {
      this.posts++;
      if(this.posts===1&&event.status===200&&event.replayed===false) {
        this.first={...event};this.checks.droppedAfterCommit=true;
        return 'truncate-commit';
      }
      if(this.posts===2&&this.first&&event.status===200&&event.replayed===true&&
        event.path===this.first.path&&event.requestId===this.first.requestId&&event.bodySha256===this.first.bodySha256&&
        event.revision===this.first.revision&&event.battleId===this.first.battleId) {
        this.replayed=true;this.checks.replaySamePayload=true;
      }
    }
    if(event.method==='GET'&&this.replayed&&event.path===this.first.path.replace(/\/settlements$/,'')&&
      event.status===200&&event.revision===this.first.revision) {
      if(!this.checks.droppedConfirmedRead) {
        this.checks.droppedConfirmedRead=true;
        return 'truncate-confirmed-get';
      }
      this.checks.retriedConfirmedReadWithoutPost=this.posts===2;
    }
    return null;
  }
  snapshot() {
    return {enabled:this.enabled,settlementPosts:this.posts,checks:{...this.checks},
      passed:!this.enabled||(this.posts===2&&Object.values(this.checks).every(Boolean))};
  }
}
