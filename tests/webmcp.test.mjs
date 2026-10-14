import assert from 'node:assert/strict';
import { registerInfiniteCreativity } from '../integrations/webmcp.mjs';
let registrations = [];
const client = {
  async listTools() { return { tools: [{ name: 'open_library', inputSchema: { type: 'object' } }, { name: 'delete_everything' }] }; },
  async callTool(call) { assert.equal(call.name, 'open_library'); return { structuredContent: { items: [{ title: 'Original' }] } }; },
};
assert.equal((await registerInfiniteCreativity({ document: {}, client })).supported, false);
const host = { modelContext: { registerTool(t, o) { registrations.push([t, o]); } } };
const adapter = await registerInfiniteCreativity({ document: host, client });
assert.equal(await registerInfiniteCreativity({ document: host, client }), adapter);
assert.equal(registrations.length, 1);
assert.equal(registrations[0][0].annotations.untrustedContentHint, true);
assert.equal((await registrations[0][0].execute({})).structuredContent.items[0].title, 'Original');
await assert.rejects(() => registrations[0][0].execute('bad input'), TypeError);
adapter.dispose();
assert.equal(registrations[0][1].signal.aborted, true);
let failedSignal;
await assert.rejects(() => registerInfiniteCreativity({ client, document: { modelContext: { registerTool(t, o) { failedSignal = o.signal; throw new Error('unsupported'); } } } }));
assert.equal(failedSignal.aborted, true);
process.stdout.write('WebMCP adapter tests passed\n');
