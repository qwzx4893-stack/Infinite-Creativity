# Admission and reference policy

The catalog intentionally excludes pornography, sexual imagery, nudity, fetish assets, obscene gestures and explicit language. Never bypass authentication, access controls, paywalls, robots/terms restrictions or provider API limits.

Current enforcement:

1. Approved public inventories, scoped repositories and official free archives with explicit license evidence.
2. English/Arabic explicit-term screening over titles and tags; path and description screening for repository discovery.
3. Unknown licenses, unreviewed general repositories and mixed commercial sources remain reference-only.
4. All content tools reject references, inactive records and missing license evidence.
5. Eligible originals and previews are retrieved only on request into a bounded private cache; SVG/source text is never executed. Credentials are never sent to asset hosts. HTTPS host/DNS checks, byte budgets, hashes, archive path and decompression limits constrain retrieval.

`metadata-screened` means only that textual admission checks passed. It must not be interpreted as human or machine visual approval. Visual assets may contain content not mentioned in metadata; an automated text filter cannot guarantee the user's visual-content requirements. General mixed-content sources must receive item-level visual review before any reusable adapter is enabled.

The initial icon providers and curated texture/model sources are ordinary creative-resource providers, not guaranteed sanitized collections. A production deployment requiring a strict zero-exposure rule should keep visual access behind a separate visual moderation/human approval system. This system is outstanding; no fake moderation verdicts are generated here.

Paid/reference sources are public URL references only. A reference grants no right to download, reproduce, clone protected artwork, redistribute premium prompts, or train on content. Agents may inspect permitted public pages through their own authorized tools and describe general artistic principles. The catalog does not perform model training.

Report an unwanted or incorrectly licensed entry in a repository issue with its catalog ID and canonical URL. Do not attach the offensive imagery or credentials. A maintainer must add the URL or source ID to `src/infinite_creativity/data/exclusions.json`, resync and republish a snapshot. Exclusions suppress reingestion and resolver access, and resync deactivates existing blocked records. Restart a running MCP server after policy changes. Remote source code is untrusted and must be inspected before execution.
