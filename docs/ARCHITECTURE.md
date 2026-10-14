# Live federation architecture

The default stdio entry starts `live_server`. It does not open `IC_CATALOG_DB`, restore catalog releases, schedule ingestion, create a catalog database or persist provider results.

`live_http` makes bounded upstream HTTPS reads with no disk cache, ETag reuse or stale fallback. Duplicate reads may be memoized inside one MCP request, then discarded. Provider APIs can independently cache their own responses; fetched timestamps are observations, not guarantees about upstream CDN invalidation.

`live_providers` and its specialized modules normalize current inventories into cards with exact sections, rights, formats, source keys and original file manifests. Generic source registration does not imply usable media. Per-item licensing and scoped first-party code differ from gallery/reference viewing. Public site HTML is parsed declaratively; no site JavaScript is evaluated.

`live` signs compact source locators and cursor positions in process memory. Cursors hold selectors, filters, provider positions and bounded digest-only navigation receipts, with authenticated bounded decompression. They contain no cached item set. Source windows are queried with bounded fan-out and failures are reported independently. There is no global counter or persistent uniqueness/quality database.

Connection configuration includes curated routing scopes only; the former bulk address dump has been removed. Descriptions, licenses, file paths, revisions, previews and asset records are not preserved in that configuration. New repositories are discovered through current upstream search, then inspected through internal library actions. Unselected connections are not crawled for every query.

Selected-content operations revalidate upstream metadata first. Their compatibility parsers use an SQLite database and manifest tables entirely in RAM. Requested binary/text bytes can use temporary files for safe parsers; the request context removes those files before returning. Public outputs strip temporary paths. Git LFS pointers are resolved as pointer metadata, with original SHA256 identities. No fetched asset is executed.

Selected ZIP/multipart members use bounded HTTP ranges; range windows never claim a complete-file hash without complete data. Unsupported range transports, login/quota HTML and malformed originals are explicit errors. There is no automatic large-file bulk fallback. Original notices and dependency paths accompany selected bundles.

Historical offline modules remain behind explicit compatibility/maintenance settings. They are not used as a fallback by live MCP. Repository CI tests the live behavior without building or publishing a creative-asset index.


## Current v0.6 admission

Built-in local original-media reviewers, no-account public asset connectors and fresh visual matching are described in [admission](LIVE_ADMISSION.md), [coverage](LIVE_SOURCE_COVERAGE.md) and [verification](V06_VERIFICATION.md). Key-required connectors are removed. No item records, embeddings or originals persist across calls.
