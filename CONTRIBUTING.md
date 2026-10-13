# Adding sources and adapters

Add provider metadata to `src/infinite_creativity/data/sources.json`. A mixed/paid/unknown provider starts with `adapter: reference`. Include canonical URL, media tags, access conditions and review status. Do not commit secrets or copyrighted premium material.

Reusable adapters require an approved API/export, complete pagination, bounded retries, rate limits, provider credit, per-item license evidence, source identity, canonical URLs and revisions. Never assume the repository's top-level software license automatically covers demo images, third-party fonts or models.

A GitHub tree adapter uses an explicit path pattern and rejects truncated trees. `license_scope_reviewed: true` is a maintainer assertion that the scoped content is covered by the item license; it is not an automatic guess. Keep this false for general discoveries.

Adapters must preserve previous snapshots on failure, reconcile removals only on complete success, and never import/execute upstream code. Add fixture tests for pagination, errors, permission rejection, unsafe content and license changes. Add end-to-end MCP coverage when changing tools.

Run `python -m unittest discover -s tests -v`. State actual indexed counts and all limits in changes; no invented million-item claims or blanket safety guarantees.
