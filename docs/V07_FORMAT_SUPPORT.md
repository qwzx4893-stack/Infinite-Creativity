# Selected original formats — v0.7

`review_asset_media` is a selected-file operation, not a background catalogue import. Pending candidates have no media/original access until they pass. It uses source-level current rights, original checksums/ZIP CRCs, scoped dependencies, automatic lexical/image/speech checks, technical validity and request-only staging. It returns a digest-bound locator and, when available, a screened native MCP image. No catalogue/index/original cache is saved.

| Format family | Implemented scope | Important exclusions |
|---|---|---|
| BLEND / FBX | Installed headless Blender with asset scripts disabled; mesh/material/bone/action metadata, all stored textures, GLB conversion and bounded animation poses | External linked libraries, missing/unlisted textures, audio/video sequencers, native simulation/volumes and changing mesh caches |
| USD / USDA / USDC / USDZ | Blender importer; mesh/materials, bounded transform caches baked to explicit keyframes before review | Time-varying geometry/cache/simulation; unsupported importer features; not every USD extension |
| BVH | Original motion plus generated bone proxies, skin pose/keyframe/midpoint review; original BVH delivered | Proxy skeleton views do not represent a full character surface or certify contextual meaning of motion |
| GLTF / GLB | Explicit licence-scoped relative BIN/image staging; embedded texture review; sparse accessors, morph weights, cubic interpolation and 8 skin influences | Remote/missing/unscoped dependencies, unsupported compression/texture codecs; unanimated morph combinations and occlusion are not exhaustively proved |
| OBJ / MTL | Scoped materials/textures; local conversion and geometry/views | Missing, ambiguous or undeclared materials/image dependencies |
| PLY / STL / OFF / 3MF | Trimesh-supported mesh representations and conversion to reviewed GLB | Unsupported nonmesh/extension data; no claim of full DCC editing-project semantics |
| DAE / Collada | Static supported meshes/materials; scoped images; no active XML declarations | Animated/skinned Collada/controller libraries require another reader |
| PSD / PSB | Stored composite and each decoded layer, including hidden layers; layer names/text; renderable text/vector layers and image smart objects | External or nested/non-image smart objects, unrenderable layers; psd-tools compositing is not identical to Photoshop |
| ORA | Every stored raster layer and composite, including hidden pixels; stack references must be present/decodable | Missing/unsupported layer payloads; no unsafe/external layer resolution |
| Raster / audio / video | Existing complete bounded review with higher selected limits; BMP/TIFF/DDS and PyAV audio/video codec families additionally routed | Unsupported codec, duration/frame/CPU cap, classifier uncertainty or invalid media |
| ZIP / split ZIP packs | Fresh bounded directory navigation and explicit member selection; selected member/dependencies reviewed internally | At most 10,000 directory members, 48 selected files, validated ranges/CRC; no whole large archive fallback when ranges are unavailable |

Ordinary browsing is still fast-budget review. Extended ceilings: 512 MiB total original bytes, 30 minutes audio, 18,000 decoded frames, two million triangles, 4,096 poses, 128 megapixels, 2,048 layers, five minutes processing. These are upper bounds; automatic review may fail earlier. Installed Blender/version/importer capabilities matter. `IC_BLENDER_PATH` chooses an existing executable; no automatic Blender download occurs.

MAX, C4D, Maya MB, AEP, PRPROJ, native Krita KRA tiles, VDB simulation, proprietary brush formats and Rive native animation are still not complete original-review formats. Registration of a filename never implies its native payload is usable. Static Alembic is conditionally routed through Blender, but time-varying geometry caches remain withheld. No claim of “all specialized formats” is made.

Whole geometry is processed, but safety views remain discrete. Automatic filtering can miss innuendo and can hold benign material. Technical validity is not artistic quality certification. Intentional minimal/low-poly/pixel styles remain eligible.
