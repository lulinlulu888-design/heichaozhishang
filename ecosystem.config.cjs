const path = require('node:path');

module.exports = {
  apps: [{
    name: 'hczs-battle',
    cwd: __dirname,
    script: path.join(__dirname, 'server/src/index.js'),
    interpreter: process.execPath,
    args: [
      '--port', '7458',
      '--data-directory', path.join(__dirname, 'analysis/game-data'),
      '--tutorial-directory', path.join(__dirname, 'analysis/first-encounter'),
      '--save-path', path.join(__dirname, 'runtime/server/tutorial-preview.sqlite'),
    ],
    exec_mode: 'fork',
    instances: 1,
    watch: false,
    autorestart: true,
    min_uptime: '10s',
    max_restarts: 10,
    restart_delay: 1500,
    kill_timeout: 5000,
    time: true,
    out_file: path.join(__dirname, 'runtime/server/pm2-battle.out.log'),
    error_file: path.join(__dirname, 'runtime/server/pm2-battle.err.log'),
    env: { NODE_ENV: 'production' },
  }],
};
