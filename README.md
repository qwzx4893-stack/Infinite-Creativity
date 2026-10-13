# Infinite Creativity

مكتبة إبداعية اتحادية مخصصة للوكلاء: فهرس قابل للبحث وروابط للأصول الأصلية، مع خادم MCP يقدمه هذا المشروع. تشمل أيقونات وخطوطًا وعناصر واجهات وحركة وخامات ومواد وHDRIs ومجسمات وقوالب ومراجع فنية للويب والهاتف وسطح المكتب.

**الأعداد الفعلية** موجودة في [إصدار الفهرس](https://github.com/qwzx4893-stack/Infinite-Creativity/releases/tag/catalog-latest) داخل `manifest.json`. لا يعني إدراج موقع أن جميع عناصره مفهرسة، ولا تُحسب أعداد يعلنها المورد كعناصر جُمعت بالفعل. المشروع لا يدعي أنه وصل إلى ملايين العناصر.

Federated creative metadata for AI agents. Search, browse every indexed record, inspect upstream licensing, obtain original asset links, and build a diverse shortlist from an artistic brief. Asset binaries stay upstream. The project provides its own MCP server; this does not imply endorsement by GitHub, MCP maintainers, or the source providers.

## Quick start

Python 3.11+ and SQLite with FTS5 are required.

```bash
git clone https://github.com/qwzx4893-stack/Infinite-Creativity.git
cd Infinite-Creativity
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e .
infinite-creativity sync
infinite-creativity stats
infinite-creativity search "wood" --kind model-3d
infinite-creativity search --kind icon --style outline --limit 10
infinite-creativity-mcp
```

`sync` indexes approved public metadata adapters; it never executes remote code or downloads original asset binaries. To enable GitHub discovery, set a read-only `GITHUB_TOKEN` in your process environment and run:

```bash
infinite-creativity sync --adapters discovery --discovery-pages 3
```

No token is required for the MCP server's local search. Never paste a token into a repository, configuration committed to Git, a URL, or an issue.

## Restore the published index

Download `catalog.sqlite.gz` and `manifest.json` from the same catalog release into `snapshots/`, then:

```bash
python scripts/verify_snapshot.py snapshots
infinite-creativity stats
```

The manifest provides SHA-256 checksums. This detects inconsistent or damaged files; it is not independent proof that a publisher is trustworthy.

## Connect an MCP host

Use your MCP host's stdio server configuration. Replace both paths with absolute paths to your installation and database:

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

On Windows use the absolute `.venv\\Scripts\\python.exe` path and JSON-escaped backslashes. The packaged executable `infinite-creativity-mcp` also works in any host supporting stdio. The server runs locally; this repository does not provide a hosted public MCP endpoint.

| Tool | Purpose |
| --- | --- |
| `search_assets` | Search text, kind, inferred style, platform, source, license and access mode with bounded pages |
| `browse_assets` | Traverse the entire indexed catalog with a keyset cursor |
| `get_asset` | Inspect provenance, license evidence, revision and reuse eligibility |
| `resolve_asset` | Return upstream file/manifest links; reject reference-only items |
| `recommend_assets` | Produce a diverse shortlist with explicit metadata matching reasons |
| `list_sources` | Browse providers and discovered repositories with review/adapter status |
| `catalog_stats` | Report real active counts and recent source failures |
| `browse_taxonomy` | Discover media categories, platforms and artistic facets |

Resources: `creativity://taxonomy`, `creativity://stats`. Prompt: `creative_brief`.

Use `count_total: false` for faster shortlist searches that do not need an exact total. Use `browse_assets` cursors to enumerate large inventories without increasing offset costs.

## Coverage and access rules

Implemented full-list metadata adapters: Poly Haven, ambientCG and eligible Iconify collections. Iconify uses its official GitHub JSON exports; these may contain vector definitions during ingestion, but the catalog and release snapshots store names and licensing metadata only. Scoped GitHub tree adapters enumerate the configured code/font/example paths in the curated registry. Discovery finds repositories and indexes repository-level references; it does **not** silently treat an entire repository license as permission for all media inside it.

[Source registry](src/infinite_creativity/data/sources.json) includes all supplied links plus additional providers and open-source repositories. The supplied `blendkit.com` URL is kept as an unverified reference, separately from `blenderkit.com`. Reference sites are link-only until an approved API/export and item-level rights review are available. Paid designs, screenshots, prompts and asset files are not mirrored. Visual references mean public links and high-level principles, not training-data acquisition or access to paid content.

`usable` requires an allowlisted license, license evidence and an admitted metadata safety state. `reference` includes paid, unknown, restrictive or unreviewed content. The resolver enforces this distinction. A free price alone is never license evidence. Even permissive licenses can require notices, attribution, share-alike obligations or separate trademark permission; read the actual upstream license.

No pornography, sexual material or obscene content is intentionally admitted. Text screening rejects explicit terms. **Text screening is not visual moderation**: the initial connectors use curated providers and ordinary metadata, but visual safety is not guaranteed. General community discoveries are reference-only. Previews are not automatically fetched. See [content policy](docs/CONTENT_POLICY.md) for the remaining moderation work and how to report an entry.

Style recommendations are lexical metadata inference, with limited Arabic query synonyms. They are not image embeddings, full Arabic semantic search, or a claim that an asset visually matches every aspect of a brief.

## Updates and development

GitHub Actions schedules metadata refreshes every six hours. Conditional HTTP requests reuse cached responses, unchanged items skip reindexing, and a budgeted oldest-first sweep revisits discovered repositories. Source failures preserve previous records, and removal is applied only after a complete successful source snapshot. Release snapshots contain the database, metadata JSONL and counts/checksums, avoiding large binary files in Git history. GitHub schedules can be delayed or disabled by platform limits.

```bash
python -m unittest discover -s tests -v
infinite-creativity export --out snapshots
```

[Architecture](docs/ARCHITECTURE.md) · [Connector contributions](CONTRIBUTING.md) · [Scaling and outstanding work](docs/ROADMAP.md)

Powered by [Poly Haven](https://polyhaven.com/). Original assets retain their original licenses. This software is MIT licensed; that license does not relicense provider assets or metadata.
