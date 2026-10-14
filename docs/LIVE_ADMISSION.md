# Live admission — v0.7

No saved asset or moderation index is used. Every request refreshes metadata; admission is performed before card display, and selected file variants are rechecked before delivery.

| Content | Built-in inspection |
|---|---|
| All items | Explicit and suggestive titles, descriptions, tags, filenames, source flags and applicable rights |
| Source code/notices | Current complete bounded text, including explicit/suggestive source-content policy |
| Raster originals | Decoded visible pixels, transparency/structure and pinned local image classifier |
| Static SVG | Source text, no external/active markup, complete local raster rendering and classifier |
| Audio | Entire bounded decode, empty/nonfinite/severe-clipping checks, local multilingual Whisper translation and lexical speech policy |
| Animated images/video | Every decoded frame inside the frame budget; audio track is checked when present |
| GLB | Self-contained geometry, every stored embedded image, six views, keyframe/midpoint skin/morph poses; sparse accessors, cubic interpolation and additional skin influences supported |
| Native 3D/layered files | Explicit selected-review path; exact capabilities and exclusions in [format support](V07_FORMAT_SUPPORT.md) |
| Packs | Container navigation; each selected member is independently admitted. Covers are checked before preview emission |
| Paid references | Screened current public presentation only; no original source reuse |

Fast browse budgets: 32 MiB original review, 90 seconds complete audio, 240 decoded frames, 120,000 triangles and 48 keyframe/midpoint poses. `review_asset_media` uses explicit extended limits: 512 MiB total source bytes, 48 files, 30 minutes audio, 18,000 frames, two million triangles, 4,096 poses, 128 megapixels and 2,048 layers, with a five-minute processing deadline. Full bounded decode/review remains required; no skipped frames are called reviewed. Timings and provider availability can impose tighter limits.

`review_queue` is metadata-only pending navigation, separate from admitted `items`. It never grants preview/original access, nor counts as admitted inventory. Explicit/suggestive metadata and failed sexual/suggestive image decisions do not enter this queue. Candidate manifests and archive directories can be navigated internally before review. Review fetches only current reusable originals and explicit dependency scopes into temporary staging; renderers are forbidden to fetch undeclared dependencies.

The returned client locator holds signed original digests, scalar sizes and a binding to current rights/revision/manifest. Later calls fetch metadata again and reject changed rights or manifests. Original delivery checks complete SHA256 and byte length before emitting even a chunk; unreviewed variants are excluded. No original, metadata, verdict or receipt index remains on the server. Locators expire after 24 hours or a server restart. A requested chunk currently re-fetches the entire bounded approved file, a deliberate cost of stateless exact-byte checks.

The pinned image, speech and CLIP model software is prepared with `prepare-live-vision`, `prepare-live-media`, `prepare-live-style`. No account/API key is needed. Missing models do not authorize unchecked media. Model files may stay installed; original bytes, embeddings, temporary parser files and verdicts are discarded when the RPC ends.

The optional local `IC_MEDIA_REVIEW_COMMAND` hook remains available for a trusted operator-supplied reviewer. It is a JSON argv array, never a source-provided command. Its verdict must match the current revision and cover sexual, suggestive and technical-quality checks. The built-in supported-media reviewers work without this hook.

Deduplication uses exact item/current-bundle identities and reviewed original digests. At most 384 digest-only receipts travel in the signed client cursor. This removes encountered duplicates while collecting, with no persistent global registry. Different material/dependency bundles remain distinct.

Image risk uses a conservative threshold and can produce false positives, including benign texture atlases. Discrete camera/keyframe views do not prove every occluded surface or continuously interpolated pose. Speech recognition can miss lyrics, words and nonverbal innuendo. CLIP ranks shown visual relevance and does not assess safety. Validity/empty/clipping/geometry checks do not certify aesthetic quality; intentional simple styles are preserved. No blanket guarantee of perfect sexual-content removal or globally exhaustive deduplication is made.

`IC_SAFETY_MODE=metadata` is an explicit compatibility mode that omits media review; strict is the default. Provider registration alone never implies safety, rights or original availability.
