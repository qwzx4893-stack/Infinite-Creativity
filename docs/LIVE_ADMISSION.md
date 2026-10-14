# Live admission — v0.6

No saved asset or moderation index is used. Every request refreshes metadata; admission is performed before card display, and selected file variants are rechecked before delivery.

| Content | Built-in inspection |
|---|---|
| All items | Explicit and suggestive titles, descriptions, tags, filenames, source flags and applicable rights |
| Source code/notices | Current complete bounded text, including explicit/suggestive source-content policy |
| Raster originals | Decoded visible pixels, transparency/structure and pinned local image classifier |
| Static SVG | Source text, no external/active markup, complete local raster rendering and classifier |
| Audio | Entire bounded decode, empty/nonfinite/severe-clipping checks, local multilingual Whisper translation and lexical speech policy |
| Animated images/video | Every decoded frame inside the frame budget; audio track is checked when present |
| GLB | Self-contained geometry, embedded visible textures, six views, and supported keyframe/midpoint skin poses |
| Packs | Container navigation; each selected member is independently admitted. Covers are checked before preview emission |
| Paid references | Screened current public presentation only; no original source reuse |

Default budgets: 32 MiB selected-original review, 90 seconds complete decoded audio, 240 complete decoded frames, 120,000 triangles and 48 animation keyframe/midpoint poses. External model buffers, morph/cubic animation, unsupported influences/native project formats and items above these budgets require specialized review or a smaller independently licensed member. They are withheld rather than passed from a safe cover.

The pinned image, speech and CLIP model software is prepared with `prepare-live-vision`, `prepare-live-media`, `prepare-live-style`. No account/API key is needed. Missing models do not authorize unchecked media. Model files may stay installed; original bytes, embeddings, temporary parser files and verdicts are discarded when the RPC ends.

The optional local `IC_MEDIA_REVIEW_COMMAND` hook remains available for a trusted operator-supplied reviewer. It is a JSON argv array, never a source-provided command. Its verdict must match the current revision and cover sexual, suggestive and technical-quality checks. The built-in supported-media reviewers work without this hook.

Deduplication uses exact item/current-bundle identities and reviewed original digests. At most 384 digest-only receipts travel in the signed client cursor. This removes encountered duplicates while collecting, with no persistent global registry. Different material/dependency bundles remain distinct.

Image risk uses a conservative threshold and can produce false positives, including benign texture atlases. Discrete camera/keyframe views do not prove every occluded surface or continuously interpolated pose. Speech recognition can miss lyrics, words and nonverbal innuendo. CLIP ranks shown visual relevance and does not assess safety. Validity/empty/clipping/geometry checks do not certify aesthetic quality; intentional simple styles are preserved. No blanket guarantee of perfect sexual-content removal or globally exhaustive deduplication is made.

`IC_SAFETY_MODE=metadata` is an explicit compatibility mode that omits media review; strict is the default. Provider registration alone never implies safety, rights or original availability.
