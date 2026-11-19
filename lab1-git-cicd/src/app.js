function add(a, b) { return a + b; }
function multiply(a, b) { return a * b; }
function subtract(a, b) { return a - b; }
function divide(a, b) {
  if (b === 0) throw new Error('Division by zero');
  return a / b;
}
function power(base, exponent) { return Math.pow(base, exponent); }
function greet(name) { return `Hello, ${name}!`; }

module.exports = { add, multiply, subtract, divide, power, greet };

if (require.main === module) {
  const { createLogger } = require('./logger');
  const logger = createLogger();
  logger.info('Application started');
  console.log('Application started');
  console.log('2 + 3 =', add(2, 3));
  console.log(greet('Student'));
}
