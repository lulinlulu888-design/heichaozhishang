/** Static audit only. No UI, build, engine initialization, or APK code execution.
 * node tools/verify_cocos_character.mjs [--config <resources/config.json>]
 *   [--output <report.json>] [--project <Cocos project>] [--creator <installation>] [--model elsa|enemy991]
 * node tools/verify_cocos_character.mjs --self-test
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MODELS = {
  elsa: { uuid: '4dcbfcd6-ae42-4aa1-bac5-c4cf8efc1d3a', bones: 180, nodes: 182, materials: 9, textures: 7,
    clips: ['stand_idle', 'skin'], source: 'analysis/animation/recovered',
    sha256: 'fcb17d9b88dc7ba726dbb7cb1a37fa4879065896cc969874424a5390c679b63b' },
  enemy991: { uuid: 'c744184a-ec92-4c0e-8f59-7c763f7c5192', bones: 61, nodes: 63, materials: 1, textures: 1,
    clips: ['idle', 'fire'], source: 'analysis/tutorial-enemy-animation',
    sha256: 'fb9286f587c7c24b7344e5116318c45224add56deaacf36d21ed22b2aa0276ea' },
};
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const slash = value => value.split(path.sep).join('/');
const relative = value => slash(path.relative(ROOT, value));
const require = createRequire(import.meta.url);
const ensure = (condition, message) => { if (!condition) throw new Error(message); };
const equalSet = (a, b) => a.length === b.length && new Set(a).size === a.length && a.every(x => b.includes(x));

export function parseCCON(bytes, decode) {
  ensure(bytes.length >= 16 && bytes.length <= 64 * 1024 * 1024, 'CCON size outside audit budget');
  ensure(bytes.toString('ascii', 0, 4) === 'CCON', 'invalid CCON magic');
  ensure(bytes.readUInt32LE(4) === 2, 'only observed CCON v2 is supported');
  ensure(bytes.readUInt32LE(8) === bytes.length, 'CCON total length mismatch');
  const length = bytes.readUInt32LE(12);
  ensure(length > 0 && length <= 8 * 1024 * 1024 && length <= bytes.length - 16, 'CCON document length outside bounds');
  const documentBytes = bytes.subarray(16, 16 + length);
  // Pass an exact ArrayBuffer; the trusted decoder's _bin uses buffer offsets.
  const document = decode(documentBytes.buffer.slice(documentBytes.byteOffset, documentBytes.byteOffset + length));
  ensure(Array.isArray(document) && document.length <= 20000, 'unsupported CCON document shape');
  const chunks = [];
  let offset = 16 + length;
  while (offset < bytes.length) {
    const aligned = Math.ceil(offset / 8) * 8;
    ensure(aligned + 4 <= bytes.length, 'CCON truncated chunk header');
    ensure(bytes.subarray(offset, aligned).every(x => x === 0), 'CCON nonzero alignment padding');
    offset = aligned;
    const size = bytes.readUInt32LE(offset);
    offset += 4;
    ensure(size <= bytes.length - offset, 'CCON chunk outside bounds');
    chunks.push(bytes.subarray(offset, offset + size));
    offset += size;
  }
  ensure(offset === bytes.length && chunks.length === 1, 'expected exactly one fully consumed CCON chunk');
  return { document, chunk: chunks[0], documentBytes: length };
}

export function floatArray(ref, chunk) {
  ensure(ref && ref.__type__ === 'TypedArrayRef' && ref.ctor === 'Float32Array', 'unsupported typed array reference');
  ensure(Number.isSafeInteger(ref.offset) && ref.offset >= 0 && ref.offset % 4 === 0 &&
    Number.isSafeInteger(ref.length) && ref.length >= 0 && ref.offset <= chunk.length &&
    ref.length <= (chunk.length - ref.offset) / 4, 'typed array outside chunk');
  const result = new Array(ref.length);
  for (let i = 0; i < result.length; ++i) {
    result[i] = chunk.readFloatLE(ref.offset + i * 4);
    ensure(Number.isFinite(result[i]), 'nonfinite animation component');
  }
  return result;
}

function refAt(document, ref, type) {
  ensure(ref && Number.isSafeInteger(ref.__id__) && ref.__id__ >= 0 && ref.__id__ < document.length, 'invalid object reference');
  const object = document[ref.__id__];
  ensure(object && object.__type__ === type, `expected ${type}`);
  return object;
}

export function prefabTree(document) {
  ensure(Array.isArray(document) && document[0]?.__type__ === 'cc.Prefab', 'expected prefab document');
  const root = refAt(document, document[0].data, 'cc.Node');
  const visited = new Set(), paths = [], ambiguousNames = [], slashNames = [];
  function visit(node, currentPath) {
    ensure(!visited.has(node), 'prefab cycle/shared child');
    visited.add(node); paths.push(currentPath);
    ensure(Array.isArray(node._children), 'prefab children must be an array');
    const names = new Set();
    for (const ref of node._children) {
      const child = refAt(document, ref, 'cc.Node');
      ensure(typeof child._name === 'string' && child._name.length > 0, 'empty prefab child name');
      if (child._name.includes('/')) slashNames.push(child._name);
      if (names.has(child._name)) ambiguousNames.push(child._name);
      names.add(child._name);
      ensure(refAt(document, child._parent, 'cc.Node') === node, 'prefab parent/child disagreement');
      visit(child, currentPath ? currentPath + '/' + child._name : child._name);
    }
  }
  visit(root, '');
  function resolve(nodePath) {
    if (nodePath === '') return root;
    if (typeof nodePath !== 'string') return null;
    let node = root;
    for (const segment of nodePath.split('/')) {
      if (!segment) return null;
      const matches = node._children.map(r => refAt(document, r, 'cc.Node')).filter(n => n._name === segment);
      if (matches.length !== 1) return null;
      node = matches[0];
    }
    return node;
  }
  return { root, resolve, nodeCount: visited.size, paths, ambiguousNames, slashNames };
}

function poses(bytes, expectedBones) {
  ensure(bytes.length >= 20 && bytes.toString('ascii', 0, 8) === 'HCZPOSE1', 'invalid HCZPOSE1 header');
  const bones = bytes.readUInt32LE(8), frames = bytes.readUInt32LE(12), rate = bytes.readFloatLE(16);
  ensure(bones === expectedBones && frames > 0 && frames <= 10000 && Number.isFinite(rate) && rate > 0,
    'unsupported poses dimensions');
  ensure(bytes.length === 20 + bones * frames * 40, 'HCZPOSE1 length mismatch');
  return { bones, frames, rate, component(frame, bone, index) {
    const value = bytes.readFloatLE(20 + ((frame * bones + bone) * 10 + index) * 4);
    ensure(Number.isFinite(value), 'nonfinite source pose');
    return value;
  } };
}

export function quaternionDifference(a, b) {
  return Math.min(Math.max(...a.map((v, i) => Math.abs(v - b[i]))),
    Math.max(...a.map((v, i) => Math.abs(v + b[i]))));
}

async function audit(options) {
  ensure(Object.hasOwn(MODELS, options.model), 'model must be elsa or enemy991');
  const model = MODELS[options.model], UUID = model.uuid;
  const modelFolder = 'recovered/models/' + options.model;
  const inputFiles = new Map();
  const report = {
    format: 'hczs-cocos-character-import-audit-v1',
    scope: 'static imported data and selected build resources; no runtime playback',
    passed: false, libraryPassed: false, buildPassed: false, model: options.model,
    runtimePlaybackVerified: false, checks: [], clips: [],
    tolerances: { translationAbsolute: 0.000002, scaleAbsolute: 0.000002,
      quaternionComponentUpToSign: 0.000002, time: 'exact Float32(frame / original sample rate)' },
    limitations: ['No rendering, animation evaluation, skin deformation, material visual equivalence or gameplay was executed.',
      'Build animation binaries are compared byte-for-byte by SHA256. Packed prefab/material JSON is not independently deserialized; pack hashes are recorded without claiming content equivalence.'],
  };
  const check = (scope, name, passed, details = {}) => report.checks.push({ scope, name, passed: Boolean(passed), ...details });
  async function read(filename) {
    const bytes = await fs.readFile(filename);
    inputFiles.set(filename, { path: relative(filename), bytes: bytes.length, sha256: sha(bytes) });
    return bytes;
  }
  const json = async filename => JSON.parse((await read(filename)).toString('utf8'));
  const libraryPath = (uuid, ext) => path.join(options.project, 'library', uuid.slice(0, 2), uuid + ext);
  try {
    const verifier = await read(fileURLToPath(import.meta.url));
    report.verifier = { path: relative(fileURLToPath(import.meta.url)), sha256: sha(verifier) };
    const ts = require(path.join(options.creator, 'resources/app.asar.unpacked/node_modules/typescript'));
    const decoderFile = path.join(options.creator, 'resources/resources/3d/engine/external/deserialize/notepack_decode.ts');
    const source = (await read(decoderFile)).toString('utf8');
    const compiled = ts.transpileModule(source, { compilerOptions: {
      target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ES2020,
    } }).outputText;
    // Execute only the explicitly trusted, installed Cocos data decoder, never
    // reconstructed game scripts or code embedded in an imported asset.
    const { notepackDecode } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
    report.decoder = { source: relative(decoderFile), sourceSha256: sha(Buffer.from(source)),
      typescriptVersion: ts.version, emittedSha256: sha(Buffer.from(compiled)) };
    const metaPath = path.join(options.project, 'assets/resources', modelFolder, options.model + '.glb.meta');
    const meta = await json(metaPath);
    ensure(sha(await read(metaPath.slice(0, -5))) === model.sha256, 'source GLB differs from verified export');
    ensure(meta.uuid === UUID && meta.importer === 'gltf' && meta.imported, 'unexpected GLB import metadata');
    const all = Object.values(meta.subMetas);
    const group = type => all.filter(x => x.importer === type);
    const clips = group('gltf-animation').sort((a, b) => a.userData.gltfIndex - b.userData.gltfIndex);
    const materials = group('gltf-material'), textures = group('texture'), images = group('gltf-embeded-image');
    check('library', 'expected_import_inventory', clips.length === 2 && materials.length === model.materials &&
      textures.length === model.textures && images.length === model.textures && group('gltf-scene').length === 1 && group('gltf-skeleton').length === 1,
    { clips: clips.length, materials: materials.length, textures: textures.length, images: images.length });
    const prefabMeta = group('gltf-scene')[0], skeletonMeta = group('gltf-skeleton')[0];
    ensure(prefabMeta && skeletonMeta, 'missing prefab or skeleton');
    const prefab = await json(libraryPath(prefabMeta.uuid, '.json'));
    const skeleton = await json(libraryPath(skeletonMeta.uuid, '.json'));
    const tree = prefabTree(prefab);
    report.prefab = { uuid: prefabMeta.uuid, nodeCount: tree.nodeCount, slashNames: tree.slashNames,
      ambiguousNames: tree.ambiguousNames };
    check('library', 'prefab_unambiguous_segment_names', !tree.slashNames.length && !tree.ambiguousNames.length, report.prefab);
    ensure(skeleton.__type__ === 'cc.Skeleton' && Array.isArray(skeleton._joints), 'invalid skeleton');
    const joints = skeleton._joints;
    const missingJoints = joints.filter(p => !tree.resolve(p));
    check('library', `all_${model.bones}_skeleton_paths_resolve`, joints.length === model.bones && new Set(joints).size === model.bones && !missingJoints.length,
      { bonePaths: joints.length, unresolvedPaths: missingJoints });
    const animations = prefab.filter(x => x.__type__ === 'cc.SkeletalAnimation');
    const renderers = prefab.filter(x => x.__type__ === 'cc.SkinnedMeshRenderer');
    check('library', 'prefab_animation_and_renderer_links', animations.length === 1 && renderers.length === 1 &&
      refAt(prefab, animations[0].node, 'cc.Node') === tree.root &&
      equalSet(animations[0]._clips.map(r => r.__uuid__), clips.map(c => c.uuid)) &&
      clips.some(c => c.uuid === animations[0]._defaultClip?.__uuid__) &&
      renderers[0]._skeleton?.__uuid__ === skeletonMeta.uuid && refAt(prefab, renderers[0]._skinningRoot, 'cc.Node') === tree.root &&
      equalSet(renderers[0]._materials.map(r => r.__uuid__), materials.map(m => m.uuid)));
    const unlit = await json(path.join(options.creator, 'resources/resources/3d/engine/editor/assets/effects/builtin-unlit.effect.meta'));
    const textureIds = textures.map(t => t.uuid), usedTextures = new Set();
    report.materials = [];
    for (const m of materials.sort((a, b) => a.userData.gltfIndex - b.userData.gltfIndex)) {
      const data = await json(libraryPath(m.uuid, '.json'));
      const texture = data._props?.[0]?.mainTexture?.__uuid__;
      usedTextures.add(texture);
      const ok = data.__type__ === 'cc.Material' && data._effectAsset?.__uuid__ === unlit.uuid && textureIds.includes(texture);
      report.materials.push({ uuid: m.uuid, name: data._name, effect: data._effectAsset?.__uuid__, texture, passed: ok });
    }
    check('library', 'unlit_materials_use_all_expected_textures', report.materials.every(m => m.passed) &&
      equalSet([...usedTextures], textureIds), { effectUuidFromInstalledBuiltin: unlit.uuid });
    report.textures = [];
    for (const t of textures) {
      const data = await json(libraryPath(t.uuid, '.json'));
      const imageUuid = t.userData.imageUuidOrDatabaseUri;
      ensure(images.some(i => i.uuid === imageUuid), 'texture references unknown embedded image');
      const png = await read(libraryPath(imageUuid, '.png'));
      const ok = data.__type__ === 'cc.Texture2D' && data.content?.mipmaps?.length === 1 &&
        data.content.mipmaps[0] === imageUuid && png.length >= 24 &&
        png.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex'));
      report.textures.push({ uuid: t.uuid, imageUuid, pngSha256: sha(png), passed: ok });
    }
    check('library', 'all_texture_image_links', report.textures.every(t => t.passed) &&
      equalSet(report.textures.map(t => t.imageUuid), images.map(i => i.uuid)));

    const clipBytes = new Map();
    for (const c of clips) {
      const bytes = await read(libraryPath(c.uuid, '.bin'));
      clipBytes.set(c.uuid, bytes);
      const { document, chunk, documentBytes } = parseCCON(bytes, notepackDecode);
      const clip = document[0];
      ensure(clip.__type__ === 'cc.AnimationClip' && model.clips.includes(clip._name), 'unexpected clip');
      const sourceMeta = await json(path.join(ROOT, model.source, clip._name + '.json'));
      const sourceBytes = await read(path.join(ROOT, model.source, clip._name + '.poses'));
      ensure(sha(sourceBytes) === sourceMeta.poses.sha256, 'source poses SHA256 mismatch');
      const original = poses(sourceBytes, model.bones), mapping = sourceMeta.bone_mapping;
      ensure(mapping.length === model.bones && equalSet(mapping.map(r => r.clip_index), Array.from({ length: model.bones }, (_, i) => i)) &&
        equalSet(mapping.map(r => r.mesh_joint), Array.from({ length: model.bones }, (_, i) => i)), 'bone mapping is not a complete bijection');
      ensure(sourceMeta.samples === original.frames && sourceMeta.sample_rate === original.rate, 'source pose metadata mismatch');
      const exotic = refAt(document, clip._exoticAnimation, 'cc.animation.ExoticAnimation');
      const nodes = exotic._nodeAnimations.map(r => refAt(document, r, 'cc.animation.ExoticNodeAnimation'));
      const unresolved = nodes.map(n => n._path).filter(p => !tree.resolve(p));
      check('library', `${clip._name}:${model.nodes}_node_paths_resolve`, nodes.length === model.nodes &&
        new Set(nodes.map(n => n._path)).size === model.nodes && unresolved.length === 0,
      { nodeTracks: nodes.length, unresolvedPaths: unresolved });
      const nodeByPath = new Map(nodes.map(n => [n._path, n]));
      const metrics = { comparedBoneFrames: 0, comparedTimeKeys: 0, maxTimeError: 0,
        maxTranslationError: 0, maxScaleError: 0, maxQuaternionErrorUpToSign: 0, quaternionSignFlips: 0 };
      let valid = true;
      const errors = [];
      function track(node, prop) {
        const data = refAt(document, node['_' + prop], 'cc.animation.ExoticTrack');
        const values = refAt(document, data.values, prop === 'rotation' ? 'cc.animation.ExoticQuatTrackValues' : 'cc.animation.ExoticVec3TrackValues');
        ensure(values._isQuantized === false, 'quantized track is outside audit scope');
        const time = floatArray(data.times, chunk), value = floatArray(values._values, chunk);
        ensure(value.length === time.length * (prop === 'rotation' ? 4 : 3), 'track component count mismatch');
        return { time, value };
      }
      for (const row of mapping) {
        const bonePath = joints[row.mesh_joint];
        ensure(bonePath.split('/').at(-1) === row.name, 'bone mapping name/path mismatch');
        const node = nodeByPath.get(bonePath);
        ensure(node, 'bone has no imported animation track: ' + bonePath);
        const tracks = { position: track(node, 'position'), rotation: track(node, 'rotation'), scale: track(node, 'scale') };
        for (const t of Object.values(tracks)) ensure(t.time.length === original.frames, 'imported frame count differs from original');
        for (let frame = 0; frame < original.frames; ++frame) {
          const expectedTime = Math.fround(frame / original.rate);
          for (const t of Object.values(tracks)) {
            const delta = Math.abs(t.time[frame] - expectedTime);
            metrics.maxTimeError = Math.max(metrics.maxTimeError, delta); ++metrics.comparedTimeKeys;
            if (delta !== 0) valid = false;
          }
          const sourceQ = Array.from({ length: 4 }, (_, i) => original.component(frame, row.clip_index, i));
          const importedQ = tracks.rotation.value.slice(frame * 4, frame * 4 + 4);
          const qDelta = quaternionDifference(sourceQ, importedQ);
          metrics.maxQuaternionErrorUpToSign = Math.max(metrics.maxQuaternionErrorUpToSign, qDelta);
          if (sourceQ.reduce((sum, v, i) => sum + v * importedQ[i], 0) < 0) ++metrics.quaternionSignFlips;
          let positionDelta = 0, scaleDelta = 0;
          for (let i = 0; i < 3; ++i) {
            positionDelta = Math.max(positionDelta, Math.abs(tracks.position.value[frame * 3 + i] - original.component(frame, row.clip_index, 4 + i)));
            scaleDelta = Math.max(scaleDelta, Math.abs(tracks.scale.value[frame * 3 + i] - original.component(frame, row.clip_index, 7 + i)));
          }
          metrics.maxTranslationError = Math.max(metrics.maxTranslationError, positionDelta);
          metrics.maxScaleError = Math.max(metrics.maxScaleError, scaleDelta);
          if (qDelta > 0.000002 || positionDelta > 0.000002 || scaleDelta > 0.000002) {
            valid = false;
            if (errors.length < 12) errors.push({ bonePath, frame, qDelta, positionDelta, scaleDelta });
          }
          ++metrics.comparedBoneFrames;
        }
      }
      const auxiliary = nodes.filter(n => !joints.includes(n._path));
      const auxiliaryResults = [];
      for (const n of auxiliary) {
        const prefabNode = tree.resolve(n._path);
        let ok = Boolean(prefabNode);
        if (prefabNode) {
          for (const prop of ['position', 'rotation', 'scale']) {
            const t = track(n, prop), key = { position: '_lpos', rotation: '_lrot', scale: '_lscale' }[prop];
            const expected = (prop === 'rotation' ? ['x', 'y', 'z', 'w'] : ['x', 'y', 'z']).map(k => prefabNode[key][k]);
            ok = ok && t.time.length === 1 && t.time[0] === 0 &&
              (prop === 'rotation' ? quaternionDifference(t.value, expected) <= 0.000002 :
                t.value.every((v, i) => Math.abs(v - expected[i]) <= 0.000002));
          }
        }
        auxiliaryResults.push({ path: n._path, passed: ok });
      }
      check('library', `${clip._name}:auxiliary_tracks_match_prefab`, auxiliary.length === 2 && auxiliaryResults.every(r => r.passed),
        { tracks: auxiliaryResults });
      const durationValid = clip._duration === Math.fround((original.frames - 1) / original.rate);
      check('library', `${clip._name}:all_original_pose_keys_match`, valid && durationValid,
        { ...metrics, duration: clip._duration, expectedDurationFloat32: Math.fround((original.frames - 1) / original.rate), firstTransformFailures: errors });
      report.clips.push({ name: clip._name, uuid: c.uuid, sourceFrames: original.frames,
        sourceSampleRate: original.rate, cocosSampleSetting: clip.sample, duration: clip._duration,
        boneCount: original.bones, nodeTracks: nodes.length, documentBytes, chunkBytes: chunk.length,
        sourcePosesSha256: sha(sourceBytes), importedSha256: sha(bytes), ...metrics });
    }
    check('library', 'both_expected_clips_present', equalSet(report.clips.map(c => c.name), model.clips));

    const config = await json(options.config);
    report.build = { config: relative(options.config), bundleName: config.name, animationBytes: [], packedArtifacts: [] };
    ensure(config.name === 'resources' && config.debug === true && typeof config.paths === 'object',
      'only observed debug resources config format is supported');
    const prefabEntries = Object.entries(config.paths).filter(([, entry]) => entry[1] === 'cc.Prefab' && entry[0].startsWith(modelFolder + '/'));
    check('build', 'unique_model_prefab_resource_path', prefabEntries.length === 1 && prefabEntries[0][0] === prefabMeta.uuid,
      { entries: prefabEntries.map(([uuid, entry]) => ({ uuid, path: entry[0], type: entry[1] })) });
    const modelEntries = Object.entries(config.paths).filter(([uuid]) => uuid.startsWith(UUID + '@'));
    check('build', 'resource_config_inventory_matches_import',
      modelEntries.filter(([, v]) => v[1] === 'cc.AnimationClip').length === 2 &&
      modelEntries.filter(([, v]) => v[1] === 'cc.Material').length === model.materials &&
      modelEntries.filter(([, v]) => v[1] === 'cc.Texture2D').length === model.textures &&
      all.every(x => Object.prototype.hasOwnProperty.call(config.paths, x.uuid)));
    const importRoot = path.resolve(path.dirname(options.config), config.importBase);
    ensure(importRoot.startsWith(path.dirname(options.config) + path.sep), 'build importBase escapes bundle');
    for (const c of clips) {
      const filename = path.join(importRoot, c.uuid.slice(0, 2), c.uuid + '.bin');
      const built = await read(filename);
      const match = built.equals(clipBytes.get(c.uuid));
      report.build.animationBytes.push({ uuid: c.uuid, path: relative(filename), sha256: sha(built), matchesLibrary: match });
      check('build', `${c.name}:bytes_match_audited_library`, match, { buildSha256: sha(built), librarySha256: sha(clipBytes.get(c.uuid)) });
    }
    for (const [pack, entries] of Object.entries(config.packs ?? {})) {
      if (entries.some(uuid => uuid.startsWith(UUID + '@'))) {
        ensure(/^[a-zA-Z0-9_-]+$/.test(pack), 'unsafe pack identifier');
        const filename = path.join(importRoot, pack.slice(0, 2), pack + '.json');
        const bytes = await read(filename);
        JSON.parse(bytes.toString('utf8')); // Syntax only; no fabricated compiled-prefab decoder.
        report.build.packedArtifacts.push({ path: relative(filename), sha256: sha(bytes), uuids: entries.filter(uuid => uuid.startsWith(UUID + '@')),
          contentEquivalenceToLibrary: 'not independently verified' });
      }
    }
  } catch (error) {
    check('audit', 'completed_without_structural_or_io_failure', false, { error: error.message });
  }
  // Refuse a mixed snapshot if a concurrent import/build changed any input.
  for (const [filename, previous] of inputFiles) {
    try {
      const now = await fs.readFile(filename);
      if (sha(now) !== previous.sha256) check('audit', 'input_changed_during_audit', false, { path: previous.path });
    } catch (error) { check('audit', 'input_disappeared_during_audit', false, { path: previous.path, error: error.message }); }
  }
  const auditOk = report.checks.filter(c => c.scope === 'audit').every(c => c.passed);
  report.libraryPassed = auditOk && report.clips.length === 2 && report.checks.filter(c => c.scope === 'library').every(c => c.passed);
  report.buildPassed = auditOk && Boolean(report.build) && report.checks.filter(c => c.scope === 'build').every(c => c.passed);
  report.passed = report.libraryPassed && report.buildPassed;
  report.inputs = [...inputFiles.values()].sort((a, b) => a.path.localeCompare(b.path, 'en'));
  await fs.mkdir(path.dirname(options.output), { recursive: true });
  const temporary = options.output + '.tmp-' + process.pid;
  try { await fs.writeFile(temporary, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' }); await fs.rename(temporary, options.output); }
  finally { await fs.rm(temporary, { force: true }); }
  console.log(JSON.stringify({ report: relative(options.output), passed: report.passed,
    libraryPassed: report.libraryPassed, buildPassed: report.buildPassed,
    failedChecks: report.checks.filter(c => !c.passed).map(c => ({ name: c.name, error: c.error, unresolvedPaths: c.unresolvedPaths })),
    clips: report.clips.map(c => ({ name: c.name, boneFrames: c.comparedBoneFrames,
      maxTranslationError: c.maxTranslationError, maxScaleError: c.maxScaleError, maxQuaternionErrorUpToSign: c.maxQuaternionErrorUpToSign })) }, null, 2));
  return report.passed;
}

function selfTest() {
  const fixture = Buffer.alloc(32); fixture.write('CCON'); fixture.writeUInt32LE(2, 4);
  fixture.writeUInt32LE(32, 8); fixture.writeUInt32LE(1, 12); fixture[16] = 0x90;
  fixture.writeUInt32LE(4, 24); fixture.writeFloatLE(1, 28);
  const decoded = parseCCON(fixture, () => []);
  assert.deepEqual(floatArray({ __type__: 'TypedArrayRef', ctor: 'Float32Array', offset: 0, length: 1 }, decoded.chunk), [1]);
  for (const changed of [fixture.subarray(0, 15), fixture.subarray(0, 31), (() => { const b = Buffer.from(fixture); b.writeUInt32LE(100, 12); return b; })(),
    (() => { const b = Buffer.from(fixture); b.writeUInt32LE(100, 24); return b; })()]) assert.throws(() => parseCCON(changed, () => []));
  assert.throws(() => floatArray({ __type__: 'TypedArrayRef', ctor: 'Float32Array', offset: 0, length: 2 }, decoded.chunk));
  const doc = [{ __type__: 'cc.Prefab', data: { __id__: 1 } }, { __type__: 'cc.Node', _name: 'root', _children: [{ __id__: 2 }] },
    { __type__: 'cc.Node', _name: 'mesh/unsafe', _parent: { __id__: 1 }, _children: [] }];
  assert.equal(prefabTree(doc).resolve('mesh/unsafe'), null);
  assert.equal(quaternionDifference([0, 0, 0, 1], [0, 0, 0, -1]), 0);
  console.log('8 static parser/path/quaternion self-checks passed');
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  if (process.argv.includes('--self-test')) selfTest();
  else {
    const options = { project: path.join(ROOT, 'legacy/cocos-poc'), creator: path.join(ROOT, '.tools/cocos/3.8.8'),
      config: path.join(ROOT, 'legacy/cocos-poc/build/web-desktop/assets/resources/config.json'),
      output: path.join(ROOT, 'analysis/cocos-character/import-verification.json'), model: 'elsa' };
    for (let i = 2; i < process.argv.length; i += 2) {
      const key = process.argv[i].slice(2);
      ensure(process.argv[i].startsWith('--') && Object.hasOwn(options, key) && process.argv[i + 1], 'invalid option');
      options[key] = key === 'model' ? process.argv[i + 1] : path.resolve(process.argv[i + 1]);
    }
    if (options.model === 'enemy991' && !process.argv.includes('--output')) {
      options.output = path.join(ROOT, 'analysis/cocos-enemy/import-verification-web.json');
    }
    if (!await audit(options)) process.exitCode = 1;
  }
}
