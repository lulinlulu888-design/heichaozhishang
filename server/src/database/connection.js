import mongoose from 'mongoose';

export const DEFAULT_MONGO_URI = 'mongodb://127.0.0.1:27027/?replicaSet=hczs-local&directConnection=true';
export const SCHEMA_VERSION = 1;

/** Centralized Mongoose connection lifecycle, following so-im's shared database boundary. */
export async function connectDatabase({ uri = process.env.MONGODB_URI ?? DEFAULT_MONGO_URI,
  database = process.env.MONGODB_DB_NAME ?? 'hczs_local' } = {}) {
  if (typeof database !== 'string' || !/^hczs_[a-z0-9_]{1,52}$/.test(database)) {
    throw new Error('MongoDB database must use the dedicated hczs_ namespace');
  }
  const connection = mongoose.createConnection(uri, { dbName: database, maxPoolSize: 10, minPoolSize: 0,
    serverSelectionTimeoutMS: 5_000, connectTimeoutMS: 5_000, socketTimeoutMS: 10_000,
    autoIndex: false, autoCreate: false, bufferCommands: false, readPreference: 'primary',
    writeConcern: { w: 'majority', j: true, wtimeoutMS: 5_000 } });
  // Connection errors are surfaced by operations; avoid an unhandled EventEmitter error.
  connection.on('error', () => {});
  try {
    await connection.asPromise();
    const hello = await connection.db.admin().command({ hello: 1 });
    if (!hello.setName && hello.msg !== 'isdbgrid') throw new Error('MongoDB transactions require a replica set; run node tools/start_mongo.mjs');
    const metadata = connection.db.collection('hczs_metadata');
    const current = await metadata.findOne({ _id: 'schema' });
    if (current && (current.project !== 'hczs-rebuild' || current.version !== SCHEMA_VERSION)) {
      throw new Error('Unsupported MongoDB save identity/version; existing data was not migrated');
    }
    if (!current) {
      const existing = await connection.db.listCollections({}, { nameOnly: true }).toArray();
      if (existing.some(item => item.name !== 'hczs_metadata' && !item.name.startsWith('system.'))) {
        throw new Error('Refusing to adopt a non-empty MongoDB database without hczs metadata');
      }
      try { await metadata.insertOne({ _id: 'schema', project: 'hczs-rebuild', version: SCHEMA_VERSION }); }
      catch (error) { if (error.code !== 11000) throw error; }
      const claimed = await metadata.findOne({ _id: 'schema' });
      if (claimed?.project !== 'hczs-rebuild' || claimed.version !== SCHEMA_VERSION) throw new Error('MongoDB save identity changed during initialization');
    }
    return connection;
  } catch (error) {
    await connection.close().catch(() => {});
    // A driver exception can contain credentials from the configured URI.
    const publicMessages = ['MongoDB transactions require', 'Unsupported MongoDB save', 'Refusing to adopt', 'MongoDB save identity'];
    if (publicMessages.some(prefix => error.message.startsWith(prefix))) throw error;
    throw new Error('MongoDB connection/initialization failed; verify the dedicated database configuration and local replica set');
  }
}
