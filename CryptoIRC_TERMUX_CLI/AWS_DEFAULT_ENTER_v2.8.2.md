# AWS connect prompt update v2.8.2

In all CLI editions (Windows, Linux, Termux): Main menu 21 > Mesh menu 1.
The menu now displays “Hit Enter for default HOST:PORT” and the connection prompt
shows the active saved relay (initially 18.227.91.173:6667).
Press Enter at the HOST:PORT prompt to use that active saved address. Typing a
host explicitly still overrides the default for that connection.

Existing trust pins and server catalogs are not reset or replaced. When upgrading,
extract into a new folder and keep a backup of your existing account, known-peers,
and settings directories; don't delete your data folder. New first-contact keys
are still TOFU; independently verify server identity before sending sensitive data.

This prompt update does not install the AWS relay, open port 6667 or prove that it
is reachable. A secure connection still requires an online compatible relay.

Tests: Termux app suite 169 tests (168 pass, 1 skip); five CLI editions' AWS menu
tests 7/7 each; GUI default tests 3/3. Full GUI Windows EXE build was not run.
