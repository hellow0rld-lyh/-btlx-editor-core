# BTLX Editor Core 0.1.0a1

**Release channel:** Alpha pre-release

**Python:** 3.11+

**License:** LGPL-3.0-or-later

## Included

- Strict Protobuf wire parser and byte-preserving serializer.
- Descriptor-injected schema/profile support.
- Structural read, comparison and typed edit operations.
- Transactional edit plans with optional source SHA-256 preconditions.
- Synthetic examples and ten contract regression tests.
- English and Simplified Chinese documentation.

## Distribution formats

The build produces:

- `btlx_editor_core-0.1.0a1-py3-none-any.whl`
- `btlx_editor_core-0.1.0a1.tar.gz`

The Wheel contains the five public Python modules, package metadata and GNU license texts. The source archive additionally contains the examples, tests and Markdown documentation.

## Verification

- Ubuntu Python 3.11, 3.12, 3.13 and 3.14: passed.
- Windows Python 3.14: passed.
- Local Python 3.14.6 wheel and source-archive build: passed.
- Local installation and synthetic smoke/regression tests: passed.

CI results are available from the [GitHub Actions workflow](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml).

## Known limitations

- Alpha API: no stable compatibility guarantee.
- No GUI, standalone CLI or MCP server.
- No bundled game-specific profiles, original game files or proprietary descriptor corpora.
- Synthetic package tests do not prove compatibility with a particular game build or device.
- PyPI publication and a GitHub Release are not part of this local release-candidate build.
