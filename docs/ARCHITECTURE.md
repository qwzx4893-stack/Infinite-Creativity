# Architecture and guarantees

Provider API / reviewed repository / official free archive -> item license and textual admission checks -> SQLite + FTS5 + file manifests -> unified MCP sessions/resources -> internal previews, original code and bounded content cache.

The registry tracks providers separately from items. Records include canonical URLs, stable IDs, titles, kinds, artistic facets, formats, authors, license evidence, source revisions and admission states. `asset_details` stores file manifests and features in snapshots. Counts include variants and references, not unique original artworks. SHA256 deduplicates retrieved bytes in the private cache; it does not merge catalog identities across creators.

Reconciliation marks missing entries inactive only after a complete inventory. Pagination failures and truncated trees preserve prior records. Content retrieval checks availability and indexed hashes. GitHub media uses immutable commits and blob SHA checks. Software license scopes are reviewed separately from media: a repository MIT license does not automatically make its models usable.

FTS5 provides indexed text ranking. Keyset browsing avoids deep offset scans. Search results are capped at 100 records, tool input is parameterized, and FTS terms are quoted. Recommendations use a bounded candidate pool, style overlap, keyword overlap and source diversity. Results include their matching reasons. JSON style/platform filters and exact-count queries can cost more at millions of records; benchmarks are required before a production scale claim.

Network ingestion has an endpoint allowlist, TLS, fixed application user agent, per-host pacing, bounded retries/response sizes, cached ETags and Last-Modified values. GitHub credentials are sent only to api.github.com; automatic redirects are disabled to avoid credential forwarding. Upstream payloads are data, never instructions. Only trusted maintainers may change the registry and connector code. Runtime agents have no sync/write MCP tool.

Iconify indexing consumes the project's official JSON exports rather than making hundreds of listing API requests. These exports include SVG definitions transiently in the private ingestion cache; only names, facets, source and license metadata enter published snapshots. Cache files are excluded from Git. HTTP 429 stops source ingestion rather than retrying before the provider's allowed time.

SQLite is a local single-writer index; each MCP call opens a connection, enabling simultaneous read calls. Data is delivered through release snapshots instead of Git history. A SHA-256 manifest checks snapshot consistency. Live databases must not be copied during an active writer; export is an operator task after sync, and scheduled runs are serialized.

GitHub search exposes at most 1,000 results for an individual query. The configured search budget enumerates only bounded pages, explicitly not the entire Internet. New repositories are reference records until their item inventory, rights and content are reviewed. Provider counts, repository counts, individual icon records and collection variants are not interchangeable.

An additional persistent discovery queue partitions topic queries by creation date. Ranges above 1,000 results split in two; smaller ranges paginate with a saved cursor. Each scheduled run has a 20-request expansion budget, and subsequent runs resume the queue. New daily date intervals are enqueued separately. If even a single day exceeds the ceiling, the job reports a need for finer qualifiers and retains the checkpoint instead of silently skipping data.

MCP uses the official Python SDK v1 maintenance line with a <2 bound; the tested v1 API avoids untested v2 migration assumptions. Transport is local stdio. No hosted endpoint, OAuth server, visual-embedding service or distributed crawler is provisioned by this repository.

## Internal content and private runtime

`Library` provides internal cards, sessions, signed ranked/keyset cursors, item/file resource URIs, previews, original code windows, dependency resolution, actual glTF inspection and bounded binary delivery. Network operations run in worker threads with separate database connections. Sessions and collections are stored in `state/private/runtime.sqlite`; cursor secrets and cached manifests stay outside exports. Catalog refreshes invalidate older library views.

`ContentCache` validates public HTTPS hosts and DNS addresses, redirects, byte budgets and file checksums. Cache files are named by SHA256, with no execution or unsafe ZIP extraction. Kenney inventories read central directories and CC0 license members through a seekable HTTP Range transport. Individual member retrieval verifies indexed CRC32 and ZIP decompression limits. Cached originals work offline. Fuel inventories check per-model license metadata; restricted models remain references.

File manifests preserve relative paths and main/variant/dependency/license roles. Poly Haven included textures remain associated with their selected format/resolution bundle. GitHub blobs are checked against their indexed SHA; LFS pointers resolve to the public original with its declared SHA256. Native MCP images are limited to supported raster MIME types; SVG is original text. Chunk delivery works when the client cannot read the server's local cache.

Topical discovery now covers 272 configured queries. A separate 24-query oldest-first search sweep and the persistent 20-request partition queue refresh slices every six hours. Repository-level discoveries remain references and do not inflate usable media counts. Single-host SQLite is the current index; distributed search, authenticated HTTP hosting, visual embeddings and visual moderation are future work.
