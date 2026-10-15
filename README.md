# Infinite Creativity

مكتبة إبداعية موحدة للوكيل عبر MCP محلي. يجلب كل طلب بيانات العناصر مباشرة من مصادرها، وتبقى الأصول هناك. يبحث الوكيل ويتصفح الأقسام والحزم ويشاهد الصور ويسمع الصوت ويقرأ الملفات داخل MCP؛ لا توجد واجهة بشرية أو قاعدة بيانات عناصر أو فهرس متجهات محفوظ.

Local stdio MCP with live provider federation, exact categories, internal original/preview delivery and local media review. No asset records, manifests, search results, embeddings or original-media copies survive a request. Source routing and pinned model software are configuration/software, not an asset index.

## Install

Python 3.11+:

```bash
git clone --depth=1 --filter=blob:none https://github.com/qwzx4893-stack/Infinite-Creativity.git
cd Infinite-Creativity
python -m venv .venv
# PowerShell: .\.venv\Scripts\Activate.ps1
# Unix: source .venv/bin/activate
python -m pip install -e ".[media]"
infinite-creativity prepare-live-vision
infinite-creativity prepare-live-media
infinite-creativity prepare-live-style
infinite-creativity-mcp
```

These preparations install approximately 617 MiB of pinned, hash-verified local model software. No provider account or API key is required. Basic software browsing can run without the media extra; unreviewable media is withheld in strict mode. No sync, catalog download or snapshot export is needed.

For native BLEND/FBX/USD/BVH originals, install Blender separately or use an existing installation. `IC_BLENDER_PATH` may point to its executable; Windows Blender Foundation installations and `blender` on PATH are detected automatically. No Blender/model asset download is performed by starting MCP.

```json
{"mcpServers":{"infinite-creativity":{"command":"/absolute/path/.venv/bin/python","args":["-m","infinite_creativity.server"]}}}
```

On Windows, use `.venv\Scripts\python.exe` with escaped backslashes. Optional `IC_VISION_MODEL`, `IC_SPEECH_MODEL` and `IC_STYLE_MODEL` point to already prepared software folders; they contain no assets. GitHub public API limits still apply; an existing optional `GITHUB_TOKEN` can increase capacity, but browsing public providers does not require it.

Model preparation keeps one verified installation and removes failed temporary downloads; it does not create a second full model cache.

## Agent workflow

1. `library_overview` → `library_sections`: **12 root families, 83 exclusive leaves, 25 independent style facets**.
2. `section_sources` → `open_library`: current item cards, per-item rights and signed continuation cursors.
3. `library_packs` → `get_library_pack`: actual thematic pack members; no external page navigation is required.
4. `get_library_item` → `preview_asset`, `preview_audio_asset`, `inspect_3d_asset`: current native media and structure.
5. `asset_files` → `fetch_asset`, `fetch_asset_bundle`, `read_asset_file`, `read_asset_code`: selected original bytes/code and licence notices inside MCP.
6. `recommend_assets` provides a metadata shortlist; `rank_library_items` compares fresh admitted previews with the requested art direction through local CLIP. Scores are relative visual relevance, not safety/aesthetic probabilities.
7. `discover_sources` → `open_repository` discovers current public repositories and their actual rights-scoped items. The former dump of 32,938 unselected repository addresses has been removed.
8. `review_queue` contains **pending metadata only** for large/native originals. Use `candidate_asset_files` → `review_asset_media` for a selected file. ZIP packs also support `open_asset_archive` for internal directory navigation/member selection. The returned signed `asset_id` authorizes only the inspected file/dependencies; use it with `asset_files` and `read_asset_file`. Native conversions can return a screened MCP image in the same response. Progress notifications accompany the selected review.
9. `build_creative_kit` selects diverse current candidates for up to six named needs with exact category/kind filters; `assess_asset_fit` distinguishes declared compatibility, mismatch and unknown evidence. `review_library_board` returns a numbered native MCP image of selected current previews for the agent's visual judgment. No human frontend, saved kit or image gallery is created.
10. Prefer **`open_asset_package`** after selection: one RPC returns current rights, complete selected-file review, a scoped manifest, bounded licence notices, a native preview/listening excerpt where supported, and initial exact original bytes. Small source files can arrive completely. `next_offset` continues larger originals through `read_asset_file`.
11. `probe_library_sources` checks actual current samples and separates navigation, pending originals, screened previews, admitted originals and failures. Use `library_page` with `resume_cursor` and `retry_sources` to retry failed providers without discarding their positions. Transient failures get one automatic fresh-page retry.
12. `browse_asset_catalog(source="pd3m", offset=2000000, limit=3)` jumps directly into a publisher-curated million-scale image collection. `source="objaverse-curated"` accepts `partition` plus an offset inside that current metadata partition. Continue with `library_page`; query/style/section filters cover the current window/partition. Upstream totals and exclusions are explicit and are never labeled admitted unique counts. Source and item cards expose the available quality evidence.

Public references use `mode="reference"`. Paid/unverified originals remain inaccessible; a reference preview grants no copying rights. Every native preview, including a pack cover, is checked before emission.

## Source scope

