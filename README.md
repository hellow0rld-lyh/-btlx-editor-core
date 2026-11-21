# BTLX Editor Core

[![Python CI](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml/badge.svg)](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: LGPL-3.0-or-later](https://img.shields.io/badge/license-LGPL--3.0--or--later-green)

**A lightweight, lossless Protocol Buffers wire parser and descriptor-driven binary editing core in Python.** The public package is a reusable library, not a complete game editor. It has no third-party runtime dependencies.

**中文简介：** BTLX Editor Core 是一个使用 Python 编写的轻量级无损 Protobuf 二进制解析与结构编辑库，支持未知字段保留、原始字节保真、外部描述符和事务式修改。它**不包含原版游戏文件、逆向获得的描述符或完整 GUI**。

> **Alpha 0.1.0a1.** Python 3.11, 3.12, 3.13 and 3.14 passed the initial Ubuntu CI matrix, and Python 3.14 passed on Windows ([verified run](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/runs/44885784941), 2026-11-21). No game or device compatibility is claimed.

## What it does

- Parses and serializes protobuf wire records while preserving untouched bytes, unknown fields, duplicate occurrences, field ordering and noncanonical varints.
- Uses **caller-supplied** descriptor reports; no game-specific schema/profile is bundled.
- Supports atomic descriptor-qualified edits: \`assert\`, \`set\`, \`add\`, \`remove\`, \`clone\`, \`move\` and \`replace-message\`.
- Supports optional source SHA-256 preconditions so a transaction can refuse stale input.
- Has no runtime dependencies beyond Python's standard library.

## Install and try it

Requires Python 3.11+ and a build environment with setuptools. PyPI distribution is **not yet available**; install from a cloned source checkout:

```bash
git clone https://github.com/hellow0rld-lyh/-btlx-editor-core.git
cd -- -btlx-editor-core
```

Then:

\`\`\`bash
python -m pip install "setuptools>=77" wheel
python -m pip install --no-build-isolation .
python examples/synthetic_roundtrip.py
python -m unittest discover -s tests -v
\`\`\`

To smoke-test a second installation in an isolated target rather than relying only on the environment-wide install:

\`\`\`bash
python -m pip install --no-build-isolation --no-deps --target .test-install .
python smoke_test.py .test-install
\`\`\`

The smoke test uses only synthetic bytes. To inspect the API:

\`\`\`python
from btlx_core import (
    ProfileSpec, profile_from_reports, parse_btlx,
    apply_edit_plan, parse_message, encode_varint, CodecError,
)
\`\`\`

\`examples/synthetic_roundtrip.py\` demonstrates a caller-authored descriptor and a byte-preserving edit. The historical edit-plan schema identifier is \`EasyTechBTLXEditPlan/v1\`; it does **not** import or depend on the EasyTech research repository.

## Documentation and verification

- [Compatibility and Python test matrix](docs/COMPATIBILITY.md)
- [Source provenance and redistribution scope](docs/SOURCE_PROVENANCE.md)
- [Contribution guidelines](CONTRIBUTING.md)
- [CI status](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml)

CI runs synthetic contract regressions and isolated package tests for Python 3.11–3.14 on Ubuntu and 3.14 on Windows. These results do not establish compatibility with any particular proprietary game build.

## Limitations

No original game APK/SO/DEX, maps, payloads, recovered descriptor corpora, game-native patches or private evidence are included. There is no GUI, CLI or MCP server in this repository. Profile-specific reference rewriting, runtime gameplay validation and compatibility with a particular game build are **not** established. Supply your own descriptors/data that you are entitled to use.

## License

**GNU Lesser General Public License, version 3 or later (LGPL-3.0-or-later).**

- \`COPYING.LESSER\`: LGPLv3 supplemental terms.
- \`COPYING\`: GPLv3 base terms incorporated by LGPLv3.
- The Python library source files carry \`SPDX-License-Identifier: LGPL-3.0-or-later\`.

LGPL permits use from independently licensed or proprietary frontends subject to its requirements, including preserving notices and offering applicable replacement/relinking options. Original game names, content and trademarks are not covered by this project's license.

See [NOTICE.md](NOTICE.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
