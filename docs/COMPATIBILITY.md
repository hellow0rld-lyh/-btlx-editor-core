# Compatibility and verification

The package declares `requires-python = ">=3.11"`, but **a declaration is
not a test result**. The project tests its synthetic, dependency-free API
on GitHub Actions using the matrix in
[`python-ci.yml`](../.github/workflows/python-ci.yml):

| Platform | Python | Validation source |
|---|---|---|
| Ubuntu | 3.11 | CI matrix |
| Ubuntu | 3.12 | CI matrix |
| Ubuntu | 3.13 | CI matrix |
| Ubuntu | 3.14 | CI matrix |
| Windows | 3.14 | CI matrix |

The initial release was built and installed locally on Python **3.14.6**.
Other interpreter/platform combinations should only be marked **passed**
after their actual CI jobs complete successfully.

Checks: standard-library compilation; isolated installation; ten synthetic
contract regression tests; synthetic example; and smoke testing of a second
target-directory installation.

These checks verify Python parsing/editing behavior, **not** any specific
proprietary game data or device. No third-party assets or recovered descriptor
corpus are bundled. For the actual per-job results, use the
[GitHub Actions page](https://github.com/hellow0rld-lyh/-btlx-editor-core/actions/workflows/python-ci.yml).
