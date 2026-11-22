# BTLX Editor Core

[![Python CI](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml/badge.svg)](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-LGPL--3.0--or--later-2B7A3D)
![Status](https://img.shields.io/badge/status-alpha-orange)

**A small, lossless Protocol Buffers wire parser and descriptor-driven binary editing library for Python.**

BTLX Editor Core focuses on one job: inspect structured binary data without needlessly rewriting bytes it does not understand. It is designed to be embedded in editors and tooling—not to be a complete game editor.

[简体中文文档](docs/README.zh-CN.md) · [Compatibility](docs/COMPATIBILITY.md) · [Source provenance](docs/SOURCE_PROVENANCE.md) · [Release notes](docs/RELEASE_NOTES_0.1.0a1.md)

---

## Why this core?

| Capability | What it means |
|---|---|
| **Lossless wire parsing** | Keeps original field bytes, ordering, duplicate occurrences, unknown fields and non-canonical varints. |
| **Descriptor-driven access** | Uses descriptors supplied by the caller; field numbers are not treated as globally meaningful. |
| **Surgical edits** | Re-encodes only the edited value and the length prefixes of affected parent messages. |
| **Transactional edit plans** | Supports guarded, multi-operation edits and returns a receipt only after post-write checks pass. |
| **Small runtime footprint** | Uses the Python standard library; no third-party runtime dependency. |

## What is included

- Strict parsing and byte-preserving serialization of Protocol Buffers wire records.
- Caller-supplied schema/profile construction and descriptor-qualified field access.
- Structural comparison and typed editing.
- Edit operations: `assert`, `set`, `add`, `remove`, `clone`, `move` and `replace-message`.
- Optional SHA-256 preconditions to reject edit plans targeting stale input.
- Synthetic examples and regression tests that do not require game assets.

## Quick start

**Requirements:** Python 3.11 or newer.

Clone the repository and install the library:

```bash
git clone https://github.com/hellow0rld-lyh/-btlx-editor-core.git
cd ./-btlx-editor-core
python -m pip install .
```

A minimal wire-level round trip:

```python
from btlx_core import parse_message, serialize_preserving

original = bytes.fromhex("08 07 10 2A")
message = parse_message(original)

# Unknown or untouched fields are emitted using their original bytes.
assert serialize_preserving(message) == original
```

For descriptor-qualified editing, see [`examples/synthetic_roundtrip.py`](examples/synthetic_roundtrip.py). It creates a synthetic descriptor, parses synthetic bytes, applies an edit plan and verifies that unrelated bytes remain unchanged.

## Build the distribution packages

The project is currently an **alpha source release**. A PyPI project release has not been published.

Build both standard Python distribution formats from a clean checkout:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

This creates:

- `dist/*.whl` — the installable wheel.
- `dist/*.tar.gz` — the source distribution, including documentation and synthetic tests.

Install a downloaded wheel with `python -m pip install path/to/package.whl`. The source archive can be installed with `python -m pip install path/to/package.tar.gz`.

The release candidate is version **0.1.0a1**. See [the release notes](docs/RELEASE_NOTES_0.1.0a1.md) for the contents and verification scope.

## API surface

The main public entry points are:

- `parse_message` / `serialize_preserving` — raw wire parsing and byte-preserving serialization.
- `ProfileSpec` / `profile_from_reports` — build a profile from caller-supplied descriptor reports.
- `parse_btlx` / `semantic_diff` — descriptor-aware parsing and comparison.
- `apply_edit_plan` — apply a validated multi-operation edit plan.

The historical plan schema identifier is `EasyTechBTLXEditPlan/v1`. It is a schema name only; this package does not import or depend on the private EasyTech research repository.

## Compatibility and verification

The package declares Python **3.11+**. The GitHub Actions matrix has passed on:

- Ubuntu: Python 3.11, 3.12, 3.13 and 3.14.
- Windows: Python 3.14.

CI runs synthetic regression tests, installation checks and examples. A dedicated [distribution job](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/runs/45017914707) also built the Wheel and source archive, passed `twine check`, and installed both formats. These results validate the Python package—not compatibility with a particular game version, save file or device.

See [the compatibility report](docs/COMPATIBILITY.md) and [GitHub Actions](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml).

## Scope and safety

This repository contains only the neutral Python core. It does **not** include:

- original game APK/SO/DEX files, assets, maps or payloads;
- recovered proprietary descriptor corpora or private research evidence;
- game-specific native patches or automatic game-version profiles;
- a graphical interface, standalone CLI or MCP server.

A successful parse is not proof that a field's game-specific meaning is known. Supply only descriptors and data you are entitled to use, and keep game/version-specific assumptions outside this neutral core unless they are independently evidenced.

## License

**LGPL-3.0-or-later.** The full license texts are included as `COPYING` and `COPYING.LESSER`. Preserve the notices and comply with the license when redistributing or modifying the library. See [`NOTICE.md`](NOTICE.md).

---

**Project status:** Alpha. The public API and edit-plan format may change before a stable 1.0 release.