const fs = require('node:fs');
const path = require('node:path');
const { rotateIfNeeded } = require('./logRotation');

const levels = ['debug', 'info', 'warn', 'error'];

function createLogger({ directory = 'logs', maxBytes = 1024 * 1024, minLevel = 'debug', clock = () => new Date() } = {}) {
  if (!levels.includes(minLevel)) throw new Error('Unknown minimum log level');
  if (!Number.isInteger(maxBytes) || maxBytes <= 0) throw new Error('maxBytes must be a positive integer');
  fs.mkdirSync(directory, { recursive: true });

  function log(level, message) {
    if (!levels.includes(level)) throw new Error('Unknown log level');
    if (levels.indexOf(level) < levels.indexOf(minLevel)) return;
    const timestamp = clock().toISOString();
    const filename = path.join(directory, `${timestamp.slice(0, 10)}.log`);
    const line = `${timestamp} ${level.toUpperCase()} ${String(message)}\n`;
    rotateIfNeeded(filename, Buffer.byteLength(line), maxBytes);
    fs.appendFileSync(filename, line, 'utf8');
  }

  return { log, ...Object.fromEntries(levels.map(level => [level, message => log(level, message)])) };
}

module.exports = { createLogger };
