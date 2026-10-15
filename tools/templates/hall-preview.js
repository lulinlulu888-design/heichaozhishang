import * as T from 'three';
import {GLTFLoader} from './vendor/loaders/GLTFLoader.js';
import {OrbitControls} from './vendor/controls/OrbitControls.js';
import {installHallLighting} from './hall-lighting.js';
import {attachShiranuiFlames} from './shiranui-flame-runtime.js';

const query = new URLSearchParams(location.search);
const status = document.querySelector('#status');
const renderer = new T.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x171923);
document.body.prepend(renderer.domElement);
const world = new T.Scene();
const camera = new T.PerspectiveCamera(18, 16/9, .1, 20000);
const controls = new OrbitControls(camera, renderer.domElement);
const mixers = [], updaters = [], clock = new T.Clock();
let cameras = [], paused = false;
function resize() {
  const w = Math.min(innerWidth, innerHeight*16/9);
  renderer.setSize(w, w*9/16);
  camera.aspect = 16/9; camera.updateProjectionMatrix();
}
resize(); addEventListener('resize', resize);
function view(name) {
  const row = cameras.find(r => r.Name === name);
  if (!row) throw Error('场景镜头缺失：'+name);
  new T.Matrix4().fromArray(row.Transform.split(',').map(Number)).decompose(camera.position,camera.quaternion,camera.scale);
  camera.scale.set(1,1,1); camera.rotateY(Math.PI);
  camera.fov = Number(row.Fov); camera.near = Number(row.Near); camera.far = Number(row.Far);
  camera.updateProjectionMatrix();
  controls.target.copy(camera.position).add(camera.getWorldDirection(new T.Vector3()).multiplyScalar(70));
  controls.update();
}
function setupTextures(root) {
  root.traverse(n => {
    if (n.userData.sourceInstance?.FilePathIndex === '25') n.visible = false;
    if (!n.isMesh) return;
    for (const m of Array.isArray(n.material) ? n.material : [n.material]) {
      if (m.userData.sourceMaterialXML?.includes('CullMode="2"')) m.side = T.FrontSide;
      if (m.map) {m.map.anisotropy = renderer.capabilities.getMaxAnisotropy(); m.map.needsUpdate = true;}
    }
  });
}
function playIdle(asset, label) {
  const idle = asset.animations.find(a => a.name === 'home_stand_idle_1');
  if (!idle) throw Error('原'+label+'待机缺失');
  const mixer = new T.AnimationMixer(asset.scene);
  mixer.clipAction(idle).play(); mixers.push(mixer); mixer.update(0);
}
function toggle(id, label, initial, apply) {
  const button = document.querySelector(id);
  let value = initial;
  function set() {apply(value); button.textContent = label+'：'+(value?'开':'关'); button.setAttribute('aria-pressed',String(value));}
  set(); button.disabled = false; button.onclick = () => {value = !value; set();};
}

try {
  const loader = new GLTFLoader();
  const [hall, actor, weapon] = await Promise.all([
    loader.loadAsync('./hall.glb'), loader.loadAsync('./shiranui.glb'), loader.loadAsync('./shiranui-weapon.glb'),
  ]);
  setupTextures(hall.scene); setupTextures(actor.scene); setupTextures(weapon.scene);
  world.add(hall.scene);
  const marker = hall.scene.children.find(n => n.userData.sourceInstance?.Name === 'player_position');
  if (!marker) throw Error('原站位标记缺失');
  const placement = new T.Group(); placement.name = 'ShiranuiHallPreview';
  placement.position.copy(marker.position); placement.quaternion.copy(marker.quaternion); placement.scale.setScalar(.86);
  placement.add(actor.scene, weapon.scene); world.add(placement);
  playIdle(actor,'角色'); playIdle(weapon,'扇子');
  world.updateMatrixWorld(true);
  // Inspection framing excludes attached FX: an effect must not move the camera.
  const center = new T.Box3().setFromObject(placement).getCenter(new T.Vector3());
  cameras = hall.parser.json.extras.sourceCameras;
  document.querySelector('#character').onclick = () => {
    view('camera_1'); const forward = camera.getWorldDirection(new T.Vector3());
    camera.position.copy(center).addScaledVector(forward,-60); camera.fov = 18; camera.updateProjectionMatrix();
    controls.target.copy(center); controls.update();
  };
  document.querySelector('#home').onclick = () => view('camera_1');
  document.querySelector('#up').onclick = () => view('camera_upstairs');
  document.querySelector('#down').onclick = () => view('camera_negative');
  view('camera_1');
  if (query.has('close')) document.querySelector('#character').click();
  toggle('#pause','暂停动作',false,value => {paused = value;});

  const results = await Promise.allSettled([
    installHallLighting(hall.scene, {baseUrl:'./lighting/'}).then(lighting => {
      toggle('#lighting','原场景光照',query.get('lighting') !== '0',value => lighting.setEnabled(value));
      document.querySelector('#lighting').title = lighting.report.installed_instances+' 个场景实例；角色受光尚未恢复';
      console.info('Hall baked lighting',lighting.report.installed_instances);
    }),
    attachShiranuiFlames({weaponRoot:weapon.scene,baseUrl:'./flame/'}).then(fx => {
      updaters.push(dt => fx.update(dt));
      toggle('#flames','原扇子火焰',query.get('fx') !== '0',value => fx.setEnabled(value));
      document.querySelector('#flames').title = fx.report.sockets+' 挂点 / '+fx.report.meshes+' 模型层；原资源适配';
      console.info('Hall flame attachments',JSON.stringify(fx.report));
    }),
    (query.has('sourceUI') || query.has('localProfile'))
      ? import('./hall-ui-preview.js').then(m => m.mountHallUI({localState:query.has('localProfile'),apiPort:Number(query.get('apiPort') || 7460)}))
      : Promise.resolve(),
  ]);
  const failures = results.filter(r => r.status === 'rejected');
  for (const failure of failures) console.error(failure.reason);
  status.textContent = failures.length
    ? '部分效果未载入：'+failures.map(r => r.reason.message).join('；')
    : query.has('localProfile') ? '主角家 · 本地档案' : query.has('sourceUI') ? '原布局核对 · 含原稿占位文字' : '主角家 · 不知火';
} catch (error) {
  status.textContent = '载入失败：'+error.message; console.error(error);
}
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(),.1);
  if (!paused) {for (const mixer of mixers) mixer.update(dt); for (const update of updaters) update(dt);}
  renderer.render(world,camera);
});