The registry has **399 configured definitions and 334 default query scopes** after routing/alias rules, including **126 media repository connections retained in v0.6**, public OpenGameArt originals/ZIP members, Lazytextures CC0 models/materials/HDRIs/textures, and individually licensed Internet Archive audio/video/image originals. Scopes are not counts of sites or admitted assets. Metadata is refreshed for each request; outages and provider limits remain explicit.

v0.8 connects **Jam-Ready Assets, Generated Assets and Open Assets** through pack/item licence contracts, current source descriptors and original-file manifests. Large pack trees are traversed incrementally; Git LFS originals and Meshopt models are handled locally. Publisher catalogue totals are not added together as a unique usable inventory. See the [review of comparable asset libraries and implemented changes](docs/LIBRARY_DONOR_REVIEW.md) and [live verification](docs/V08_VERIFICATION.md).

v0.9 adds **five verified original-access sources**: Poly Pizza models, TextureCan CC0 material packs/maps, Met public-domain images, Cleveland CC0 images and Incompetech free attributed music/collections. It restores Motion Primitives access through `LICENCE.md`, improves request transport and preview/selection latency, strengthens duplicate/text filtering, and exposes **38 MCP tools**. See [changes, measured workflows and remaining limits](docs/V09_CHANGES_AND_VERIFICATION.md). FreePD was found closed; ccMixter originals returned HTTP 403 and were excluded from the configured library.

v0.10 adds **PD3M, curated Objaverse originals, Meta Open Sound instrument packs, GL Transitions shaders and official Manim motion examples**, with **39 MCP tools**. The current PD3M API reports **3,301,062 publisher-curated image records**; this is a directly navigable upstream row extent, not millions of independently reviewed/unique approved assets. The instrument collection exposes **1,075 real OGG samples in three named packs**. Models require current per-object source rights and a curation signal; transition shaders require individual MIT declarations. See [million-scale access, quality gates, actual delivery tests and limitations](docs/V010_LARGE_CATALOGS.md).

Existing integrations include Poly Haven, ambientCG, creator-scoped Kenney/KayKit/Quaternius packs, public creator-linked Drive folders, Fuel, FSD50K recordings, Blender demo subsets, Khronos assets, licensed LUTs, Openverse provider connections, Wikimedia, Uiverse, Motion Primitives, Mapcn, Codrops and current permissive UI/code repositories. Public presentation scopes are detailed in [coverage](docs/LIVE_SOURCE_COVERAGE.md).

**Account/key-required connectors have been removed**, including 21st, MotionSites, CGTrader, Dribbble, Freesound and authenticated Sketchfab downloads. The Objaverse adapter uses public AllenAI GLB mirrors and anonymous source-model metadata for current rights checks; it never requests a Sketchfab download token. Other nonworking placeholders are absent from live routing. No provider key onboarding is part of this library.

## Admission and practical limits

Filtering happens before cards are emitted and again before exact selected bytes are delivered. It checks explicit/suggestive metadata and source text, available original rasters, rendered static SVG, bounded complete audio plus translated speech, all bounded video/animated-image frames, and supported GLB textures/geometry/skin poses. Exact original/bundle digests and bounded client cursor receipts suppress duplicates during collection. Minimal, pixel and low-poly art is preserved.

Additional duplicate checks cover decoded raster pixels across lossless container/metadata changes (while preserving ICC colour-profile variants), and normalized GLB JSON/generator formatting with complete binary payloads preserved. Cover-image similarity never merges distinct original models. Text checks normalize common Unicode/diacritic/confusable/zero-width and leetspeak obfuscation. These remain bounded checks, not global visual-similarity or universal content guarantees.

Selected review supports BLEND, FBX, the USD family, BVH bone-motion proxies, scoped GLTF dependencies, OBJ/materials, PLY/STL/OFF/3MF, static Collada, PSD/PSB stored layers and ORA, plus larger supported raster/audio/video originals. Total source bytes are bounded to **512 MiB**, audio to 30 minutes, decoded frames to 18,000, triangles to two million and poses to 4,096; a five-minute processing deadline can impose a tighter practical limit. These are ceilings, not promises that every file below them passes. Ordinary browsing retains smaller budgets. See the [format/scope matrix](docs/V07_FORMAT_SUPPORT.md).

Unsupported native projects, simulation caches, unrendered layers, complex rigs and uncertain media remain withheld. Automatic classifiers can miss contextual innuendo or reject benign material. Technical validity is checked; no subjective aesthetic certification or global/permanent uniqueness guarantee is claimed. With no retained index, neither a verified million-item total nor a perfect all-site inventory is asserted. Signed client digests permit later exact-byte validation; no original or verdict index is saved. A byte-chunk call re-fetches the whole approved original to verify its digest. See [exact admission scopes](docs/LIVE_ADMISSION.md), [v0.7 verification](docs/V07_VERIFICATION.md) and the [comparison with similar MCP projects](docs/COMPARISON_2026-10-15.md).

The optional [WebMCP host adapter](docs/WEBMCP.md) forwards the same completed read tools to a compatible browser host. No human library UI or hosted endpoint is created.

```bash
python -m unittest discover -s tests -v
node tests/webmcp.test.mjs
# Optional real online acceptance checks; prints metrics, saves no originals:
python scripts/verify_live_workflows.py --probe
# New large-catalog and non-image delivery cases, also without provider keys:
python scripts/verify_live_workflows.py --case millionth-art --case curated-model --case instrument --case transition --case motion-code
```
