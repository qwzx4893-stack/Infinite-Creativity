/** Optional browser host adapter. No page/UI is created by the local MCP. */
const allowed = new Set([
  'library_overview', 'library_sections', 'list_sources', 'open_library',
  'library_page', 'get_library_item', 'library_packs', 'get_library_pack',
  'asset_files', 'read_asset_code', 'preview_asset', 'preview_audio_asset',
  'inspect_3d_asset', 'inspect_asset_media', 'read_asset_file', 'fetch_asset',
  'fetch_asset_bundle', 'discover_sources', 'open_repository',
  'catalog_providers', 'search_library_batch', 'inspect_library_batch',
  'recommend_assets', 'rank_library_items', 'section_sources',
  'candidate_asset_files', 'open_asset_archive', 'review_asset_media',
  'build_creative_kit', 'assess_asset_fit', 'review_library_board',
]);

const hosts = new WeakMap();

export async function registerInfiniteCreativity(options) {
  const { document } = options;
  if (!document?.modelContext?.registerTool) return { supported: false, registered: [], dispose() {} };
  if (hosts.has(document)) return hosts.get(document);
  const pending = registerTools(options);
  hosts.set(document, pending);
  pending.catch(() => hosts.delete(document));
  return pending;
}

async function registerTools({ document, client, onError = () => {} }) {
  if (!document?.modelContext?.registerTool) return { supported: false, registered: [], dispose() {} };
  if (!client?.listTools || !client?.callTool) throw new TypeError('Provide an initialized MCP client');
  const lifecycle = new AbortController();
  const registered = [];
  try {
    const response = await client.listTools();
    for (const tool of response.tools) {
      if (!allowed.has(tool.name)) continue;
      await document.modelContext.registerTool({
        name: `infinite_creativity_${tool.name}`,
        title: tool.title ?? tool.name,
        description: tool.description ?? 'Read current creative library data',
        inputSchema: tool.inputSchema,
        annotations: { readOnlyHint: true, untrustedContentHint: true },
        async execute(input) {
          if (input === null || Array.isArray(input) || typeof input !== 'object') throw new TypeError('Tool arguments must be an object');
          const result = await client.callTool({ name: tool.name, arguments: input });
          // Await completion, preserve structured/native media, and never turn
          // upstream data into a command or page execution.
          return JSON.parse(JSON.stringify(result));
        },
      }, { signal: lifecycle.signal });
      registered.push(tool.name);
    }
    return { supported: true, registered, dispose() { lifecycle.abort(); hosts.delete(document); } };
  } catch (error) {
    lifecycle.abort();
    onError(error);
    throw error;
  }
}
