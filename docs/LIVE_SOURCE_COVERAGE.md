# Live source coverage — v0.5

This describes connector capabilities, not stored item inventories or whole-provider completion. Every item query obtains current upstream data. Counts from v0.3 snapshots are historical and are not used by the default MCP.

| Original requested source | Current live behavior |
| --- | --- |
| Poly Haven | Current complete public metadata response; original variants and previews on demand |
| Uiverse | Current scoped original HTML from the official galaxy repository, with MIT notice |
| Motion Primitives | Current scoped core/UI code and original notices |
| Codrops | Current public MIT organization windows and selected original code/shader pack members; vendor media/fonts excluded |
| Mapcn | Current original registry code; map tile services retain independent terms |
| Blendkit / BlenderKit | Unified official free-asset API. CC0 or conditional royalty-free end-product rights; original descriptors use official scene UUID parameters and current account access limits |
| MockupBro | Current public mockup presentation entries and native eligible thumbnails; raw creator files are not assumed stock-redistributable |
| NameThatUI | Current public pattern entries; visual reference only |
| Refero | Current public style entries; visual reference only |
| Awwwards | Current public showcase entries; visual reference only |
| Jiro | Current public template/component presentation entries; original copying requires verified rights |
| Oron | Current public library entry presentations; original copying requires verified rights |
| Prompt Motion | Current public item presentations; paid/protected full prompts are not exposed as reusable originals |
| Jitter | Current public template presentations; native preview where the permitted presentation transport is supported |
| Screenrove | Current public product-reference pages; visual reference only |
| Aceternity | Current public free registry metadata. Applicable free original-source redistribution scope unresolved; no blanket MIT assumption |
| MotionSites | First-party MCP metadata through authorized account OAuth. Local access token configuration required; no copying of paid full prompts |
| 21st.dev | Official account MCP metadata connector using `API_KEY_21ST`; no marketplace scraper, hosted generation or unverified premium code copying |
| CGTrader | Official developer API for free-price presentations, requiring `CGTRADER_TOKEN`. Current royalty-free/custom original scope remains unresolved; originals withheld |
| Dribbble | Official API v2 using `DRIBBBLE_TOKEN`; authorized account shots only, not the whole public gallery |
| Magnific | Supplied app endpoint rejected public access (HTTP 403); no public original-asset inventory established |
| String Tune | Current official `@fiddle-digital/string-tune` package, verified MIT notice and bounded original JS/CJS/MJS members, read inside MCP |
| SiteReel | Public page did not expose supported item permalinks; dynamic inventory not integrated |

Additional current connectors cover ambientCG, scoped CC0 game/2D/3D repositories, Kenney original ranged ZIP members, supported creator-linked Quaternius Drive folders, Fuel, individually licensed FSD50K recordings, official Blender demo subsets, audited LUT collections and optional Iconify queries.

Known repository connection addresses are retained as software routing configuration only. Search, licenses and item metadata are fetched anew; addresses are not proof of usable assets. The MCP can discover current repositories and open their scoped items without navigating websites.

Rights eligibility and original availability are separate. Upstream deletion, changed licenses, quotas, account restrictions and unsupported formats can affect the next call. Native public preview endpoints may themselves be unavailable or point to a general presentation image; this is never claimed as a full original download.

References: [official Blendkit licenses](https://www.blendkit.com/docs/licenses/), [MotionSites MCP/account limits](https://motionsites.ai/mcp), [21st terms](https://21st.dev/terms), [Aceternity licence](https://ui.aceternity.com/licence).

All rows describe connector scopes. Default v0.5 admission can withhold their items before display. The current Art Institute metadata API worked, but its original image host rejected our verification requests with HTTP 403; these images were withheld. Account connectors above have not been tested with authorized account keys in this workspace. [Admission limits](LIVE_ADMISSION.md) · [New connections](V05_CONNECTIONS.md).
