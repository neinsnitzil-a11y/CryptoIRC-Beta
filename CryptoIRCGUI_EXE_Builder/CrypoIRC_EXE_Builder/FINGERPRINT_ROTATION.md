# Verified Fingerprint Rotation — CryptoIRC (CLI, GUI, Termux)

The mesh protocol **automatically detects** when a peer at a previously trusted
HOST:PORT presents a different cryptographic fingerprint after a handshake.
For security, **it never automatically trusts the replacement key**. A changed
key could indicate a server reinstall or an attacker impersonating the server.

## CLI (Windows, Linux and Termux)

- At connection time, a changed key produces a clear `RELAY IDENTITY CHANGE DETECTED`
  warning, showing the stored and newly presented 16-character fingerprints.
- While running interactively, the CLI asks you to **independently verify** the
  new fingerprint (using server SSH console or a known administrator), then type
  `TRUST <new-fingerprint>` exactly to update the saved pin and retry.
- Press Enter to cancel. The connection stays blocked and the original pin is
  unchanged. Headless relays and uninteractive clients do not auto-trust keys.
- To change trust explicitly later, use `/trust` to view pins, then
  `/rotate HOST:PORT FINGERPRINT`; it requires you to type `TRUST FINGERPRINT`.
  `/unpin HOST:PORT` remains supported as a separate manual operation.
- Only the relevant endpoint is modified. A permission-restricted backup of the
  previous pin mapping is created under `~/VaultForge/mesh_chat` or the
  configured user chat storage root.

## CRYPTO NOCTURNE native GUI

On a changed server identity, the GUI receives a structured `peer_identity_changed`
event and automatically opens the verification dialog, displaying the original
and newly presented fingerprints. The new key is UNTRUSTED until verified
**independently** and manually entered in the dialog, followed by confirmation.
The GUI checks that the entered fingerprint matches the one the peer presented.
Cancelling or typing another value leaves the old pin unchanged; accepting updates
just that endpoint's pin, saves a backup, and retries the connection.
You can still choose `Verify / Update Relay Trust` manually.

## Your AWS relay

If you explicitly recreated the AWS relay, its identity changed from
`f704e415f7ffc6dd` to `9aca2e4a28878448`, as you confirmed from the server
console in your previous log. You should always verify the current value again
from your own server console before approving a rotation.

Do not paste passwords, `node.secret`, private keys or wallet recovery material
into logs. No AWS relay update is required for this client-side workflow.

## Verification

Source-level simulated peer handshakes, explicit approval/cancellation, wrong-ID
rejection, unrelated pin preservation, and GUI prompts passed locally.
This does not prove a Windows EXE rebuild or a live AWS network test.
