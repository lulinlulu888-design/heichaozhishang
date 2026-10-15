// Initial test ownership is claimed only after the unchanged production
// initializer has legally created hczs_metadata in a verified empty database.
import mongoose from '../../server/node_modules/mongoose/index.js';
import { connectDatabase, SCHEMA_VERSION } from '../../server/src/database/connection.js';
import { IDENTITY_COLLECTION, isGeneratedDatabase, validateMongoUri } from './isolated_session_manifest.mjs';

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function assertProductionMetadata(row) {
  if(row?._id!=='schema'||row.project!=='hczs-rebuild'||row.version!==SCHEMA_VERSION)
    throw Error('The generated test database lacks the exact production schema identity');
}
export async function initializeFreshTestDatabase({mongoUri,identity,onPhase=async()=>{}}) {
  if(!isGeneratedDatabase(identity?.mongoDatabase)||identity?._id!=='identity'||identity.schemaVersion!==1
    ||identity.mode!=='isolated-native-session-test'||identity.processIndex!==0||identity.lifecycle!=='starting'
    ||!UUID.test(identity.runId)||!UUID.test(identity.databaseIdentity)||!UUID.test(identity.processIdentity)
    ||identity.mongoUriSha256!==validateMongoUri(mongoUri))throw Error('Invalid fresh test database ownership');
  const probe=mongoose.createConnection(mongoUri,{dbName:identity.mongoDatabase,serverSelectionTimeoutMS:5000});
  probe.on('error',()=>{});
  try {
    await probe.asPromise();
    if((await probe.db.listCollections({}, {nameOnly:true}).toArray()).length!==0)
      throw Error('Generated test database already contains collections; refusing initialization');
    await onPhase('preflight-empty');
  } finally {await probe.close().catch(()=>{});}
  const initialized=await connectDatabase({uri:mongoUri,database:identity.mongoDatabase});
  try {
    assertProductionMetadata(await initialized.db.collection('hczs_metadata').findOne({_id:'schema'}));
    const names=(await initialized.db.listCollections({}, {nameOnly:true}).toArray()).map(row=>row.name);
    if(names.length!==1||names[0]!=='hczs_metadata')throw Error('Unexpected collections appeared during production test initialization');
    await onPhase('production-metadata-initialized');
    // The fixed identity _id gives a single winner if two claims race. No
    // existing identity is updated or adopted by an initial process.
    await initialized.db.collection(IDENTITY_COLLECTION).insertOne(identity);
    await onPhase('identity-claimed');
  } finally {await initialized.close();}
}
