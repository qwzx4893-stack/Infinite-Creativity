# Using the unified library

No provider page navigation is needed to browse indexed records or retrieve eligible content:

1. `library_overview()` reveals sections; `library_facets(kind="model-3d")` reveals styles and formats.
2. `open_library(kind="model-3d", style="low-poly", platform="game")` returns internal cards and a private session. Refine with query, format or source.
3. Continue `library_page(session_id=..., cursor=next_cursor)` until its cursor is null. Cursors are signed and session-bound; sessions expire after 24 hours. Reopen after a refresh, since updates can affect ordering.
4. `get_library_item` shows license evidence and features. `preview_asset` returns a native MCP image where a licensed raster preview exists, or SVG text. Missing preview does not mean missing asset content.
5. `asset_files(asset_id=..., format="glb")` lists file IDs. `inspect_3d_asset` reports real skins and animation data; do not infer a rig from a title.
6. `fetch_asset_bundle` retrieves the preferred main file, indexed dependencies and license files. Explicit `file_ids` change variants. Poly Haven selections bring included texture dependencies; other explicit selections must include desired dependency IDs.
7. Assemble files using returned `relative_path` values. `read_asset_file` delivers original base64 bytes for remote clients; `fetch_asset` returns cache locations for local clients. No retrieved files are executed.
8. Save IDs through `create_collection`, `add_to_collection` and `get_collection`. Collections, filters, cursor secrets and downloaded bytes never enter public snapshots.

For components, `read_asset_code` provides line windows and imports. `read_asset_dependency(import_specifier=...)` accepts declared relative dependencies in reviewed repositories, checking coherence against the indexed revision. External packages return identity without installation. Alias resolution supports package-root `@/` and `~/`, not arbitrary bundler configurations.

Kenney file IDs refer to individual ZIP members. HTTPS ranges retrieve central-directory metadata and the selected member. Indexed CRC32 is verified; retrieved bytes receive a SHA256 digest. This does not independently authenticate the whole archive. Generic Fuel ZIPs expose an inventory via `inspect_3d_asset`; `read_archive_entry` reads members without extraction.

Budgets: pages up to 100 records, source up to 400 lines/40,000 characters, binary chunks up to 1 MiB, inline file resources and raster previews up to 2 MiB, bundles up to 100 files and 512 MiB total. GLB/glTF inspection is limited to 64 MiB. Style suggestions use lexical inference. References cannot be fetched, previewed or copied by content tools.
