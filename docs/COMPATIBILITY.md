# Compatibility and verification

The package declares `requires-python = ">=3.11"`, but **a declaration is
not a test result**. The initial GitHub Actions run completed successfully
on all five configured jobs: [CI run #44885784941](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/runs/44885784941),
2026-11-21, source commit `f6046a57fc8218355e79db20ca6dab7ed0476d98`.
The synthetic, dependency-free matrix is defined in
[`python-ci.yml`](../.github/workflows/python-ci.yml):

| Platform | Python | CI run #44885784941 |
|---|---|---|
| Ubuntu | 3.11 | **PASS** |
| Ubuntu | 3.12 | **PASS** |
| Ubuntu | 3.13 | **PASS** |
| Ubuntu | 3.14 | **PASS** |
| Windows | 3.14 | **PASS** |

The initial release was built and installed locally on Python **3.14.6**.
Other interpreter/platform combinations should only be marked **passed**
after their actual CI jobs complete successfully.

Checks: standard-library compilation; isolated installation; ten synthetic
contract regression tests; synthetic example; and smoke testing of a second
target-directory installation.

A separate `distributions` CI job is now configured to build both Wheel and
source archive with `python -m build`, run `twine check`, confirm that the
source archive contains the Chinese guide and synthetic tests, and install
both artifacts into isolated targets. Its result is pending the next GitHub
Actions run; the local 3.14.6 build and both isolated installs have passed.

These checks verify Python packaging and parsing/editing behavior, **not** any
specific proprietary game data or device. No third-party assets or recovered
descriptor corpus are bundled. For actual per-job results, use the
[GitHub Actions page](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml).
