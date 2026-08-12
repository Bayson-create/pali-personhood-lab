const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.resolve(__dirname, '..');
const context = { console, window: null };
context.window = context;
vm.createContext(context);
for (const file of ['schema.js', 'evidence.js', 'engine.js', 'fixtures.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'frontend', 'personhood', file), 'utf8'), context, { filename: file });
}
const request = { modelVersion: 'pali-canonical/v1', scenario: context.PaliPersonhood.FIXTURES[0], agents: context.PaliPersonhood.defaultAgents(), seed: 'ci', maxRounds: 1 };
const trace = context.PaliPersonhood.runInteraction(request);
if (!trace.validation.ok || !trace.streams.length) throw new Error('frontend fixture failed');
console.log('frontend fixture ok');
