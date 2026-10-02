/* Retired demo surface: absence and no re-registration, not browser acceptance. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const retired = 'agent-pack/skills/cross-system-analysis/ui/cooperation-panel.js';
assert.equal(fs.existsSync(path.join(root, retired)), false, retired + ' must remain removed');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'agent-pack/ees-demo.json'), 'utf8'));
assert.equal(manifest.registration, 'retired');
for (const field of ['tools', 'models', 'skills', 'optional_existing_tools']) assert.equal((manifest[field] || []).length, 0);
assert.ok(manifest.preserve.includes('Native model connections'));
assert.ok(manifest.preserve.includes('ees_workflow'));
console.log('Specialist cooperation panel retirement/no-re-registration assertions passed');
