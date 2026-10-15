import { resolve } from 'node:path';
import { connectDatabase } from '../server/src/database/connection.js';
import { migrateSqlite } from '../server/src/database/migrate-sqlite.js';

// Stop source SQLite writers AND target application writers before running.
// Defaults to dry-run. No service is stopped by this tool.
const args = process.argv.slice(2), options = {};
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--apply') options.apply = true;
  else if (['--source', '--database', '--uri'].includes(args[i]) && args[i + 1] && !args[i + 1].startsWith('--')) options[args[i].slice(2)] = args[++i];
  else throw new Error('Usage: node tools/migrate_server_sqlite.mjs --source FILE --database hczs_NAME [--uri URI] [--apply]');
}
if (!options.source || !options.database) throw new Error('--source and --database are required; default mode is dry-run');
const connection = await connectDatabase({ uri: options.uri, database: options.database });
try {
  console.log(JSON.stringify(await migrateSqlite({ connection, savePath: resolve(options.source), apply: options.apply }), null, 2));
} finally { await connection.close(); }
