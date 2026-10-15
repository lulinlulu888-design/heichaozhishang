// Exercise the real menu coordinator with engine rendering stubbed out.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
const require = createRequire(import.meta.url);
const ts = require('../.tools/cocos/3.8.8/resources/app.asar.unpacked/node_modules/typescript/lib/typescript.js');
const source = readFileSync(new URL('../legacy/cocos-poc/assets/ToolchainProof.ts', import.meta.url), 'utf8');
assert.equal(source, readFileSync(new URL('./templates/cocos-toolchain-proof.ts', import.meta.url), 'utf8'));
class Controller {
    constructor(transport) { this.transport = transport; this.snapshot = { phase: 'idle', pending: false, canRetry: false }; }
    dispose() { this.disposed = true; }
}
class View { render() {} destroy() { this.destroyed = true; } }
const cc = { _decorator: { ccclass: () => value => value }, Color: class {}, Component: class {} };
const exports = {};
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, experimentalDecorators: true,
} }).outputText, { exports, require: name => name === 'cc' ? cc : name === './TutorialBattleController'
    ? { TutorialBattleController: Controller } : name === './TutorialBattleView' ? { TutorialBattleView: View } : {}, console });
const menu = new exports.ToolchainProof();
menu.charactersRoot = { children: [] }; menu.cardsRoot = { children: [] };
menu.connection = {}; menu.feedback = message => { menu.lastMessage = message; };
menu.updateProfile = () => {}; menu.reload = async () => { menu.reloadCount = (menu.reloadCount || 0) + 1; };
const requests = [];
menu.request = async (method, path, body, endpoint) => requests.push({ method, path, endpoint });
menu.createBattleClient();
const original = menu.tutorialController;
for (const patch of [{ pending: true }, { canRetry: true }, { phase: 'uncertain' }]) {
    original.snapshot = { phase: 'ready', pending: false, canRetry: false, ...patch };
    await menu.switchService(7460);
    assert.equal(menu.tutorialController, original);
    assert.equal(menu.api, 'http://127.0.0.1:7458/api/rebuild/v1');
    assert.equal(menu.reloadCount, undefined);
}
original.snapshot = { phase: 'ready', pending: false, canRetry: false };
menu.profile = { id: 'old-profile' }; menu.catalog = {}; menu.selectedId = 1;
await menu.switchService(7460);
assert.equal(original.disposed, true);
assert.equal(menu.profile, null); assert.equal(menu.catalog, null); assert.equal(menu.selectedId, null);
assert.equal(menu.reloadCount, 1);
// A retained old transport must never send its pending receipt to the new service.
await original.transport('GET', '/old');
await menu.tutorialController.transport('GET', '/new');
assert.equal(requests[0].endpoint, 'http://127.0.0.1:7458/api/rebuild/v1');
assert.equal(requests[1].endpoint, 'http://127.0.0.1:7460/api/rebuild/v1');
const city = menu.tutorialController;
await menu.switchService(7460);
assert.equal(menu.tutorialController, city); assert.equal(menu.reloadCount, 2);
menu.busy = true;
await menu.switchService(7459);
assert.equal(menu.tutorialController, city);
menu.busy = false; menu.tutorialOpen = true;
await menu.switchService(7459);
assert.equal(menu.tutorialController, city);
console.log('PASS selection guards, profile reset, same-service reload and immutable transport endpoint; engine UI stubbed');
