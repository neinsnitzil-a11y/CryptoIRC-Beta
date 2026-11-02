# v2.8.1 mesh diagnostics hotfix

Preserves v2.8.0 features, saved relays and fingerprints. The retry log now shows the actual error message instead of only `ValueError`. TCP timeouts now report 'TCP connection timed out' instead of a blank cause. It does NOT relax fingerprint-change protections.

For a NEW EC2 relay, install the separate `VaultForge_AWS_Standalone_Relay_v2.8.1.zip` on the server.

Your log already attempts `18.227.91.173:6667`; the old endpoint in `/trust` is a retained pin, not the active connection. It remains until explicitly removed.
