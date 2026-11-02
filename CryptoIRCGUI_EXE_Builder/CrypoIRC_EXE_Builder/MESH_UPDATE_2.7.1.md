# VaultForge Mesh 2.7.1 — rooms, roster and transfers

- Create or join channels with `/join #room` or `/create #room` (rooms are decentralized and announced to connected peers).
- `/rooms` shows currently visible room names and online counts across **reachable** mesh nodes, not all users worldwide.
- `/users` shows currently authenticated online peers. The new relay forwards recent signed presence immediately to newly connected peers; older relays may require a heartbeat interval.
- `/msg USER@ID message` sends a private encrypted DM; you cannot message yourself. Select the recipient from `/users` in the GUI. Use **Send to Room** to clear the DM target.
- `/upload USER@ID PATH` sends an encrypted file/folder to one online user.
- `/uploadroom #room PATH` or `/sendroom #room PATH` sends separate encrypted offers to up to eight currently online members who advertise membership of that room. Recipients accept individually. Max 4 MiB compressed per recipient; no offline queue.
- Room messages and room histories are readable by relays; DMs and files are per-recipient encrypted. This custom protocol is unaudited.
- Existing identity stores and wallet vault files are unchanged. Do not copy account databases or private keys to AWS.
- Update the AWS relay to 2.7.1 to allow immediate signed roster synchronization. Old peers remain wire-compatible for normal chat.
