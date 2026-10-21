# Infinite Creativity

مكتبة إبداعية موحدة للوكيل عبر MCP محلي: يبحث في المصادر الأصلية، يفرز المرشحين، يعاين الوسائط ويستلم الملفات واعتمادياتها وتراخيصها داخل MCP. البيانات والأصول تُجلب عند الطلب؛ لا فهرس أصول دائم ولا مخزون صور أو ملفات أو embeddings محفوظ.

Local stdio MCP with live provider federation, progressive type-specific curation, current rights, exact original delivery, and resource-limited local media readers.

## v0.12 — useful originals, professional UI/motion routes, bounded execution

- **44 MCP tools**, **405 configured connections / 338 default query scopes**, 12 root families and 83 exclusive leaves. Configuration counts are not healthy-source or approved-asset counts.
- Browsing automatically excludes demonstrably empty/invalid originals and duplicate identities. Complete source syntax and original-media evidence determine useful technical candidates. Unverified candidates remain in `quality_queue`; large/native unreviewed originals remain in `review_queue`. No universal professional-quality score is invented.
- **Corsair UI, UI Layouts and useLayouts** join Agent Elements, Magic UI and shadcn author registries. Original source, scoped dependencies and current MIT notices arrive inside MCP. UI code is parsed, never installed or executed.
- **`open_component_reference`** resolves a supported selected 21st component reference to its independently public original-author repository. Signature is delivered through Kevin Girelli's Corsair source, without a 21st key. This is original-author access, not anonymous marketplace access or a copy of its catalog/previews. See [source access](docs/SOURCE_ACCESS.md).
- Server-wide admission, cooperative cancellation, aggregate request budgets, request-local host approvals, DNS-pinned public HTTPS, and media worker memory/CPU/deadline limits.
- Signed chunk digests permit exact verified original ranges after a complete selected-file review. Encoded/archive members and incompatible range representations use complete-file verification; current rights are always rechecked.
- Pillow 13+, hash-pinned dependency locks, local readiness diagnostics and cross-platform CI. See [contracts and limitations](docs/PRODUCTION_HARDENING.md).

## Install

Python 3.11+. The committed `uv.lock` resolves all optional dependencies across supported Python/platform markers:

```bash
git clone https://github.com/qwzx4893-stack/Infinite-Creativity.git
cd Infinite-Creativity
uv sync --frozen --all-extras
uv run infinite-creativity doctor
uv run infinite-creativity prepare-live-vision
uv run infinite-creativity prepare-live-media
uv run infinite-creativity prepare-live-style
uv run infinite-creativity-mcp
```

Alternatively create a virtual environment, install the exported hashed dependencies, then the project without resolving them again:

```bash
python -m venv .venv
# Activate .venv, then:
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps .
infinite-creativity doctor
```

The three preparation commands install approximately 617 MiB of pinned, hash-verified **model software**, not asset collections. They are explicit; starting MCP never downloads models, Blender or originals automatically. Missing media software leaves uncertain originals withheld. Software/source browsing can work without model preparation. `doctor --verify-models` checks installed software hashes without fetching assets.

SVG rendering also requires a discoverable native Cairo library (`libcairo2` on Linux; an installed `libcairo-2.dll` on Windows). On Windows set `CAIROCFFI_DLL_DIRECTORIES` to its folder and put that folder on `PATH` so transitive DLLs are found. `doctor` reports native SVG readiness; `python scripts/verify_svg_renderer.py` actually renders a small generated SVG. Native BLEND/FBX/USD/BVH inspection uses an existing Blender installation; optionally set `IC_BLENDER_PATH`. Local model paths may be selected through `IC_VISION_MODEL`, `IC_SPEECH_MODEL`, `IC_STYLE_MODEL`.

Configure your MCP client with the absolute virtual-environment Python path:

```json
{"mcpServers":{"infinite-creativity":{"command":"/absolute/path/Infinite-Creativity/.venv/bin/python","args":["-m","infinite_creativity.server"]}}}
```

On Windows use `.venv\\Scripts\\python.exe` with escaped backslashes. Sources do not require provider API keys. An existing optional `GITHUB_TOKEN` increases GitHub's public API capacity; anonymous upstream rate limits remain explicit. No 21st key is required for the original-author routes implemented here.

## Agent workflow

