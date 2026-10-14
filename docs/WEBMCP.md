# Optional WebMCP adapter

The local stdio MCP remains the primary interface. No website or human library UI is required. A browser host that already has an initialized MCP client may import `integrations/webmcp.mjs` and call:

```js
const registration = await registerInfiniteCreativity({ document, client });
// On host teardown:
registration.dispose();
```

The adapter uses the imperative proposed [WebMCP API](https://webmachinelearning.github.io/webmcp/), registers only supported read tools, preserves completed structured/native responses, marks upstream data untrusted, feature-detects unsupported browsers, and cleans up with AbortSignal. It does not create an HTTP proxy, acquire credentials, execute source code, expose publishing/generation tools or register tools on other people's websites. Host-to-local-MCP connection and browser support must be supplied by the embedding host.

Test with `node tests/webmcp.test.mjs`.
