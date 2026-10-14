# Architecture and guarantees

Provider API / curated repository -> metadata adapter -> license and textual admission checks -> SQLite + FTS5 -> bounded agent tools -> original upstream access links.

The registry tracks providers separately from asset records. Each record includes a canonical URL, stable URL-derived ID, upstream ID, title, kind, inferred styles, platforms, formats, author, license, license evidence URL, source revision, first/last observation times, active flag and safety/access states. Canonical URLs are unique; identical binaries across providers are not content-deduplicated because the index does not download binaries. Do not call record counts counts of unique original artworks.

Source reconciliation marks missing entries inactive only after a complete adapter snapshot. Paginated API failures and truncated GitHub trees fail visibly rather than pretending that partial data is complete. Previously known assets remain available if a source temporarily fails. Current remote availability is checked at use time by the agent; stored links can age or disappear.

FTS5 provides indexed text ranking. Keyset browsing avoids deep offset scans. Search results are capped at 100 records, tool input is parameterized, and FTS terms are quoted. Recommendations use a bounded candidate pool, style overlap, keyword overlap and source diversity. Results include their matching reasons. JSON style/platform filters and exact-count queries can cost more at millions of records; benchmarks are required before a production scale claim.

Network ingestion has an endpoint allowlist, TLS, fixed application user agent, per-host pacing, bounded retries/response sizes, cached ETags and Last-Modified values. GitHub credentials are sent only to api.github.com; automatic redirects are disabled to avoid credential forwarding. Upstream payloads are data, never instructions. Only trusted maintainers may change the registry and connector code. Runtime agents have no sync/write MCP tool.

Iconify indexing consumes the project's official JSON exports rather than making hundreds of listing API requests. These exports include SVG definitions transiently in the private ingestion cache; only names, facets, source and license metadata enter published snapshots. Cache files are excluded from Git. HTTP 429 stops source ingestion rather than retrying before the provider's allowed time.

SQLite is a local single-writer index; each MCP call opens a connection, enabling simultaneous read calls. Data is delivered through release snapshots instead of Git history. A SHA-256 manifest checks snapshot consistency. Live databases must not be copied during an active writer; export is an operator task after sync, and scheduled runs are serialized.

GitHub search exposes at most 1,000 results for an individual query. The configured search budget enumerates only bounded pages, explicitly not the entire Internet. New repositories are reference records until their item inventory, rights and content are reviewed. Provider counts, repository counts, individual icon records and collection variants are not interchangeable.

An additional persistent discovery queue partitions topic queries by creation date. Ranges above 1,000 results split in two; smaller ranges paginate with a saved cursor. Each scheduled run has a 20-request expansion budget, and subsequent runs resume the queue. New daily date intervals are enqueued separately. If even a single day exceeds the ceiling, the job reports a need for finer qualifiers and retains the checkpoint instead of silently skipping data.

MCP uses the official Python SDK v1 maintenance line with a <2 bound; the tested v1 API avoids untested v2 migration assumptions. Transport is local stdio. No hosted endpoint, OAuth server, visual-embedding service or distributed crawler is provisioned by this repository.
