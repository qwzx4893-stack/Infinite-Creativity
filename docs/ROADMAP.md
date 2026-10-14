# Million-scale expansion: remaining work

This repository is an operational first catalog, not a completed index of every free creative resource on the Internet. The manifest is the source of truth for current coverage.

1. Extend the implemented Kenney/KayKit/Fuel model, sprite, character, animation, audio and UI inventories with further provider-approved exports for film/VFX, volumes, motion capture, video, mockups and templates. Many registered providers remain references; account/API permission may be necessary.
2. Review item-level licenses and mixed content before promoting discovered repositories. Repository discovery is not complete asset extraction.
3. Implement visual moderation and durable exclusions with reviewed provenance; metadata keyword screening is insufficient for a zero-explicit-content guarantee.
4. Enrich items with machine-readable component roles, palette, density, lighting, material, framework/version compatibility, accessibility and motion behavior. Present confidence and inference provenance.
5. Add rights-cleared visual embeddings and reranking, separate from the current lexical recommendations. Paid reference content is not a training dataset.
6. Expand the implemented persistent topic/date partition queue to more topics and item inventories. Oversized date ranges split and resume across scheduled runs; a single day above 1,000 results currently needs additional qualifiers. Use distributed queues and checkpoints for larger provider inventories.
7. Benchmark millions of real records. Move facet indices and serving replicas into PostgreSQL/search services when measured SQLite costs justify it; add distributed connector workers and object storage without mirroring restricted assets.
8. Support trusted upstream webhooks, license changes, takedowns, content-hash deduplication when downloads are permitted, and source-level health/freshness SLAs.
9. Publish versioned packages and optionally deploy authenticated Streamable HTTP. Current delivery is clone/install + local stdio with native content/resources. Add optional MCP Apps viewers for interactive 3D rendering where a host supports them.

There is no fabricated inventory to reach a target number. Expansion must preserve licensing, provenance, content screening and truthful counts.
