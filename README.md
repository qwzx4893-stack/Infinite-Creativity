# Infinite Creativity

مكتبة إبداعية موحدة للوكلاء مع خادم MCP يقدمه المشروع. يتصفح الوكيل الأقسام والعناصر، يعرض المعاينات، يقرأ الكود وتبعياته، يفحص المجسمات والتحريك، ويحصل على الملفات الأصلية داخل MCP دون فتح صفحات الموردين. تشمل الويب والهاتف وسطح المكتب والألعاب والبيئات والشخصيات والخامات والأصوات والخطوط.

Unified creative library for AI agents. The database holds indexed records and file manifests; original content is retrieved on demand into a private, bounded cache. GitHub stores the software and release snapshots, avoiding asset binaries in Git history. The MCP server is provided by this project, without implying endorsement by GitHub or source providers.

**Exact coverage:** see `manifest.json` in the [latest catalog release](https://github.com/qwzx4893-stack/Infinite-Creativity/releases/tag/catalog-latest). Records can include variants and references; they are not estimated provider totals or unique artworks. This is an expanding library, not a completed million-item index of the entire Internet.

[Coverage of the originally requested sites](docs/REQUESTED_SOURCE_COVERAGE.md) distinguishes actual indexed items from source registration and unavailable integrations. `library_overview` reports usable counts by medium and a separate total excluding icons. Unrestricted recommendations sample each medium independently and cap both source and medium concentration.

## Install and restore

Python 3.11+ and SQLite FTS5 are required.

```bash
git clone https://github.com/qwzx4893-stack/Infinite-Creativity.git
cd Infinite-Creativity
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Download `catalog.sqlite.gz` and `manifest.json` from the same release into `snapshots/`, then:

```bash
python scripts/verify_snapshot.py snapshots
infinite-creativity stats
infinite-creativity-mcp
```

SHA256 verification detects damaged or inconsistent snapshots; it does not independently authenticate their publisher. Close active servers before replacing their database. Alternatively, `infinite-creativity sync` builds the approved inventories directly. Public source APIs have their own availability and rate limits.

## Connect an MCP host

Use absolute paths in your host's stdio configuration:

```json
{
  "mcpServers": {
    "infinite-creativity": {
      "command": "/absolute/path/Infinite-Creativity/.venv/bin/python",
      "args": ["-m", "infinite_creativity.server"],
      "env": {
        "IC_CATALOG_DB": "/absolute/path/Infinite-Creativity/state/catalog.sqlite"
      }
    }
  }
}
```

Windows: use `.venv\\Scripts\\python.exe` with JSON-escaped backslashes. No GitHub token is needed for local browsing. Some first-time GitHub requests benefit from an optional read-only `GITHUB_TOKEN` process environment variable. Never commit a token. This release provides local stdio, with no hosted public endpoint.

## Browse and use originals inside MCP

| Tools | In-library behavior |
| --- | --- |
| `library_overview`, `library_facets`, `browse_taxonomy` | Discover sections, real counts, styles, platforms and formats |
| `library_sections`, `library_packs`, `get_library_pack` | Precise section tree and actual thematic packs with indexed members |
| `open_library`, `library_page` | Browse the full matching inventory with private sessions and signed keyset cursors |
| `get_library_item` | Full record, features, provenance, license and permitted actions |
| `recommend_assets` | Diverse art-direction shortlist with explicit matching reasons |
| `preview_asset` | Native MCP raster image for eligible previews; SVG returned as original text |
| `preview_audio_asset` | Native MCP audio for licensed recordings up to 2 MiB |
| `asset_files` | Actual variants, file IDs, dependencies, formats and sizes |
| `read_asset_code`, `read_asset_dependency` | Original source text and verified declared relative dependencies |
| `inspect_3d_asset` | glTF/GLB meshes, materials, skins, animation names, triangles and external resources; ZIP inventory |
| `inspect_asset_media` | Original audio duration/channels, raster dimensions, Aseprite frame counts and LUT grid/color metadata |
| `fetch_asset`, `fetch_asset_bundle` | Originals, dependencies, preserved relative paths, checksums and attribution |
| `read_asset_file`, `read_archive_entry` | Bounded base64 chunks for clients without the server filesystem |
| `create_collection`, `add_to_collection`, `get_collection` | Private project shortlists excluded from public exports |
| `search_assets`, `browse_assets`, `get_asset`, `resolve_asset` | Compatibility metadata/search/link interface |
| `list_sources`, `catalog_stats` | Sources, review status, coverage and sync health |

Resources: `creativity://library`, `creativity://taxonomy`, `creativity://stats`, `creativity://section/{encoded_id}`, `creativity://pack/{id}`, `creativity://asset/{id}`, `creativity://asset/{id}/file/{file_id}`. Prompt: `creative_brief`.

Start with `library_overview`. Open, for example, `kind="model-3d", style="low-poly"`; continue using the returned session/cursor, inspect an item, preview where available, select variants with `asset_files`, then retrieve or inspect those file IDs. Component users can read source and declared imports before assembling a bundle. See [agent usage](docs/AGENT_USAGE.md).

## Agent navigation in v0.3

This is an MCP library, with no human frontend. The controlled hierarchy has 62 primary leaves for interfaces, animation, editing, 3D, 2D, surfaces, lighting, audio, typography, visual studies and discovery. An item occupies one primary leaf. Parent counts roll up descendants; artistic styles, platforms, formats, licenses and pack membership remain independent filters. Empty sections are hidden by default and can be inspected explicitly.

`library_sections(parent="three-d")` expands the tree. `library_packs(section="three-d", style="cartoon")` lists real themed packs. `get_library_pack` opens actual members; `open_library(section="three-d/characters", pack="...")` combines precise placement and pack membership. Source directories and unreviewed repositories are excluded from pack browsing. Inspiration is a separate reference view with native public presentation thumbnails, attribution and no original-file actions.

New ingestion covers individually licensed FSD50K audio, creator-linked public Quaternius Drive distributions, large scoped CC0 2D/game pack archives, Duelyst pixel animation/effects/audio, and per-card official Blender demos. Public Drive listings that may be paginated are withheld; paid Pro/source files are never taken. Truncated Git trees are walked through their subtrees before reconciliation. Read `list_sources` coverage and the release manifest for actual records and supported subsets.

Codrops public MIT repositories contribute actual code packs with original files, shaders, relative paths and license notices. Vendor libraries, fonts and demo media are excluded from that software-license scope; records expose remaining setup requirements. Mapcn contributes selected original map/analytics components; default CARTO tiles have separate service rights and are not included.

## Curation and image review

Exact duplicates require compatible rights and matching upstream cryptographic hashes for the entire indexed original/dependency bundle. Names, CRC32, visual similarity and a matching main mesh alone are insufficient. Duplicate aliases and quarantined items are omitted from all browse/search/facet paths. Small icons, pixel art, low-poly models and minimal design are retained. Technical quality and aesthetic quality are distinct; no invented quality score is assigned.

```bash
python -m pip install -e '.[vision]'
infinite-creativity prepare-vision
infinite-creativity curate
infinite-creativity screen-vision --limit 500
```

The optional pinned ONNX classifier runs locally, verifies its hashes, screens raster images and multiple crops, and quarantines both suggestive and uncertain results. Evidence records image/model hashes, class probabilities, threshold and whether the image was an original raster or a preview. New upstream revisions invalidate old verdicts. Six-hour updates continue image-review batches; the manifest reports actual coverage and pending items. This is probabilistic screening: it does not certify unseen 3D surfaces, unsampled animation frames, speech or contextual innuendo. Aesthetic filtering of the full collection is not complete.

Editing inventories also include licensed creative grading, camera/display transforms and color-accessibility LUT packs. Their records preserve input/output gamut, transfer functions, inference confidence, conversion warnings and upstream notices. Only audited collections with confirmed current licenses qualify; third-party caveat collections and unclear calibration images are excluded.

Cards expose internal resource URIs and actions. External URLs remain provenance; browsing and file retrieval do not require visiting them. Individual Kenney originals are read from verified free ZIPs with HTTP ranges, avoiding a whole-pack download for one mesh, sprite or sound. SHA256 deduplicates fetched bytes. Downloaded files remain untrusted and are never executed.

## Coverage and access rules

Public inventories: Poly Haven, ambientCG, eligible Iconify collections and public Open Robotics Fuel models, including Google Research scanned household objects. Scoped software/font repositories provide web, mobile and desktop components. Explicit CC0-scoped KayKit/Kenney repositories provide characters, rigs, models and dependencies. Kenney's connector traverses the official free pack list and verifies CC0 archive dedications; legacy packs require an explicit CC0 declaration on the creator's official pack page. Package previews and paid All-in-1 downloads are excluded. Khronos glTF models use individual component legal metadata, with restrictive or unknown component rights kept reference-only.

[The source registry](src/infinite_creativity/data/sources.json) includes supplied sites, additional providers, curated repositories and 272 specialized discovery queries. New GitHub discoveries remain repository-level references until their item inventories, rights and content are reviewed. Registration does not mean a source's entire content is indexed. The supplied `blendkit.com` address remains distinct from `blenderkit.com`.

`usable` requires an allowlisted license, evidence and admitted metadata state. `reference` includes paid, unknown, restrictive or unreviewed content. Every content tool rejects reference-only downloads. Paid references provide public provenance and high-level design inspiration; paid images, templates and prompts are not mirrored or used as training data. A zero price is not license evidence. Attribution and upstream notices remain applicable.

Sexual, pornographic and obscene material is excluded by admission policy and text screening. **Metadata screening is not visual certification.** No blanket visual-safety guarantee is claimed. General community discoveries remain reference-only. See [content policy](docs/CONTENT_POLICY.md).

Art-direction matching uses metadata/style inference and limited Arabic synonyms, with no image embeddings. Not every model includes a preview, rig or animation; inspection reports actual glTF data. Blender/FBX/USD can be fetched but need separate native parsers for deeper inspection. Files above the configurable 512 MiB ceiling remain visible but cannot be retrieved by these tools. The server needs upstream connectivity for uncached files; cached originals and the local record index can be read offline.

## Refresh and development

GitHub Actions refreshes every six hours and publishes verified SQLite/JSONL snapshots with file manifests. Conditional metadata caches, rotating search budgets and persistent date-partitioned discovery avoid repeatedly scanning every query. Complete successful source inventories reconcile removals; failures preserve prior records and prevent publishing an incomplete refresh. Platform schedules may be delayed.

```bash
infinite-creativity sync --adapters github-assets fuel kenney-packs
infinite-creativity sync --adapters discovery --discovery-pages 3
python -m unittest discover -s tests -v
infinite-creativity export --out snapshots
```

[Architecture](docs/ARCHITECTURE.md) · [Contributing](CONTRIBUTING.md) · [Expansion work](docs/ROADMAP.md)

Powered by [Poly Haven](https://polyhaven.com/). This software is MIT licensed; originals retain their own licenses. Credit creators and providers.
