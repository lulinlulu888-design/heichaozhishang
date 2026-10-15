import { connectDatabase } from './connection.js';

export async function openStorage({ storage = 'mongodb', mongoUri, mongoDatabase, savePath, battleSavePath, tutorial, heroes, operationalDefaults }) {
  if (storage === 'mongodb') {
    if (savePath !== undefined || battleSavePath !== undefined) throw new Error('SQLite paths require explicit storage=sqlite; use the migration command for MongoDB');
    const { MongoProfileStore } = await import('./mongo-profiles.js');
    const { MongoHallStore } = await import('./mongo-hall.js');
    const { MongoBattleStore } = await import('./mongo-battles.js');
    const { MongoOperationsStore } = await import('./mongo-operations.js');
    const connection = await connectDatabase({ uri: mongoUri, database: mongoDatabase });
    try {
      const store = new MongoProfileStore(connection);
      const hall = heroes ? new MongoHallStore(connection) : null;
      const battles = tutorial ? new MongoBattleStore(connection) : null;
      const admin = new MongoOperationsStore(connection);
      await store.init();
      if (hall) await hall.init();
      if (battles) await battles.init();
      await admin.init(operationalDefaults);
      return { store, hall, battles, admin, backend: 'mongodb', close: () => connection.close() };
    } catch (error) { await connection.close(); throw error; }
  }
  if (storage !== 'sqlite') throw new Error('storage must be mongodb or explicit legacy sqlite');
  if (!savePath) throw new Error('Legacy SQLite mode requires an explicit savePath');
  const { ProfileStore } = await import('../store.js');
  const { HallStore } = await import('../hall-store.js');
  const { BattleStore } = await import('../battles.js');
  const store = new ProfileStore(savePath);
  let hall = null, battles = null;
  const close = async () => { try { hall?.close(); } finally { try { battles?.close(); } finally { store.close(); } } };
  try {
    if (tutorial) battles = new BattleStore(battleSavePath ?? (savePath === ':memory:' ? ':memory:' : `${savePath}.battles`));
    if (heroes) hall = new HallStore(savePath === ':memory:' ? ':memory:' : `${savePath}.hall`);
    return { store, hall, battles, backend: 'sqlite-legacy', close };
  } catch (error) { await close(); throw error; }
}
