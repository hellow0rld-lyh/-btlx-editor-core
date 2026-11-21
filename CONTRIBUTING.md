# Contributing

Contributions are welcome if they are independently authored and permitted
to be distributed under **LGPL-3.0-or-later**.

## Local development

Use Python 3.11+ with setuptools and wheel installed. This project uses
only synthetic test data and the standard library at runtime.

```bash
python -m pip install "setuptools>=77" wheel
python -m pip install --no-build-isolation .
python -m unittest discover -s tests -v
python examples/synthetic_roundtrip.py
```

GitHub Actions runs these checks across the supported Python-version matrix.
A passing local test on one interpreter does not establish compatibility with
all other interpreters. See [compatibility](docs/COMPATIBILITY.md).

## Contribution boundaries

- Include a clear explanation and synthetic reproduction or regression test.
- Preserve existing copyright, license and provenance notices.
- Do not submit original game assets, proprietary descriptor dumps, APK/SO/DEX,
  private data, credentials, keys, or copied third-party source without
  compatible rights and attribution.
- You retain your own copyright. By contributing, you confirm that you have
  the right to provide the changes under the project's license.
- Identify any third-party influence, source reuse or copyright notices that
  affect your changes. Do not copy third-party code solely because it is public.
- Prefer new or changed synthetic regression tests with each behavioral fix.
- No copyright assignment or agreement granting proprietary frontend access
  to the original author is implied. Separate optional arrangements remain
  independent of the LGPL license.
