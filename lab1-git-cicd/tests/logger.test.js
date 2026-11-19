const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createLogger } = require('../src/logger');

function withDirectory(callback) {
  const directory = fs.mkdtempSync(path.join(__dirname, '.logger-'));
  try { callback(directory); }
  finally {
    for (const filename of fs.readdirSync(directory)) fs.unlinkSync(path.join(directory, filename));
    fs.rmdirSync(directory);
  }
}

test('daily files contain messages at the selected level', () => withDirectory(directory => {
  let date = new Date('2026-11-11T12:00:00.000Z');
  const logger = createLogger({ directory, minLevel: 'info', clock: () => date });
  logger.debug('excluded');
  logger.info('hello');
  date = new Date('2026-11-12T08:00:00.000Z');
  logger.error('problem');
  assert.match(fs.readFileSync(path.join(directory, '2026-11-11.log'), 'utf8'), /INFO hello/);
  assert.doesNotMatch(fs.readFileSync(path.join(directory, '2026-11-11.log'), 'utf8'), /excluded/);
  assert.match(fs.readFileSync(path.join(directory, '2026-11-12.log'), 'utf8'), /ERROR problem/);
}));

test('rotation preserves the previous file', () => withDirectory(directory => {
  const logger = createLogger({ directory, maxBytes: 60, clock: () => new Date('2026-11-11T12:00:00Z') });
  logger.warn('first message');
  logger.warn('second message');
  assert.match(fs.readFileSync(path.join(directory, '2026-11-11.1.log'), 'utf8'), /first message/);
  assert.match(fs.readFileSync(path.join(directory, '2026-11-11.log'), 'utf8'), /second message/);
}));

test('invalid logger settings are rejected', () => withDirectory(directory => {
  assert.throws(() => createLogger({ directory, minLevel: 'verbose' }));
  assert.throws(() => createLogger({ directory, maxBytes: 0 }));
}));
