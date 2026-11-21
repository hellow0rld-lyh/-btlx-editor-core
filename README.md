# BTLX Editor Core

**Experimental lossless protobuf wire and descriptor-driven editing library** written in Python. The project exposes a small reusable core rather than a complete game editor.

> **Alpha 0.1.0a1.** Tested locally on Python 3.14. Python 3.11–3.13 are currently untested even though the declared version range allows them. No device or game runtime compatibility is claimed.

## What it does

- Parses and serializes protobuf wire records while preserving untouched bytes, unknown fields, duplicate occurrences, field ordering and noncanonical varints.
- Uses **caller-supplied** descriptor reports; no game-specific schema/profile is bundled.
- Supports atomic descriptor-qualified edits: \`assert\`, \`set\`, \`add\`, \`remove\`, \`clone\`, \`move\` and \`replace-message\`.
- Supports optional source SHA-256 preconditions so a transaction can refuse stale input.
- Has no runtime dependencies beyond Python's standard library.

## Install and try it

In a Python environment with setuptools available:

\`\`\`bash
python -m pip install --no-build-isolation .
python examples/synthetic_roundtrip.py
\`\`\`

To smoke-test the installed Wheel in an isolated target rather than using an environment-wide install:

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

## Limitations

No original game APK/SO/DEX, maps, payloads, recovered descriptor corpora, game-native patches or private evidence are included. There is no GUI, CLI or MCP server in this repository. Profile-specific reference rewriting, runtime gameplay validation and compatibility with a particular game build are **not** established. Supply your own descriptors/data that you are entitled to use.

## License

**GNU Lesser General Public License, version 3 or later (LGPL-3.0-or-later).**

- \`COPYING.LESSER\`: LGPLv3 supplemental terms.
- \`COPYING\`: GPLv3 base terms incorporated by LGPLv3.
- The Python library source files carry \`SPDX-License-Identifier: LGPL-3.0-or-later\`.

LGPL permits use from independently licensed or proprietary frontends subject to its requirements, including preserving notices and offering applicable replacement/relinking options. Original game names, content and trademarks are not covered by this project's license.

See [NOTICE.md](NOTICE.md) and [CONTRIBUTING.md](CONTRIBUTING.md).
