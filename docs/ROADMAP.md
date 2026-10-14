# Million-scale expansion: remaining work

This repository is an operational first catalog, not a completed index of every free creative resource on the Internet. The manifest is the source of truth for current coverage.

1. Add provider-approved APIs/export adapters for model, illustration, sprite, animation, audio, video, mockup and template collections. Many registry providers are currently references only. An API key/account or express provider permission may be necessary.
2. Review item-level licenses and mixed content before promoting discovered repositories. Repository discovery is not complete asset extraction.
3. Implement visual moderation and durable exclusions with reviewed provenance; metadata keyword screening is insufficient for a zero-explicit-content guarantee.
4. Enrich items with machine-readable component roles, palette, density, lighting, material, framework/version compatibility, accessibility and motion behavior. Present confidence and inference provenance.
5. Add rights-cleared visual embeddings and reranking, separate from the current lexical recommendations. Paid reference content is not a training dataset.
6. Expand the implemented persistent topic/date partition queue to more topics and item inventories. Oversized date ranges split and resume across scheduled runs; a single day above 1,000 results currently needs additional qualifiers. Use distributed queues and checkpoints for larger provider inventories.
7. Benchmark millions of real records. Move facet indices and serving replicas into PostgreSQL/search services when measured SQLite costs justify it; add distributed connector workers and object storage without mirroring restricted assets.
8. Support trusted upstream webhooks, license changes, takedowns, content-hash deduplication when downloads are permitted, and source-level health/freshness SLAs.
9. Publish versioned package releases and optionally deploy an authenticated Streamable HTTP service. This initial delivery is clone/install + local stdio, not a public hosted service.

There is no fabricated inventory to reach a target number. Expansion must preserve licensing, provenance, content screening and truthful counts.
