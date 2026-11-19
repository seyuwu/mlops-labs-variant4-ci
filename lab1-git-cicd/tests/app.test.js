const { test } = require('node:test');
const assert = require('node:assert/strict');
const { add, multiply, subtract, divide, power, greet } = require('../src/app');

test('arithmetic operations', () => {
  assert.equal(add(2, 3), 5);
  assert.equal(multiply(4, 5), 20);
  assert.equal(subtract(5, 3), 2);
  assert.equal(divide(10, 2), 5);
  assert.equal(power(2, 3), 8);
});

test('division by zero is rejected', () => {
  assert.throws(() => divide(10, 0), /Division by zero/);
});

test('greeting includes the name', () => {
  assert.equal(greet('World'), 'Hello, World!');
});
