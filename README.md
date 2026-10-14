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

```json
{"mcpServers":{"infinite-creativity":{"command":"/absolute/path/.venv/bin/python","args":["-m","infinite_creativity.server"]}}}
```

On Windows, use `.venv\Scripts\python.exe` with escaped backslashes. Optional `IC_VISION_MODEL`, `IC_SPEECH_MODEL` and `IC_STYLE_MODEL` point to already prepared software folders; they contain no assets. GitHub public API limits still apply; an existing optional `GITHUB_TOKEN` can increase capacity, but browsing public providers does not require it.

## Agent workflow

1. `library_overview` → `library_sections`: **12 root families, 80 exclusive leaves, 25 independent style facets**.
2. `section_sources` → `open_library`: current item cards, per-item rights and signed continuation cursors.
3. `library_packs` → `get_library_pack`: actual thematic pack members; no external page navigation is required.
4. `get_library_item` → `preview_asset`, `preview_audio_asset`, `inspect_3d_asset`: current native media and structure.
5. `asset_files` → `fetch_asset`, `fetch_asset_bundle`, `read_asset_file`, `read_asset_code`: selected original bytes/code and licence notices inside MCP.
6. `recommend_assets` provides a metadata shortlist; `rank_library_items` compares fresh admitted previews with the requested art direction through local CLIP. Scores are relative visual relevance, not safety/aesthetic probabilities.
7. `discover_sources` → `open_repository` discovers current public repositories and their actual rights-scoped items. The former dump of 32,938 unselected repository addresses has been removed.

Public references use `mode="reference"`. Paid/unverified originals remain inaccessible; a reference preview grants no copying rights. Every native preview, including a pack cover, is checked before emission.

## Source scope

The v0.6 registry has **322 default query scopes**, including **126 newly retained media repository connections**, public OpenGameArt originals/ZIP members, Lazytextures CC0 models/materials/HDRIs/textures, and individually licensed Internet Archive audio/video/image originals. Scopes are not counts of sites or admitted assets. Metadata is refreshed for each request; outages and provider limits remain explicit.

Existing integrations include Poly Haven, ambientCG, creator-scoped Kenney/KayKit/Quaternius packs, public creator-linked Drive folders, Fuel, FSD50K recordings, Blender demo subsets, Khronos assets, licensed LUTs, Openverse provider connections, Wikimedia, Uiverse, Motion Primitives, Mapcn, Codrops and current permissive UI/code repositories. Public presentation scopes are detailed in [coverage](docs/LIVE_SOURCE_COVERAGE.md).

**Account/key-required connectors have been removed**, including 21st, MotionSites, CGTrader, Dribbble, Freesound and Sketchfab. Other nonworking placeholders are absent from live routing. No provider key onboarding is part of this library.

## Admission and practical limits

Filtering happens before cards are emitted and again before exact selected bytes are delivered. It checks explicit/suggestive metadata and source text, available original rasters, rendered static SVG, bounded complete audio plus translated speech, all bounded video/animated-image frames, and supported GLB textures/geometry/skin poses. Exact original/bundle digests and bounded client cursor receipts suppress duplicates during collection. Minimal, pixel and low-poly art is preserved.

Unsupported native projects, large recordings/videos, complex rigs and uncertain media are withheld; a safe thumbnail does not authorize an unreviewed variant. Automatic classifiers can miss contextual innuendo or reject benign material. Technical validity is checked; no subjective aesthetic certification or global/permanent uniqueness guarantee is claimed. With no retained index, neither a verified million-item total nor a perfect all-site inventory is asserted. See [exact admission scopes](docs/LIVE_ADMISSION.md) and [verification](docs/V06_VERIFICATION.md).

The optional [WebMCP host adapter](docs/WEBMCP.md) forwards the same completed read tools to a compatible browser host. No human library UI or hosted endpoint is created.

```bash
python -m unittest discover -s tests -v
node tests/webmcp.test.mjs
```
