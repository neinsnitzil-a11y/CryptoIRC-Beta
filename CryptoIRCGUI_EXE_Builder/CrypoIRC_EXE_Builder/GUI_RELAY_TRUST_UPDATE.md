# CRYPTO NOCTURNE — Mesh Relay Identity Update (GUI)

This patch adds a **Verify / Update Relay Trust** button to the existing native Mesh Network page.
It is intended for CRYPTO NOCTURNE's Mesh v2.7.2 source with auto-connect and Refresh Online.
It changes only the chat GUI/worker; it does not replace wallet vaults, chat accounts, or the AWS server.

## Why the old GUI cannot connect

The AWS relay identity was regenerated. The GUI correctly refuses a different fingerprint for the same endpoint.
The **chat message box is not a CLI command shell**. Typing `/trust` or `/unpin` there will NOT change its saved identity pins.

## Apply the small update on Windows

1. Close the CRYPTO NOCTURNE GUI/EXE.
2. Extract this patch ZIP **into the existing GUI source project root**, next to `BUILD_WINDOWS.bat`. The ZIP contains `PATCH_FILES` and `APPLY_GUI_RELAY_TRUST_FIX_WINDOWS.cmd`.
3. Run `APPLY_GUI_RELAY_TRUST_FIX_WINDOWS.cmd`. It checks for the existing `src/mesh_gui.py` and `src/mesh_bridge.py`, then backs up and patches those two source files.
4. For source testing use `START_WINDOWS.bat`, or run `BUILD_WINDOWS.bat` to compile a new EXE. The already compiled EXE is NOT modified by this source patch.
5. Open **Mesh Network**, log in to your existing `testuser1` chat identity, and leave `18.188.145.207:6667` in the Peer/bootstrap field.
6. Click **Verify / Update Relay Trust**. The window shows the saved fingerprint for the selected endpoint.
7. Independently verify the *new* fingerprint on your AWS server using its SSH terminal. For this particular recovery, the user already reported AWSVaultRelay as `9aca2e4a28878448`, replacing `f704e415f7ffc6dd`.
8. Type the new fingerprint into the dialog and confirm the deliberate trust rotation. The GUI writes only the endpoint-specific pin, backs up the old pins, and reconnects.
9. After `CONNECTED`, click **Refresh Online**. This shows currently reachable users, not every registered account.

If there is no saved pin, click Connect instead, then verify the new first-contact fingerprint separately.
If the new identity doesn't match the live server handshake, the connection will STILL be rejected.

## Files and data safety

The chat worker reads/writes `~/VaultForge/mesh_chat/known_peers.json` (Windows: `%USERPROFILE%\VaultForge\mesh_chat\known_peers.json`).
It writes `known_peers.pre-rotation-<random>.json` before changing that file.
The update does NOT delete/recreate `accounts.json`, chat account keys, wallet files, or the AWS identity.
The patch requires the old pin to still match what the GUI displayed, preventing accidental overwrites after another change.

## Testing

Four targeted test methods passed: failed old pin, verified rotation and actual local encrypted handshake, mismatch rejection, and live-link protection.
Full source regression: 494 tests run, 2 skipped, no failures on Linux Python 3.13. A native Windows EXE rebuild and real AWS reconnection have not been run in this environment.
Custom mesh protocol remains experimental and unaudited.
