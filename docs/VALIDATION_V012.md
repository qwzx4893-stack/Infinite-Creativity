# v0.12 validation

The machine-readable record is [validation.json](../artifacts/production/validation.json). Counts below describe measured runs, not all upstream assets or all possible behavior.

## Local acceptance

- Final pre-merge review: 234 tests ran on Windows Python 3.13.15; 233 passed and the POSIX-only process-group regression was skipped on Windows. Linux CI runs that regression. The earlier 218-test runs below describe the initial acceptance baseline.
- The rebuilt final wheel independently ran the same 234 tests on Windows Python 3.12.14: 233 passed, with the same one POSIX-only skip.
- 218/218 tests passed on Windows Python 3.13.15, including actual SDK stdio cancellation, aggregate resource limits, original-author routing, source curation, DNS pinning and chunk contracts.
- 218/218 passed against a clean installed wheel on Python 3.12.14. No optional tests were skipped. WebMCP tests passed.
- Both installations actually ran the pinned image/speech readers and native Blender against generated PNG/WAV/GLB/BLEND fixtures. No fake classifier was used in those local media acceptance scripts. Unit tests elsewhere do use controlled classifiers/transports.
- All ten installed model-software files matched their pinned hashes. No originals or model weights were placed in the public source tree.
- The exported lock's 67 active-marker packages had zero known vulnerabilities in pip-audit 2.10.1 at verification time; no package was skipped. This is point-in-time known dependency data, not a proof that the whole system is vulnerability-free. CI additionally checks the Python 3.11/3.13 marker branches.

## Real source delivery

Selected current author routes delivered source, dependencies and notices through actual MCP: Corsair, UI Layouts and useLayouts, plus Magic UI/shadcn samples. The clean installed package resolved a selected 21st Signature URL to its original public Corsair author source and delivered four scoped files without a 21st key. That does not imply anonymous access to every marketplace component.

Other sample workflows exercised original motion/shader code, Met/Cleveland images, a Poly Pizza model, a Meta Open Sound instrument and a PD3M photograph. Actual audio listening revalidation and signed original range delivery passed. A photographic estimate of 6.332 was observed, with threshold 0 selection and threshold 10 exclusion; this demonstrates the filter contract, not an objective professional-quality label.

GitHub's anonymous API allowance was exhausted during an early multi-source run. Rechecking with the existing optional GitHub session succeeded; no 21st key was requested or used. UI Layouts initially exposed a missing configured `www` redirect and was successfully rechecked after correction. Those failures were not substituted with saved results.

Met served different bytes/extent for a ranged representation. Chunk verification rejected those bytes. Complete-file revalidation against the prior signed digest then succeeded; the transport reports that fallback. Incompetech transport timed out in the final sample; its configured connector is retained but no successful final delivery is claimed. The instrument source separately passed real audio delivery/revalidation.

## Pre-merge corrections

The independent review reproduced and corrected incomplete HTTP body acceptance, slow-drip HTTP reads bypassing cancellation/deadline checks (including status/header/chunk lines), source fingerprints omitting JSON configuration or file layout/root roles, and BOM-prefixed author files having incorrect original checksums. Sixteen new regression cases cover these contracts and the media fixes below.

GLB preview rendering, audio excerpt decoding and CLIP/SVG ranking now run inside the bounded decoder workers during MCP requests, including receipt-preview paths. POSIX cleanup also terminates owned native descendants after a worker leader has already exited. Actual generated GLB preview, WAV excerpt and PNG/SVG ranking succeeded after the changes; the original-author, UI Layouts and useLayouts delivery workflows also passed again with complete notices/dependencies.

## Quality coverage and boundaries

All default MCP browsing pages apply the same progressive type-specific policy, including continuations and batched/kit child scopes. This is not a completed scan of every publisher's inventory. No item database exists to delete wholesale. Rejected/duplicate candidates are omitted at request time, uncertain quality is queued, and current source failures stay visible.

Semantic source checks cover root components separately from helpers: a valid dependency cannot hide an empty root. Source fingerprints preserve literal content and rights notices. Existing geometry/material/ICC/pixel safeguards remain. These tests establish concrete contracts; they do not certify all UI appearance, animation performance, model topology or classifier accuracy.

Workers enforce OS memory/CPU bounds and hard parent deadlines, with credentials removed and Python networking disabled. They are not claimed to be an OS filesystem sandbox. Unsupported formats/semantic scopes remain explicit.

## Reproduce

```bash
uv sync --frozen --all-extras
uv run --frozen --all-extras python -m unittest discover -s tests -v
node tests/webmcp.test.mjs
uv run infinite-creativity doctor --verify-models
uv run python scripts/verify_live_workflows.py --case 21st-original --case ui-layouts --case uselayouts
uv run python scripts/verify_local_media.py
```

Prepare the three pinned model-software folders and an existing Blender installation for the actual media acceptance script. GitHub/source capacity and content availability can change. The machine-readable artifact links the authoritative [current CI checks](https://github.com/qwzx4893-stack/Infinite-Creativity/pull/1/checks) and the [independent original-author acceptance run](https://github.com/qwzx4893-stack/Infinite-Creativity/actions/runs/39591388349); local success does not stand in for remote CI completion.
