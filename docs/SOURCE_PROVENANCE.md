# Source provenance and redistribution boundaries

This repository is the **standalone, neutral** portion of the BTLX tooling
developed for the EasyTech research project. Its public source history begins
with a clean publication commit; it is **not** a mirror or export of the
original private research repository and does not import that repository's
Git history.

## Scope of the published source

| Module | Purpose |
|---|---|
| `src/btlx_core/wire.py` | Strict, byte-preserving protobuf wire parsing and serialization |
| `src/btlx_core/schema.py` | Caller-provided descriptor model and validation |
| `src/btlx_core/codec.py` | Descriptor-qualified decoding, editing and difference detection |
| `src/btlx_core/edit.py` | Generic transactional edit plans |
| `src/btlx_core/__init__.py` | Public import surface |

Source extraction removed embedded game profiles and game-specific reference
rewriting. The core uses Python's standard library and package-local imports;
it does not vendor third-party Python libraries. The repository does **not**
include original game data, game executable code, recovered descriptors,
APK/SO/DEX files, signing material or reverse-engineering evidence.

## Development and contribution provenance

The underlying modules were developed in the project workspace, with a single
developer identity observed in their available source history at the point of
extraction. This is a **bounded Git-history and source-import observation**,
not an independent audit proving exclusive ownership of every contribution.
AI-assisted development may have been used, as with other project code.

The project maintainer authorized release of this neutral core under
**LGPL-3.0-or-later**. Contributors retain copyright in their own work;
future contributions must be made with permission to distribute them under
that license. See [CONTRIBUTING.md](../CONTRIBUTING.md) and
[NOTICE.md](../NOTICE.md).

If you discover an uncredited third-party source, a rights conflict or a
proprietary artifact here, please open a GitHub issue with a **non-sensitive**
description and affected file path. Do not include copyrighted game content
or personal credentials in an issue.
