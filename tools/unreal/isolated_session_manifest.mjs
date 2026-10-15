import { createHash } from 'node:crypto';
import { resolve, relative, isAbsolute, basename } from 'node:path';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA = /^[0-9a-f]{64}$/;
export const IDENTITY_COLLECTION = 'hczs_ue_test_identity';
export const REQUIRED_COLLECTIONS = ['profiles', 'hall_states', 'hall_requests',
  'hczs_battles', 'hczs_battle_commands', 'hczs_battle_creations', 'hczs_admin_config',
  'hczs_admin_releases', 'hczs_admin_requests', 'hczs_admin_logs', 'hczs_metadata', IDENTITY_COLLECTION];
export const digest = value => createHash('sha256').update(value).digest('hex');
export const isGeneratedDatabase = name => typeof name === 'string' && /^hczs_test_ue_[0-9a-f]{32}$/.test(name);
export const isTestPort = port => Number.isInteger(port) && port > 0 && port <= 65535 && ![7456,7457,7458,7460,7470,7471].includes(port);
/** Legacy manifests omitted the option and are always non-mainline runs. */
export function mainlineEnabled(manifest) {
  if(manifest && Object.hasOwn(manifest,'mainlineEnabled') && typeof manifest.mainlineEnabled!=='boolean')
    throw Error('mainlineEnabled must be a boolean');
  return manifest?.mainlineEnabled ?? false;
}
export function resolveMainlineOption(requested, previousManifest) {
  if(requested!==undefined&&typeof requested!=='boolean')throw Error('--mainline must be a boolean option');
  if(previousManifest) {
    if(requested!==undefined)throw Error('Resume inherits mainlineEnabled; an override is forbidden');
    return mainlineEnabled(previousManifest);
  }
  return requested ?? false;
}
function mainlineFaultFlag(manifest) {
  if(manifest && Object.hasOwn(manifest,'mainlineFaults') && typeof manifest.mainlineFaults!=='boolean')
    throw Error('mainlineFaults must be a boolean');
  return manifest?.mainlineFaults ?? false;
}
export function mainlineFaultMode(manifest) {
  const enabled=mainlineFaultFlag(manifest);
  if(enabled&&(!mainlineEnabled(manifest)||manifest.faults!==false))throw Error('Mainline faults require an exclusive mainline run');
  return enabled;
}
export function resolveMainlineFaultOption(enabled=false,{mainlineEnabled: mainline=false,faults=false,resume=false}={}) {
  if(typeof enabled!=='boolean'||(enabled&&(!mainline||faults||resume)))
    throw Error('--mainline-faults requires --mainline and forbids --faults or resume');
  return enabled;
}
export function within(root, path) { const r=relative(resolve(root),resolve(path)); return Boolean(r) && !r.startsWith('..') && !isAbsolute(r); }
export function validateMongoUri(uri) {
  const u=new URL(uri);
  if(u.protocol!=='mongodb:'||u.hostname!=='127.0.0.1'||u.port!=='27027'||u.username||u.password||(u.pathname!=='/'&&u.pathname!=='')
    ||u.searchParams.get('replicaSet')!=='hczs-local'||u.searchParams.get('directConnection')!=='true'
    ||[...u.searchParams.keys()].length!==2) throw Error('Only the project loopback replica set on 27027 is permitted');
  return digest(uri);
}

/** Validate the isolated UI target before issuing any HTTP inspection. */
export function validateUIRunningManifest(manifest) {
  mainlineEnabled(manifest);
  mainlineFaultMode(manifest);
  if(manifest?.schemaVersion!==2||manifest.mode!=='isolated-native-session-test'||!isTestPort(manifest.port)
    ||!isGeneratedDatabase(manifest.mongoDatabase)||manifest.address!==`http://127.0.0.1:${manifest.port}`
    ||manifest.mongoEndpoint!=='127.0.0.1:27027'||!SHA.test(manifest.mongoUriSha256??'')
    ||!UUID.test(manifest.runId)||!UUID.test(manifest.databaseIdentity)||!UUID.test(manifest.processIdentity)
    ||!Number.isSafeInteger(manifest.pid)||manifest.pid<1||!Number.isSafeInteger(manifest.processIndex)||manifest.processIndex<0
    ||manifest.faults!==false||typeof manifest.preserveDatabase!=='boolean'||!/^[0-9a-f]{48}$/.test(manifest.controlToken??''))
    throw Error('Unrecognized isolated UI manifest');
}

/** Authenticated read-only response from the actual isolated Node process. */
export function validateLiveTestIdentity(identity, manifest, manifestText) {
  validateUIRunningManifest(manifest);
  if(identity?.schemaVersion!==1||identity.mode!=='isolated-native-session-test-identity'||identity.readOnly!==true
    ||identity.databaseLifecycle!=='running'||identity.pid!==manifest.pid||identity.port!==manifest.port
    ||identity.mongoDatabase!==manifest.mongoDatabase||identity.mongoEndpoint!==manifest.mongoEndpoint
    ||identity.runId!==manifest.runId||identity.databaseIdentity!==manifest.databaseIdentity
    ||identity.processIdentity!==manifest.processIdentity||identity.processIndex!==manifest.processIndex
    ||mainlineEnabled(identity)!==mainlineEnabled(manifest)
    ||mainlineFaultFlag(identity)!==mainlineFaultMode(manifest)
    ||identity.manifestSha256!==digest(manifestText))throw Error('Live Node/database identity does not match the isolated run manifest');
  return identity;
}

