# v0.12 production and curation contracts

This document specifies implemented behavior and limits. Measured validation belongs in the version's validation artifacts; none of these limits implies exhaustive upstream coverage or perfect security/artistic judgment.

## Progressive curation

Every default MCP browsing request starts `LiveLibrary` with useful curation enabled. Its signed continuation retains that policy; batched search and creative-kit child scopes inherit it. The low-level Python `LiveLibrary` compatibility API remains configurable separately. Explicit `curate_library` applies its own stricter photographic/visual-score contract rather than running two conflicting filters.

The pipeline checks current rights/content, existing exact identity/bundle/pixel deduplication, bounded complete original evidence, then type-specific utility. Complete source syntax is checked without execution. Demonstrably empty component function bodies, zero-byte originals and invalid syntax/media are excluded. Unknown original quality remains in `quality_queue`; unreviewed originals remain in `review_queue`; pack navigation carries no approved-asset quality claim.

Parsed source fingerprints ignore comments/formatting tokens while preserving literal content and syntax. Cosmetic source duplicates are excluded only when the full parsed bundle and license notices agree. Existing original-pixel/GLB checks preserve ICC/material/transform differences. Cursor deduplication receipts are bounded; there is no global permanent duplicate index. Missing imports are explicit integration requirements, not evidence that an unexecuted UI renders successfully.

Photo thresholds use a pinned LAION aesthetic head over CLIP embeddings. The estimate is not applied as an authoritative UI/mesh/audio score. Photographic scoring also runs in a resource-limited process during MCP calls. Intentional minimal, pixel and low-poly styles are not rejection heuristics. No universal high-quality or sexual-content guarantee is claimed.

The filter covers every traversed configured source type; it does not claim a one-time scan of every original on every site. No asset catalog is persisted. `curation_policy` describes coverage; each response reports actual examined/excluded/queued counts and continuation. [Large-catalog navigation](V010_LARGE_CATALOGS.md) remains window/partition scoped.

## Request lifetime and capacity

- At most 4 active blocking MCP operations, 2 selected heavy operations and 12 admitted active/queued operations per server process.
- At most 2 media decoder processes run simultaneously, including decoders requested by ordinary browsing.
- One shared cancellation/deadline/budget scope follows child executor tasks. Aggregate ceilings are 256 HTTP requests and 640 MiB decoded network bytes, with 120 seconds ordinary or 330 seconds selected request time. Existing tighter provider/media limits still apply.
- Cancellation is cooperative in network reads, budget checks, provider-map waits and progress checkpoints. A received MCP cancellation notification propagates to those checkpoints; cancelling a client-side Python task alone is not assumed to send that notification.
- A cancelled caller does not release its admission slot while its worker still runs. Cleanup is briefly shielded; a slow socket can remain until its bounded read ends. Stuck native decoding is killed by its parent deadline. These are explicit operational bounds, not instantaneous thread termination.
- Runtime counters retain no asset metadata and are exposed by `library_diagnostics`.

## Network trust

Configured content hosts and provider-approved public HTTPS destinations belong to the request's `LiveHTTP` instance. They no longer expand a process-global approval set. Selected originals receive that instance's approved hosts.

Both metadata and original-byte transports use the same DNS-pinned HTTPS primitive. It rejects any resolution containing a private/non-global address, connects to the validated numeric socket address, and verifies TLS against the original hostname. Redirects are explicit and revalidated. Proxy environment variables are ignored. Public GET/HEAD only, fixed supported TLS ports, bounded decoded reads and request-local connection reuse apply. Provider tokens are attached only to their intended API host.

Configuration approval does not prove per-item rights or hostile-provider correctness. Source-provided text/code remains untrusted data.

## Selected original ranges

A complete selected review computes whole-file SHA256 plus a bounded set of chunk SHA256 values. The signed asset locator carries those digests and current metadata fingerprint, not file bytes. A later `read_asset_file` first revalidates current rights/manifest, reads complete proof blocks intersecting the requested window, verifies their digests, and returns only that exact window. Block sizes adapt to keep signed metadata bounded; normal blocks start at 1 MiB.

Encoded registry JSON members, ZIP/TAR/container members and unsupported range transports require complete-file revalidation. A changed ranged representation is never emitted: the router may instead fetch the complete original and verify its **prior signed whole-file digest** before returning a window. If that full digest also changes, delivery fails. The response distinguishes `verified-original-range`, complete verification and a range-representation fallback.

Met's image service produced a different total/byte representation for a ranged request in a real test even with identity encoding. The exact-range contract rejected it; subsequent complete-file digest verification successfully delivered the original. Cleveland, Poly Pizza, a photographic sample and original-author source files exercised verified range delivery. These are sample observations, not universal provider range promises.

## Decoder isolation

MCP original image, selected native/temporal/layered media, delivery rechecks and photographic aesthetic assessment use fixed local decoder software in child processes. Source code is never imported or executed. The workers:

- apply a 3 GiB memory cap and CPU limits before loading original parsers: Windows Job Objects including child processes, or POSIX address-space/CPU/file-descriptor limits;
- receive a minimal environment without provider/cloud credentials and installed, pinned local model paths;
- disable Python network connections and enforce request-staged paths;
- return bounded JSON/evidence, verified generated previews and explicitly scoped conversion paths;
- are killed on parent deadline/cancellation, with owned native descendants constrained by the Windows job;
- leave no staged original after the request ends.

Blender runs with factory settings, auto-execution disabled and an owned fixed inspection script. Existing scoped-dependency and unsupported simulation/rig/layer checks remain. A synthetic BLEND fixture was actually inspected during local acceptance.

**No OS filesystem sandbox or OS-wide network namespace is claimed.** Python network guards do not constrain arbitrary native network code. POSIX address-space accounting and Windows commit-memory accounting differ. Supported preview composition and some compatibility/in-process paths remain bounded Python/library code. Installed native software versions and parser limitations still matter. Missing/unsupported readers fail explicitly.

## Dependencies, diagnostics and CI

Pillow is constrained to `>=13,<14`, addressing the audited 12.3.0 dependency range. `uv.lock` resolves supported Python/platform branches; `requirements.lock` exports pinned versions and hashes. CI verifies lock consistency, audits known dependency vulnerabilities and tests Linux Python 3.11/3.13 plus Windows Python 3.13. Workflow actions are pinned to reviewed commit identifiers. Native OS libraries and provider responses are not frozen by a Python dependency lock.

`infinite-creativity doctor` and `library_diagnostics` inspect readiness without downloading assets/software. `--verify-models`/`verify_models=true` hashes installed model software. Missing readiness does not silently authorize unchecked media. Cairo and Blender are native prerequisites for their respective format paths.

Tests include actual SDK stdio cancellation, aggregate budgets/context propagation, DNS pinning, request-local approvals, exact/cross-block chunk integrity, changed representations, source-quality cases, original-author routes, OS worker limits, credential stripping and hard decoder termination. `scripts/verify_local_media.py` uses generated fixtures and actual installed readers/models; it measures execution, not learned-model accuracy across a representative real-world corpus.

Historical v0.x documents are records of their versions. They are not current whole-site quality/coverage certificates.
