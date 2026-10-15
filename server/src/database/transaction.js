/** Driver withTransaction owns transient/unknown-commit retries. Duplicate insert races
 * need a fresh transaction snapshot so the winner's receipt can be read. */
export async function runTransaction(connection, callback) {
  for (let attempt = 0; ; attempt++) {
    const session = await connection.startSession();
    try {
      let result;
      await session.withTransaction(async () => { result = await callback(session); }, {
        readConcern: { level: 'snapshot' }, writeConcern: { w: 'majority', j: true, wtimeoutMS: 5_000 }, readPreference: 'primary',
        maxCommitTimeMS: 5_000, timeoutMS: 10_000,
      });
      return result;
    } catch (error) {
      if (error.code !== 11000 || attempt >= 4 || error.hasErrorLabel?.('UnknownTransactionCommitResult')) throw error;
    } finally { await session.endSession(); }
  }
}
