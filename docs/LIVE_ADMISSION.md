# Admission before display — v0.5

Every live page runs admission before emitting cards. It checks current title, description, tags, source keys and filenames for explicit/obscene/suggestive content. Original source-text delivery checks the actual current text as well. Paid and unverified source files remain unavailable; visual references are a separate access scope.

The default `IC_SAFETY_MODE=strict` screens eligible raster images with the pinned Apache-2.0 ONNX five-class model. Safe-looking titles are insufficient. Risk or uncertainty above the conservative threshold is withheld. Missing model software, unsupported vectors, malformed/oversized images and unavailable previews are withheld, with counts/reasons in the page response. Full original rasters are used where available within the review budget; selected original ZIP raster members can be screened without extracting whole packs. Tiny pixel art and intentional minimal styles are not low-quality rejection rules.

Install classifier software with `pip install -e ".[vision]"`, then `infinite-creativity prepare-live-vision`. The pinned weights and checksums are software, not an asset index. `IC_VISION_MODEL` can select an existing pinned installation. Weight loading is reused in memory; image data/verdicts are not kept across calls. The explicit `metadata` mode is for compatibility and does **not** promise visual filtering.

The classifier covers the recorded image views. It does not certify unseen model geometry, animation frames, speech, music lyrics, contextual innuendo or subjective artistic quality. A 3D thumbnail pass remains a thumbnail pass. Audio, video and other temporal/project originals are withheld by default unless a real local reviewer is configured. Do not call these items completely reviewed merely because upstream declared a safe flag.

## Exact duplicate admission

Response-local identities and complete known original/dependency digest bundles are compared before emitting cards. Common geometry with different texture dependencies is preserved. Exact reviewed original-raster digests can also collapse repeats. Signed **client navigation cursors** carry at most 384 digest receipts; they contain no titles, licences, image data, manifests or saved result set. This is bounded traversal deduplication, not a persistent global artwork/perceptual similarity database. Different pages or sources outside that horizon can still repeat an artwork. No blanket global uniqueness claim is made.

## Optional original-media reviewer

`IC_MEDIA_REVIEW_COMMAND` is a JSON argv array of a trusted program installed by the local operator. It is never obtained from source data or a tool input, never runs through a shell, and receives one current item descriptor on stdin. It must fetch/check the current original content without keeping it. Timeout and response size are bounded. The response must contain:

```json
{
  "revision": "the exact current revision from stdin",
  "decision": "allow",
  "checks": ["sexual", "suggestive", "technical-quality"],
  "scope": "the actual original media checked",
  "evidence": "brief verifiable evidence"
}
```

Missing required checks, a mismatched revision, an unavailable reviewer or rejection cannot create an approval. This is a backend integration contract, not a supplied comprehensive audio/geometry/art-quality model. Do not invent a permissive reviewer merely to increase library counts.

No image classifier or metadata rule can guarantee perfect contextual moderation. The current quality gate rejects invalid/unsupported media; it does not claim to distinguish all bad art from deliberately simple art.
