# v0.8 verification — 2026-10-15

This records measured scopes, not a claim that every asset in a publisher's library was reviewed. The [donor review](LIBRARY_DONOR_REVIEW.md) identifies the compared repositories, what was integrated, and what was intentionally excluded.

## Configuration and protocol

- 389 configured definitions; 324 default scopes after routing/alias rules. Neither number is an independent website count or an admitted asset count.
- 12 root families, 81 exclusive leaves, 25 independent style facets.
- A real local stdio MCP session advertised **36 tools**, including `build_creative_kit`, `assess_asset_fit`, and `review_library_board`.
- No persistent asset index, upstream catalogue copy, embedding index, original, or gallery was added. The new JSON file contains three source configurations only.

## Real upstream originals through stdio MCP

| Source | Observed current window | Verified internal access |
|---|---|---|
| Jam-Ready Assets | Dungeon sprite query returned admitted original PNG members; root browsing separately returned navigation-only pack folders | A 39,623-byte original PNG was resolved through Git LFS. `asset_files` refreshed its manifest, and `read_asset_file` returned a verified 512-byte chunk inside MCP |
| Generated Assets | Bench model admitted after local Meshopt decoding and original geometry screening | A 7,836-byte original compressed GLB, fresh manifest, and verified 512-byte internal chunk. Delivery preserves source bytes rather than silently substituting the decoded inspection representation |
| Open Assets | A barrel-related query selected `kenney-blaster-kit-silencer-larger`; it was pending because its GLB refers to an external texture | `review_asset_media` staged and checked **2 files / 21,635 bytes**, including the 11,412-byte GLB and 10,223-byte texture. It measured 120 triangles and returned native MCP text plus image. Fresh `asset_files` and a 512-byte original chunk then succeeded |

The third query demonstrates metadata relevance limitations: a related barrel/silencer description matched. It is not evidence of semantic perfection. Publisher catalogue totals (10,668 Open Assets records, 172 Generated Assets descriptors, 371 Jam-Ready packs reported by its README at review time) are not totals of newly admitted, unique or independently quality-certified assets.

`assess_asset_fit` returned **unverified** for an arbitrary rig target with no supporting publisher declaration. It did not invent compatibility. A real `build_creative_kit` call returned distinct admitted candidates in both requested groups: dungeon sprites and model furniture. Each group carried its own current filters/continuation evidence.

A native comparison-board run returned text plus an image, keeping an individual unavailable preview separate. This exposed a Git LFS preview URL that still pointed to its pointer file; the request-only manifest now resolves a matching preview to the verified LFS original. A follow-up stdio check successfully compared **both Jam-Ready and Generated Assets previews**, returned native text plus image, and reported **zero unavailable items**. Reference-only rights and per-item failure isolation are also covered by automated tests.

Observed live calls depended on the network and local CPU: approximately 5–28 seconds for sampled source/manifest/byte calls, 12 seconds for the two-group kit, and 48 seconds for the initial comparison. These are observations on this machine, not latency guarantees. Tests used the user's existing optional GitHub authentication to increase the public API allowance. No donor-specific account or key was added as a runtime requirement.

## Regression coverage

Final local run: **121 Python tests passed** in 13.1 seconds; **WebMCP adapter tests passed**; `git diff --check` passed. These are local regression results, not a claim of exhaustive live-source health.

The Python suite covers current licence/schema/attribution changes, restricted RUN packs, incomplete giant-root avoidance, nested pack rights, unknown mirror creators, unsafe paths, same-product and exact-byte duplicate suppression, diverse selection, unsupported compatibility evidence, preview/original-size distinction, local native comparison, and temporary-file cleanup.

Media tests encode and decode their own Meshopt triangle fixture, check packed 16-bit indices and positions, reject out-of-bounds/compression-budget claims, review a real generated GLB with an explicit relative PNG dependency, and reject a missing dependency. Exact repeated rendered images may share a prediction only within one geometry review; changes and later calls are screened again. Git LFS pointer and original digests are checked without changing upstream metadata records.

Commands:

```bash
python -m unittest discover -s tests -q
node tests/webmcp.test.mjs
git diff --check
```

## Practical boundaries

An animated crate from Open Assets required many pose screenings and was interrupted during the exploratory run. It is **not** recorded here as successfully reviewed. Native animations, skeleton-only clips, compression variants, very large scenes and dependent file layouts still have format/time limits. A static model succeeding does not authorize every variant or an entire pack.

Each later RPC re-fetches current upstream metadata and validates selected original bytes. Signed client locators carry bounded positions/digests, expire, and stop working after a server restart. Exact duplicate checks are bounded to current requests and cursor receipts. Automatic sexual/suggestive screening and technical validation can fail or misclassify; they do not certify artistic quality, all unseen surfaces or perfect safety.
