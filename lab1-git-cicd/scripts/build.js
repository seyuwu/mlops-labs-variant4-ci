const fs = require('node:fs');
fs.cpSync('src', 'dist', { recursive: true });
console.log('Source copied to dist/');
