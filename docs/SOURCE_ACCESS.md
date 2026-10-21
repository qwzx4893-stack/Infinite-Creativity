# Professional UI/motion source access — v0.12

Research/implementation date: 2026-10-21, Asia/Baghdad.

## Access without a 21st key

`open_component_reference` treats a selected component reference as a locator and resolves an explicitly configured **original author**. For example:

```text
open_component_reference(reference="https://21st.dev/@kevingirelli/components/signature")
open_asset_package(asset_id=<returned item.id>)
```

The implementation does not request the marketplace page, scrape its catalog, retrieve its screenshots, use another account, forge credentials, or convert a marketplace denial into invented success. It reads Kevin Girelli's independently public [Corsair UI repository](https://github.com/KevinGirelli/corsair-ui), current MIT notice, author registry declarations and exact pinned original files/dependencies. The current Signature route delivered four scoped files including its notice in a real MCP test. Author rights are rechecked on selection and delivery.

An unknown author returns `independent-author-route-not-configured` with a `discover_sources` action. A known author whose item/rights change returns explicit unavailability. It never substitutes a lookalike and labels it the requested component.

## Implemented author registries

| Source ID | Original author | Access contract |
| --- | --- | --- |
| `registry:corsair` | [KevinGirelli/corsair-ui](https://github.com/KevinGirelli/corsair-ui) | Current MIT repository; UI/lib/hook registry indexes; files pinned to the current author commit; exact dependencies/notices |
| `registry:ui-layouts` | [ui-layouts/uilayouts](https://github.com/ui-layouts/uilayouts) | Public author registry and current MIT notice; configured publisher `www` redirect |
| `registry:uselayouts` | [iurvish/uselayouts](https://github.com/iurvish/uselayouts) | Public author registry, current MIT original source and scoped dependencies |
| `registry:agent-elements` | [21st-dev/agent-elements](https://github.com/21st-dev/agent-elements) | Independent MIT author registry, not the main marketplace |
| `registry:magicui` | [magicuidesign/magicui](https://github.com/magicuidesign/magicui) | Public MIT author registry; paid/private items excluded |
| `registry:shadcn` | [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | Official public MIT author components and scoped registry dependencies |

These are configuration scopes, not a claim that all items were downloaded, rendered, or approved. Live registry indexes are fetched per request and are not saved as an asset inventory. Six candidate components per page keep original inspection bounded. A component's code, dependencies, CSS/configuration and notices are useful evidence; they do not prove its rendered aesthetics, accessibility or motion performance.

## What the 21st research actually found

Context7's older registry description said `/api/r/{author}/{component}` served free components without authentication. Actual selected requests on 2026-10-21 for `kevingirelli/signature` and `shadcn/button` returned HTTP 403 `Authentication required`; the `/r/` route also returned 403. We did not call this anonymous marketplace integration.

The current [official MCP documentation](https://docs.21st.dev/mcp) describes authenticated search/retrieval. Its [terms](https://docs.21st.dev/terms) distinguish original author code from marketplace presentation/metadata and restrict automated marketplace collection and bypassing technical protections. An independent author license covers that author's original scope; it does not grant the marketplace's preview/curation rights. These source distinctions are enforced rather than inferred from a public page or zero price.

Animate UI was also investigated. Its current [license](https://github.com/imskyleen/animate-ui/blob/main/LICENSE.md) includes Commons Clause restrictions on redistribution of components. We do not label it unrestricted MIT or mirror its component collection. This does not remove professional motion support from the independent MIT sources above, Motion Primitives and other current configured author sources.

## Rate limits and failures

Anonymous GitHub metadata calls share the provider's public API limit. An existing optional `GITHUB_TOKEN` can improve capacity and is sent only to `api.github.com`; redirect hosts do not receive it. Selected real tests without a 21st key succeeded using the existing GitHub session to avoid an exhausted anonymous GitHub quota. The keyless author registry design remains usable anonymously while upstream capacity is available.

No credentials are logged, stored in source configuration or inherited by media decoders. No source reports `healthy` merely because it is configured. Use `probe_library_sources` for current bounded evidence; transient upstream failure and complete-provider coverage are separate questions.
