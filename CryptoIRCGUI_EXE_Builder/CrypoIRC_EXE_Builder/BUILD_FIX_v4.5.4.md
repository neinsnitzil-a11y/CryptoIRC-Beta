# CRYPTO NOCTURNE v4.5.4 builder repair — Windows builder test repair

## Repair

- Implemented missing `MeshNode.remember_retry()` used by the GUI worker and CLI.
- Eliminated references to obsolete `retry_after` and `retry_delay` in fingerprint rotation.
- Made GUI trust rotation reset its reconnect flag after removing a changed host from the retry queue.
- Updated GUI regression tests to match the current no-typing flow, with two explicit confirmation dialogs, cancellation safety, input validation, and endpoint-change checks.
- Added tests for GUI worker connect, deduplicated reconnect targets, offline mode, and manual identity rotation.
- Kept the existing two AWS relay endpoints and community hosts catalog.

## Build on Windows

1. Extract this **entire** ZIP to a new folder (do not overlay an older source tree).
2. Inside the extracted directory, run `BUILD_WINDOWS.bat`.
3. In the builder window, run `FULL` (tests, PyInstaller, Inno Setup).
4. Inspect the build log for `Ran ... tests` / `OK` before interpreting later compiler errors.

A Windows EXE and Inno Setup installer have **not** been built or tested on this Linux environment. Do not copy `.vault` files, seeds, wallet keys, credentials, or saved chats into the source/release tree. No financial/security audit implied.

## Validation

On Linux, `build_release.run_tests()` completed: 504 tests, 502 passed, 2 skipped. Windows PyInstaller and Inno Setup were not executed here. The existing older application/version metadata remains v4.5.1 to avoid altering release-signature and upgrade policies in this builder-only repair.
