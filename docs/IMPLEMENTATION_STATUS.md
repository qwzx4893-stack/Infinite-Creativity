# Quality and production hardening

Approved scope (2026-10-21): dependency security/reproducibility; request cancellation and aggregate budgets; media/network isolation; verified efficient chunk delivery; source readiness/search/quality; cross-platform validation and documentation. Additional priority: useful professional UI/motion sources and automatic quality/duplicate exclusion without a persistent asset index or exhaustive original downloads.

The implementation is present on the review branch. Measured local/installed acceptance and limitations are recorded in [VALIDATION_V012.md](VALIDATION_V012.md) and [validation.json](../artifacts/production/validation.json). GitHub check runs are the authoritative current CI status; configuration alone is never reported as a passing job or healthy provider.

## Acceptance gates

- Fresh media+quality install resolves a patched Pillow and passes original tests.
- Cancellation propagates into network/media checkpoints; server admission is bounded and cleanup is tested.
- Request-local host approvals, consistent HTTP deadlines, and resource-limited native readers have explicit platform limits.
- Signed chunk proofs authorize only exact previously inspected bytes and current rights; unsupported ranges remain explicit.
- Curation uses type-specific evidence, excludes demonstrably poor/duplicate assets, and reports unknown cases without invented universal quality scores.
- Professional UI/motion author sources deliver actual current files, dependencies and license notices without account keys where independently public.
- The 21st marketplace's authenticated endpoint is not called anonymously through forged credentials. Public author sources are identified by their real provenance and are not mislabeled marketplace access.
- Tests cover all new contracts, real selected-source delivery, clean installation and meaningful platform/runtime variations.

## Source-access research

2026-10-21: Context7's older `/api/r/{author}/{component}` description said free components could be fetched without authentication. Actual requests for `kevingirelli/signature` and `shadcn/button` returned HTTP 403 `Authentication required`; the `/r/` variant also returned 403. No successful marketplace download is claimed. The independent `KevinGirelli/corsair-ui` repository and current MIT license are public, providing a candidate original-author route to a component also listed on 21st.

The task does not require a 21st account key to continue. Author registry/source access and quality hardening proceed independently.
