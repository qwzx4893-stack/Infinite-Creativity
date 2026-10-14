# Infinite Creativity

مكتبة إبداعية موحدة عبر MCP محلي يتصل بالمصادر مباشرة. تُجلب بيانات العناصر عند كل طلب، وتبقى الأصول عند مصادرها. لا يحتاج النموذج الافتراضي إلى قاعدة بيانات أو فهرس عناصر أو نسخة catalog أو كاش بيانات محلي.

Local, live federated MCP for creative assets. Every item operation requests current upstream metadata. Source connection addresses and the controlled taxonomy are configuration; asset records, file manifests and search results are not retained between calls. Original bytes are fetched only when requested. Parser/preview temporary files are deleted before the response completes.

## Install

Python 3.11+:

```bash
git clone https://github.com/qwzx4893-stack/Infinite-Creativity.git
cd Infinite-Creativity
python -m venv .venv
# PowerShell: .\.venv\Scripts\Activate.ps1
# Unix: source .venv/bin/activate
python -m pip install -e .
infinite-creativity-mcp
```

No sync, catalog download, restore or export step is required.

## Connect a local MCP host

```json
{
  "mcpServers": {
    "infinite-creativity": {
      "command": "/absolute/path/Infinite-Creativity/.venv/bin/python",
      "args": ["-m", "infinite_creativity.server"]
    }
  }
}
```

Windows: use the absolute `.venv\Scripts\python.exe` path, escaping backslashes in JSON. Optional `GITHUB_TOKEN` in the process environment increases GitHub API capacity. The program is local stdio; upstream requests are HTTPS. No hosted endpoint or human frontend is provided.

## Agent workflow

1. `library_overview`, `library_sections`, `list_sources`: exact categories and actual connector capabilities. Counts are unknown without querying providers.
2. `open_library(source="polyhaven", kind="model-3d", query="chair")`: current source data, normalized internal cards and live cursors.
3. `library_page(cursor=next_cursor)`: refresh the next source window. Cursors contain filters and positions, never cached result sets.
4. `get_library_item`, `asset_files`: revalidate current metadata, rights and original variants.
5. `preview_asset`, `preview_audio_asset`, `read_asset_code`, `inspect_3d_asset`, `inspect_asset_media`: consume selected content inside MCP.
6. `read_asset_file`, `fetch_asset`, `fetch_asset_bundle`, `read_archive_entry`: selected original bytes. Inline files/bundles are bounded to 2 MiB; larger originals use verified HTTP range windows where supported.

`library_packs` and `get_library_pack` navigate current themed pack membership. `discover_sources` and `open_repository` discover and inspect public repositories online without a saved search index. Known repository addresses remain configuration only; they are queried when selected, rather than issuing tens of thousands of requests for a single library page.

Reference views use `mode="reference"` or `mode="all"`: public presentations can have native previews, while paid or unverified original source files remain inaccessible. A free price is not a reuse license. Blendkit royalty-free records allow end-product use under their own restrictions; raw asset redistribution or asset-pack mirroring is not permitted.

## Current source scope

Live adapters cover Poly Haven, ambientCG, scoped UI/software and CC0 media repositories, Uiverse, Motion Primitives, Mapcn, Codrops code packs, official Blendkit free-asset APIs, Kenney original ZIP members, supported creator-linked Quaternius public Drive folders, Fuel, per-clip FSD50K audio, official Blender demo subsets, licensed LUT collections and optional Iconify queries.

Public presentation item windows are available for MockupBro, NameThatUI, Refero, Awwwards, Jiro, Oron, Prompt Motion, Jitter and Screenrove. Aceternity's public free registry is browsable as reference metadata while its applicable free-item redistribution scope remains unresolved. These are not claims of reusable originals or complete whole-site coverage.

MotionSites metadata can be federated through its [official account-authorized MCP](https://motionsites.ai/mcp), using an authorized `IC_MOTIONSITES_TOKEN` process environment variable. OAuth acquisition is not automated by this project. Full paid prompts are never copied. Provider notices and account access limits are preserved.

Some sources need authorization, reject requests or expose no supported public inventory. They return explicit limitations, with no stored snapshot fallback or protection bypass. [Live coverage and limitations](docs/LIVE_SOURCE_COVERAGE.md) distinguish original access, reference previews, conditional connections and unavailable sources.

## Freshness and limits

Provider changes can alter results between pages. Item/file locators bind current source identities and revisions; stale file selections require a fresh manifest. Signed cursors expire after 24 hours and after server restart. Metadata, HTTP responses and decoded audio/model/image bytes are discarded after the request; software configuration and source addresses remain.

There are no global million-item counts, saved global duplicate decisions, persisted collections or blanket quality/visual-safety verdicts. Current metadata is screened for explicit/suggestive terms. Unseen 3D surfaces, animation frames, speech and contextual innuendo are not certified. Intentional minimal, pixel and low-poly styles are not rejected as bad quality. Model formats can be grouped as one record inside a pack; this is not global aesthetic deduplication.

Live access depends on provider latency, quotas and rights. Full metadata distributions such as FSD50K can take longer because this model deliberately retains no local copy. A provider may have its own CDN cache; this server makes fresh requests and does not silently substitute old records.

## Development

```bash
python -m unittest discover -s tests -v
infinite-creativity stats
infinite-creativity search chair --source polyhaven --kind model-3d
```

The historical indexed implementation requires explicit `IC_MODE=legacy-indexed` and an explicit maintenance database. It is retained only for compatibility and is not the default library. Old v0.3 catalog counts and review reports describe that archived approach, not live v0.4 inventories.

The six-hour snapshot publisher has been retired. Every live query observes its source directly; no automated asset-index exports are produced.

[Architecture](docs/ARCHITECTURE.md) · [Agent usage](docs/AGENT_USAGE.md) · [Content policy](docs/CONTENT_POLICY.md)

Software is MIT licensed. Original assets retain their own licenses. The MCP is provided by this project; no endorsement by GitHub or source providers is implied. Powered by [Poly Haven](https://polyhaven.com/).
