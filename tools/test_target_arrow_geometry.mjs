import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { stripTypeScriptTypes } from 'node:module';

const root = new URL('../', import.meta.url);
const source = await readFile(new URL('tools/templates/cocos-target-arrow-geometry.ts', root), 'utf8');
assert.equal(await readFile(new URL('legacy/cocos-poc/assets/TargetArrowGeometry.ts', root), 'utf8'), source);
const { createTargetArrowGeometry: geometry } = await import('data:text/javascript;base64,' +
  Buffer.from(stripTypeScriptTypes(source)).toString('base64'));
const close = (actual, expected, epsilon = 1e-8) => assert.ok(Math.abs(actual - expected) < epsilon, `${actual} != ${expected}`);
const cases = [[0,300], [300,0], [-300,0], [220,370], [-220,370], [90,-200]];
const results = [];
for (const [x,y] of cases) {
  const mesh = geometry({x:0,y:0},{x,y});
  assert.ok(mesh);
  assert.equal(mesh.positions.length,360);
  assert.equal(mesh.uvs.length,240);
  assert.equal(mesh.indices.length,354);
  assert.ok(mesh.positions.every(Number.isFinite));
  assert.ok(mesh.indices.every(i=>Number.isInteger(i)&&i>=0&&i<120));
  const last = mesh.positions.slice(-6);
  close((last[0]+last[3])/2,x); close((last[1]+last[4])/2,y);
  close(Math.hypot(last[0]-last[3],last[1]-last[4]),20);
  close(mesh.uvs.at(-1),59/119);
  const shifted = geometry({x:37,y:-19},{x:x+37,y:y-19});
  mesh.positions.forEach((value,i)=>close(shifted.positions[i],value+([37,-19,0][i%3])));
  results.push({target:[x,y],endWidthAngle:mesh.endWidthAngleDegrees,headRotation:mesh.nativeHeadRotationDegrees});
}
// Analytic straight vertical input has zero curvature slope, including overshoot.
const vertical=geometry({x:0,y:0},{x:0,y:300});
close(vertical.endWidthAngleDegrees,90*Math.PI/Math.fround(3.14));
close(vertical.nativeHeadRotationDegrees,-vertical.endWidthAngleDegrees);
// A vertical arrow's endpoint ribbon spans horizontally, not along its travel direction.
close(vertical.positions.at(-6),10); close(vertical.positions.at(-5),300);
close(vertical.positions.at(-3),-10); close(vertical.positions.at(-2),300);
assert.notEqual(results[3].endWidthAngle,-results[3].headRotation);
for (const end of [{x:0,y:0},{x:.01,y:0},{x:NaN,y:1},{x:Infinity,y:0}]) {
  assert.equal(geometry({x:0,y:0},end),null);
}
const report={source_sha256:createHash('sha256').update(source).digest('hex'),cases:results,
  checks:['template parity','mesh bounds','finite vertices','endpoint midpoint and width',
    'source UV range','translation invariance','vertical analytic angle','head overshoot differs','degenerate guards'],
  scope:'Mathematical port validation only; no original execution comparison or renderer validation'};
await writeFile(new URL('analysis/battle-ui/target-arrow-geometry-checks.json',root),JSON.stringify(report,null,2));
console.log(JSON.stringify({cases:results.length,checks:report.checks.length,passed:true}));