1. `library_diagnostics` → `library_overview` → `library_sections` → `section_sources`.
2. `open_library` returns selected useful candidates, `quality_queue`, `review_queue`, source failures and signed continuation cursors. Continue `library_page` even after an empty selected page when `next_cursor` exists. Curation is applied to fresh pages, not a saved inventory.
3. `curation_policy` explains exclusions and coverage. `curate_library` adds an explicit photographic threshold; by default its stricter visual-score requirement keeps unrendered UI and other unscored domains in `quality_queue`. `require_visual_score=false` exposes technically admitted candidates with unverified appearance clearly labeled.
4. `get_library_item` / `asset_files` / `preview_asset` / `preview_audio_asset` / `inspect_3d_asset` inspect the current selection. `library_packs` and `get_library_pack` navigate actual thematic members.
5. Prefer **`open_asset_package`**: current rights, complete selected original/dependency review, scoped manifest/notices, supported native preview and initial exact original bytes in one RPC. Continue `read_asset_file` with the returned reviewed `asset_id`; chunk proofs are signed and require no server-side original cache.
6. For a selected supported reference: `open_component_reference(reference="https://21st.dev/@kevingirelli/components/signature")`, then `open_asset_package`. Unconfigured authors return an explicit unresolved route and a discovery action.
7. `build_creative_kit` combines up to six typed needs; `assess_asset_fit` separates compatibility and unknowns; `review_library_board` supplies a temporary numbered comparison image. `rank_library_items` scores fresh preview relevance through local CLIP; it does not certify beauty or safety.
8. `candidate_asset_files` / `open_asset_archive` / `review_asset_media` handle selected large/native originals. Pending metadata grants no original access until review. Exact rights, digest and dependency scope are revalidated on later calls.
9. `probe_library_sources` reports current bounded sample evidence, not full-provider approval. `discover_sources` / `open_repository` find new independent public sources whose own rights must be checked.

## Scope and practical limits

Sources include professional UI/motion author projects, Codrops, Poly Haven, ambientCG, creator-scoped game packs, OpenGameArt, Lazytextures, Openverse, Wikimedia, Met, Cleveland, Incompetech, selected Internet Archive originals, PD3M, curated Objaverse, public instrument packs and other typed sources. Every item still requires current rights and supported original access; publisher totals are not admitted unique counts.

Large-catalog filters cover the current PD3M window or Objaverse partition. `browse_asset_catalog` can jump to large offsets; no full global million-item search is claimed when the provider does not supply one. No exhaustive upstream-original scan is performed merely by installing this server.

Content screening, technical validity, source syntax, relative visual relevance and photographic aesthetic estimates are separate evidence. Automatic classifiers can be wrong. Minimal/pixel/low-poly work is retained. Distinct material/pose/ICC variants are not dropped merely because they look similar. Duplicate receipts are bounded hashes in client cursors, not a global permanent uniqueness index. Model-based aesthetic scores are not validated universal UI/3D/audio craft judgments.

Selected media ceilings remain 512 MiB total source bytes, 30 minutes audio, 18,000 decoded frames, two million triangles and 4,096 poses. Workers have a 3 GiB resource cap, a hard parent deadline and minimal environment; supported OS limits are applied before decoding. Python networking is disabled inside them. **This is not an OS filesystem sandbox or a universal native-parser security guarantee.** Unsupported layers/rigs/simulations/codecs remain withheld. See [format coverage](docs/V07_FORMAT_SUPPORT.md) and [hardening contracts](docs/PRODUCTION_HARDENING.md).

The optional [WebMCP host adapter](docs/WEBMCP.md) forwards completed read tools to an embedding host. No human frontend, hosted service, publishing tool or automatic source execution is created.

## Verify

```bash
uv run --frozen --all-extras python -m unittest discover -s tests -v
node tests/webmcp.test.mjs
uv run infinite-creativity doctor --verify-models
# Explicit online samples; no originals survive the test:
uv run python scripts/verify_live_workflows.py --case corsair --case ui-layouts --case uselayouts
# Generated fixtures, real installed models and optional existing Blender:
uv run python scripts/verify_local_media.py
```

Historical feature/verification documents remain under `docs/`; their old counts describe their recorded versions. Current contracts are documented above and in the v0.12 hardening/source-access documents. External assets retain their original licenses; this repository's MIT license covers its software.
