# TERMUX — Encrypted File Inbox and Safe Downloads

This update adds a discoverable receiving workflow to existing VaultForge encrypted attachment transfers. It does **not** change the mesh wire protocol, wallet storage, chat identity, or the 4 MiB attachment limit.

## How receiving works

1. The sender connects to the same reachable mesh as the intended recipient, then sends a file with `/upload USER@ID PATH` or shares to a room with `/uploadroom #general PATH`.
2. The recipient must also be connected and logged in. Each online recipient receives a separate, encrypted attachment offer. Room file sharing is opt-in per recipient; being in a room does not auto-download anything.
3. Wait for **READY** (not **Receiving**). Files do not appear on disk until the recipient explicitly accepts an offer. Incomplete, expired or rejected offers require the sender to resend.
4. Files save to the receiver's own `~/VaultForge/mesh_chat/downloads` (Windows: `%USERPROFILE%\VaultForge\mesh_chat\downloads`). Folders are delivered as ZIP archives, without automatic extraction or execution. Downloads are saved with exclusive non-overwriting filenames.

## Windows / Linux CLI (and full Termux CLI)

```text
/files               # Numbered list of current incoming offers
/inbox               # Alias for /files
/download 1          # Download the first READY offer
/download ID         # Download by the exact ID shown by /files
/accept ID           # Original command remains supported
/reject 1            # Reject an incoming offer by index
/downloads           # Show the private downloads folder and saved files
/saved               # Alias for /downloads
```

For example, a file offer may appear as `1. [READY] README.md (87557 bytes) from Joker@... | ID ...`; enter `/download 1`. A second recipient can separately accept the same room offer. **File numbers are snapshots** and can change if an offer expires or another file arrives; choose by full ID when uncertain. Received files are not made available remotely as a persistent server library, and the server does not provide offline mailbox storage.

## CRYPTO NOCTURNE Windows GUI

1. Sign in to **Mesh Network**, connect to the relay, and open **Receive / Download Files**.
2. On **File Inbox**, click **Refresh Inbox**, select a READY item, then **Download Selected**. Select **Reject** to discard the offer.
3. After saving, select **Downloaded Files**. Use **Preview Image / Text / ZIP** for accepted PNG/JPEG/GIF/WebP/BMP images, safe plain-text/Markdown/JSON/CSV/log inspection, or a ZIP contents listing. Preview does not extract a ZIP, execute a downloaded program, or open untrusted attachments automatically.
4. Click **Open Downloads Folder** to access the saved file with your operating system's file manager.

Image previews use Pillow when available; the built-in Tk fallback supports PNG and GIF. Unknown file types stay on disk unopened. ZIP previews show filenames only; inspect any content and manually extract only if you trust the sender.

## CLI setup

Use the existing `Windows/INSTALL_WINDOWS.bat` / `Windows/START_WINDOWS.bat` or `Linux/install_linux.sh` / `Linux/start_linux.sh`. This source update does not require reinstalling the AWS relay. The Termux port uses its existing install/start scripts.

## GUI setup

For a full source release: extract and run the original `START_WINDOWS.bat` to use source, or `BUILD_WINDOWS.bat` to compile the EXE. For a **small GUI patch**, extract it into the same project root as `BUILD_WINDOWS.bat`, preserving `src/` paths, then rebuild/restart. An already compiled EXE cannot update itself from the source patch.

## Security and limits

- Custom mesh encryption is experimental and not independently audited.
- The receiver explicitly accepts every encrypted attachment; avoid unknown senders. Files use a maximum 4 MiB encrypted transfer size and may expire after about 30 minutes in memory.
- Public room **messages** and history may be visible to relays; file contents and direct messages use recipient encryption.
- Files do not auto-extract; a received ZIP may contain malicious files. Never run unknown executables or scripts.
- This is a source release tested offline. Live AWS deployment and new Windows EXE compilation still require device testing.
