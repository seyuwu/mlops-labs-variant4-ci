const fs = require('node:fs');
const path = require('node:path');

function rotateIfNeeded(filename, incomingBytes, maxBytes) {
  if (!fs.existsSync(filename) || fs.statSync(filename).size + incomingBytes <= maxBytes) return;
  const parsed = path.parse(filename);
  let index = 1;
  let archive;
  do {
    archive = path.join(parsed.dir, `${parsed.name}.${index++}${parsed.ext}`);
  } while (fs.existsSync(archive));
  fs.renameSync(filename, archive);
}

module.exports = { rotateIfNeeded };