/** A delete is allowed only for the current claim of this generated database. */
export function validateOwnedDatabaseForDrop(identity, {databaseName,runId,databaseIdentity,processIdentity}) {
  if(!isGeneratedDatabase(databaseName)||!UUID.test(runId)||!UUID.test(databaseIdentity)||!UUID.test(processIdentity)
    ||identity?._id!=='identity'||identity.schemaVersion!==1||identity.mode!=='isolated-native-session-test'
    ||identity.mongoDatabase!==databaseName||identity.runId!==runId||identity.databaseIdentity!==databaseIdentity
    ||identity.processIdentity!==processIdentity)throw Error('Database ownership changed; refusing to delete it');
}

/** Resume can only reopen an authenticated, normally stopped run created by this tool. */
export function validateResumeManifest({manifest, manifestText, manifestPath, allowedRoot, stopped, mongoUri}) {
  mainlineEnabled(manifest);
  if(mainlineFaultMode(manifest))throw Error('Mainline fault runs cannot be resumed');
  const directory=resolve(manifestPath,'..'), hash=digest(manifestText);
  if(basename(manifestPath)!=='server.json'||!within(allowedRoot,directory))throw Error('Resume manifest must be server.json in an isolated run directory');
  if(manifest?.schemaVersion!==2||manifest.mode!=='isolated-native-session-test'||!isGeneratedDatabase(manifest.mongoDatabase)
    ||!UUID.test(manifest.runId)||!UUID.test(manifest.databaseIdentity)||!UUID.test(manifest.processIdentity)
    ||!Number.isSafeInteger(manifest.processIndex)||manifest.processIndex<0||!isTestPort(manifest.port)
    ||manifest.address!==`http://127.0.0.1:${manifest.port}`||manifest.mongoEndpoint!=='127.0.0.1:27027'
    ||resolve(manifest.recordDirectory??'')!==directory||resolve(manifest.tracePath??'')!==resolve(directory,'http-trace.jsonl')
    ||manifest.mongoUriSha256!==validateMongoUri(mongoUri)||manifest.preserveDatabase!==true||manifest.faults!==false
    ||!Number.isSafeInteger(manifest.pid)||manifest.pid<1||!/^[0-9a-f]{48}$/.test(manifest.controlToken??''))throw Error('Unrecognized or non-resumable isolated test manifest');
  if(stopped?.stopped!==true||stopped.databaseDropped!==false||stopped.mongoDatabase!==manifest.mongoDatabase
    ||stopped.runId!==manifest.runId||stopped.databaseIdentity!==manifest.databaseIdentity
    ||stopped.processIdentity!==manifest.processIdentity||stopped.processIndex!==manifest.processIndex
    ||stopped.manifestSha256!==hash||!Number.isSafeInteger(stopped.time))throw Error('The previous test server was not normally stopped with its database preserved');
  return {directory,hash};
}
export function validateDatabaseIdentity(identity, manifest, hash) {
  if(identity?._id!=='identity'||identity.schemaVersion!==1||identity.mode!=='isolated-native-session-test'
    ||identity.runId!==manifest.runId||identity.databaseIdentity!==manifest.databaseIdentity
    ||identity.mongoDatabase!==manifest.mongoDatabase||identity.recordDirectory!==manifest.recordDirectory
    ||identity.mongoUriSha256!==manifest.mongoUriSha256||identity.activeManifestSha256!==hash
    ||identity.processIdentity!==manifest.processIdentity||identity.processIndex!==manifest.processIndex
    ||mainlineEnabled(identity)!==mainlineEnabled(manifest)
    ||mainlineFaultFlag(identity)!==mainlineFaultMode(manifest)
    ||identity.lifecycle!=='stopped'||!SHA.test(identity.firstManifestSha256??''))throw Error('Database identity does not match the preserved test run');
}
export function validateResumeCollections({names,profile,battle,config,release,profileCount,battleCount,creationCount,mainlineEnabled: enabled=false}) {
  if(typeof enabled!=='boolean'||![...REQUIRED_COLLECTIONS,...(enabled?['mainline_states','mainline_requests']:[])].every(name=>names.includes(name)))throw Error('Preserved test schema is incomplete');
  if(profileCount!==1||battleCount!==1||creationCount!==1||!UUID.test(profile?._id)||profile.schemaVersion!==1
    ||!Number.isSafeInteger(profile.revision)||profile.revision<1||!UUID.test(battle?.id)||battle.schemaVersion!==1
    ||battle.profile_id!==profile._id||!Number.isSafeInteger(battle.revision)||battle.revision<1
    ||config?._id!=='config'||config.schemaVersion!==1||!Number.isSafeInteger(config.revision)||config.revision<1
    ||release?._id!==0||release.schemaVersion!==1)throw Error('Resume requires one valid test profile and battle and an initialized operational schema');
  return {profileId:profile._id,battleId:battle.id,revision:battle.revision};
}
