# Live federation architecture

The default stdio entry starts `live_server`. It does not open `IC_CATALOG_DB`, restore catalog releases, schedule ingestion, create a catalog database or persist provider results.

`live_http` makes bounded upstream HTTPS reads with no disk cache, ETag reuse or stale fallback. Duplicate reads may be memoized inside one MCP request, then discarded. Provider APIs can independently cache their own responses; fetched timestamps are observations, not guarantees about upstream CDN invalidation.

`live_providers` and its specialized modules normalize current inventories into cards with exact sections, rights, formats, source keys and original file manifests. Generic source registration does not imply usable media. Per-item licensing and scoped first-party code differ from gallery/reference viewing. Public site HTML is parsed declaratively; no site JavaScript is evaluated.

`live` signs compact source locators and cursor positions in process memory. Cursors hold selectors, filters, provider positions and bounded digest-only navigation receipts, with authenticated bounded decompression. They contain no cached item set. Source windows are queried with bounded fan-out and failures are reported independently. There is no global counter or persistent uniqueness/quality database.

Connection configuration includes previously discovered repository addresses only. Descriptions, licenses, file paths, revisions, previews and asset records are not preserved in that configuration. New repositories are discovered through current upstream search, then inspected through internal library actions. Unselected connections are not crawled for every query.

Selected-content operations revalidate upstream metadata first. Their compatibility parsers use an SQLite database and manifest tables entirely in RAM. Requested binary/text bytes can use temporary files for safe parsers; the request context removes those files before returning. Public outputs strip temporary paths. Git LFS pointers are resolved as pointer metadata, with original SHA256 identities. No fetched asset is executed.

Selected ZIP/multipart members use bounded HTTP ranges; range windows never claim a complete-file hash without complete data. Unsupported range transports, login/quota HTML and malformed originals are explicit errors. There is no automatic large-file bulk fallback. Original notices and dependency paths accompany selected bundles.

Historical offline modules remain behind explicit compatibility/maintenance settings. They are not used as a fallback by live MCP. Repository CI tests the live behavior without building or publishing a creative-asset index.

## v0.5 admission and expansion

Admission now occurs before cards are emitted and again on selected-item access. See [current admission policy](LIVE_ADMISSION.md) for the strict classifier/reviewer setup, bounded cursor digest receipts and the exact limits of preview, geometry, temporal and aesthetic coverage. See [connection expansion](V05_CONNECTIONS.md) for checked scope and external account requirements. Batched searches and section routing remain inside MCP; no human frontend or retained item index is added.
