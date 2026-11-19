const { test } = require('node:test');
const assert = require('node:assert/strict');
const { add } = require('../src/app');
test('addition handles negative numbers', () => assert.equal(add(-2, 3), 1));
