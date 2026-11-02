#!/usr/bin/env python3
"""VaultForge: offline, encrypted, multi-coin KEY/ADDRESS generator.

WARNING: Software wallet. A USB stick does not provide secure-element protection.
No blockchain transactions or signing are performed by this program.
"""
from __future__ import annotations

import base64
import getpass
import hmac
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

COINS = [
    ("BTC", "Bitcoin (native SegWit BIP84)", "bip84", "BITCOIN"),
    ("LTC", "Litecoin (native SegWit BIP84)", "bip84", "LITECOIN"),
    ("DOGE", "Dogecoin", "bip44", "DOGECOIN"),
    ("BCH", "Bitcoin Cash (CashAddr)", "bip44", "BITCOIN_CASH"),
    ("DASH", "Dash", "bip44", "DASH"),
    ("DGB", "DigiByte", "bip44", "DIGIBYTE"),
    ("ZEC", "Zcash (transparent t-address only)", "bip44", "ZCASH"),
    ("ETH", "Ethereum", "bip44", "ETHEREUM"),
    ("ETC", "Ethereum Classic", "bip44", "ETHEREUM_CLASSIC"),
    ("BSC", "BNB Smart Chain", "bip44", "BINANCE_SMART_CHAIN"),
    ("POLYGON", "Polygon PoS", "bip44", "POLYGON"),
    ("AVAXC", "Avalanche C-Chain", "bip44", "AVAX_C_CHAIN"),
    ("ARB", "Arbitrum One", "bip44", "ARBITRUM"),
    ("OP", "Optimism", "bip44", "OPTIMISM"),
    ("FTM", "Fantom Opera", "bip44", "FANTOM_OPERA"),
    ("TRX", "TRON", "bip44", "TRON"),
    ("XRP", "XRP Ledger", "bip44", "RIPPLE"),
    ("XLM", "Stellar", "bip44", "STELLAR"),
    ("SOL", "Solana", "bip44", "SOLANA"),
    ("ATOM", "Cosmos Hub", "bip44", "COSMOS"),
    ("OSMO", "Osmosis", "bip44", "OSMOSIS"),
    ("NEAR", "NEAR Protocol", "bip44", "NEAR_PROTOCOL"),
    ("FIL", "Filecoin", "bip44", "FILECOIN"),
    ("XTZ", "Tezos", "bip44", "TEZOS"),
    ("VET", "VeChain", "bip44", "VECHAIN"),
    ("ZIL", "Zilliqa", "bip44", "ZILLIQA"),
    ("EGLD", "MultiversX (eGLD)", "bip44", "MULTIVERSX"),
    ("SUI", "Sui (ed25519)", "bip44", "SUI"),
    ("APT", "Aptos", "bip44", "APTOS"),
    ("XMR", "Monero (native legacy 25-word)", "monero", None),
]
COIN_BY_CODE = {x[0]: x for x in COINS}
VERSION = 1
AAD = b"vaultforge.v1.aes256gcm.argon2id"
KDF_TIME = 3
KDF_MEMORY_KIB = 65536
KDF_PARALLELISM = 2
MAX_VAULT_BYTES = 2_000_000


class CryptoDependencyUnavailable(RuntimeError):
    """Record only a fixed, public import name; never exception text or secrets."""
    def __init__(self, module_name: str):
        self.module_name = module_name
        super().__init__('Required wallet cryptography component unavailable')


def load_crypto():
    """Fail closed when the frozen EXE lacks a required cryptographic module."""
    from importlib import import_module
    for module_name in ('bip_utils', 'argon2.low_level',
                        'cryptography.hazmat.primitives.ciphers.aead'):
        try:
            import_module(module_name)
        except (ImportError, OSError) as exc:
            raise CryptoDependencyUnavailable(module_name) from exc


def encrypt_payload(payload: dict, password: str) -> bytes:
    from argon2.low_level import Type, hash_secret_raw
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = hash_secret_raw(password.encode("utf-8"), salt, KDF_TIME,
                          KDF_MEMORY_KIB, KDF_PARALLELISM, 32, Type.ID)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cipher = AESGCM(key).encrypt(nonce, raw, AAD)
    container = {
        "format": "VaultForge-Encrypted-Vault", "version": VERSION,
        "kdf": "argon2id", "kdf_memory_kib": KDF_MEMORY_KIB,
        "kdf_iterations": KDF_TIME, "kdf_parallelism": KDF_PARALLELISM,
        "cipher": "AES-256-GCM", "salt_b64": base64.b64encode(salt).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "ciphertext_b64": base64.b64encode(cipher).decode(),
    }
    return (json.dumps(container, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def decrypt_payload(blob: bytes, password: str) -> dict:
    from argon2.low_level import Type, hash_secret_raw
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(blob) > MAX_VAULT_BYTES:
        raise ValueError("Unreasonable vault file size")
    obj = json.loads(blob)
    if (obj.get("format") != "VaultForge-Encrypted-Vault" or obj.get("version") != VERSION
        or obj.get("kdf") != "argon2id" or obj.get("cipher") != "AES-256-GCM"):
        raise ValueError("Unknown/incompatible vault format")
    # Strictly reject unexpected KDF values to prevent malicious files exhausting memory.
    if (obj.get("kdf_memory_kib"), obj.get("kdf_iterations"), obj.get("kdf_parallelism")) != (
        KDF_MEMORY_KIB, KDF_TIME, KDF_PARALLELISM
    ):
        raise ValueError("Unsupported or unsafe KDF parameters")
    salt = base64.b64decode(obj["salt_b64"], validate=True)
    nonce = base64.b64decode(obj["nonce_b64"], validate=True)
    cipher = base64.b64decode(obj["ciphertext_b64"], validate=True)
    if len(salt) != 16 or len(nonce) != 12:
        raise ValueError("Invalid encryption header")
    key = hash_secret_raw(password.encode("utf-8"), salt, KDF_TIME,
                          KDF_MEMORY_KIB, KDF_PARALLELISM, 32, Type.ID)
    return json.loads(AESGCM(key).decrypt(nonce, cipher, AAD))


def secure_dir(folder: Path) -> Path:
    folder = folder.expanduser()
    if not folder.is_absolute():
        raise ValueError("Output folder must be an absolute path")
    # Do not allow symlinked final directories.
    if folder.is_symlink():
        raise ValueError("Refusing a symbolic-link output directory")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(folder, 0o700)
        except OSError:
            print("[WARN] Could not set directory permissions (common on FAT/exFAT USB drives).")
    return folder


def write_new_vault(folder: Path, payload: dict, password: str) -> Path:
    folder = secure_dir(folder)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"vault_{stamp}_{secrets.token_hex(6)}.vault"
    destination = folder / filename
    blob = encrypt_payload(payload, password)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(destination), flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        return destination
    except BaseException:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def update_password(path: Path, payload: dict, password: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Not a regular vault file")
    new_blob = encrypt_payload(payload, password)
    tmp = path.with_name(".rotate_" + secrets.token_hex(8))
    fd = os.open(str(tmp), os.O_EXCL | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new_blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def generate_bip39(words: int) -> str:
    from bip_utils import Bip39MnemonicGenerator
    return Bip39MnemonicGenerator().FromEntropy(secrets.token_bytes(16 if words == 12 else 32)).ToStr()


def generate_monero() -> str:
    from bip_utils import MoneroMnemonicGenerator
    return MoneroMnemonicGenerator().FromEntropyWithChecksum(secrets.token_bytes(32)).ToStr()


def validate_phrase(scheme: str, phrase: str) -> str:
    phrase = " ".join(phrase.strip().lower().split())
    if scheme == "monero":
        from bip_utils import MoneroMnemonicValidator
        if len(phrase.split()) != 25 or not MoneroMnemonicValidator().IsValid(phrase):
            raise ValueError("Not a valid 25-word legacy Monero phrase")
    else:
        from bip_utils import Bip39MnemonicValidator
        if len(phrase.split()) not in (12, 24) or not Bip39MnemonicValidator().IsValid(phrase):
            raise ValueError("Not a valid BIP39 12/24-word phrase")
    return phrase


def derive_coin(code: str, mnemonic: str, bip39_passphrase: str, account: int = 0) -> dict:
    from bip_utils import (Bip39SeedGenerator, Bip44, Bip44Coins,
                           Bip44Changes, Bip84, Bip84Coins, Monero, MoneroSeedGenerator)
    coin = COIN_BY_CODE[code]
    if code == "XMR":
        seed = MoneroSeedGenerator(mnemonic).Generate()
        wallet = Monero.FromSeed(seed)
        return {"coin": code, "address": wallet.PrimaryAddress(),
                "derivation": "Native Monero 25-word; primary address"}
    seed = Bip39SeedGenerator(mnemonic).Generate(bip39_passphrase)
    if coin[2] == "bip84":
        engine = Bip84.FromSeed(seed, getattr(Bip84Coins, coin[3]))
        purpose = 84
    else:
        engine = Bip44.FromSeed(seed, getattr(Bip44Coins, coin[3]))
        purpose = 44
    node = engine.Purpose().Coin().Account(account).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
    # Bip44 coin conf owns the SLIP-0044 coin index; paths can differ by chain.
    coin_idx = engine.CoinConf().CoinIndex()
    return {"coin": code, "address": node.PublicKey().ToAddress(),
            "derivation": f"m/{purpose}'/{coin_idx}'/{account}'/0/0"}


def discover_usb():
    """Mounted USB-backed filesystem choices; never repartitions or formats."""
    results = []
    if os.name == "nt":
        ps_script = (
            "$ErrorActionPreference='Stop'; "
            "$out=@(Get-Disk | Where-Object {$_.BusType -eq 'USB'} | ForEach-Object {"
            "$disk=$_; Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue | "
            "Where-Object {$_.DriveLetter} | ForEach-Object {"
            "[pscustomobject]@{path=([string]$_.DriveLetter+':\\'); label=$disk.FriendlyName}}}); "
            "ConvertTo-Json -InputObject $out -Compress"
        )
        try:
            p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                               capture_output=True, text=True, timeout=12, check=True)
            data = json.loads(p.stdout)
            for item in data if isinstance(data, list) else ([data] if data else []):
                if isinstance(item, dict) and item.get("path") and Path(item["path"]).is_dir():
                    results.append((Path(item["path"]), str(item.get("label", "USB drive"))))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    elif sys.platform.startswith("linux"):
        try:
            p = subprocess.run(["lsblk", "--json", "-o", "NAME,TYPE,MOUNTPOINTS,TRAN,RM,MODEL"],
                               capture_output=True, text=True, timeout=8, check=True)
            disks = json.loads(p.stdout).get("blockdevices", [])
            def visit(node, usb: bool, label: str):
                detected = usb or (str(node.get("tran") or "").lower() == "usb") or str(node.get("rm", "0")) in ("1", "true")
                name = str(node.get("model") or label or "Removable storage").strip()
                for mount in node.get("mountpoints") or []:
                    if detected and mount and Path(mount).is_dir() and mount != "/":
                        results.append((Path(mount), name))
                for child in node.get("children") or []:
                    visit(child, detected, name)
            for disk in disks:
                visit(disk, False, "USB disk")
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return list({str(p): (p, label) for p, label in results}.values())


def choose_storage() -> Path:
    print("\nSTORAGE TARGET\n 1) This computer (user profile, local storage)\n 2) Mounted USB drive\n 3) Custom absolute directory (external drive, etc.)")
    choice = input("Choice [1]: ").strip() or "1"
    if choice == "1":
        return secure_dir(Path.home() / "VaultForge" / "wallets")
    if choice == "2":
        usb = discover_usb()
        if not usb:
            print("No mounted USB drive found. Plug it in and mount it, or select custom path.")
            raise ValueError("No available USB drive")
        for idx, (path, name) in enumerate(usb, 1):
            print(f" {idx:2}) {path}   [{name}]")
        idx = number("USB drive number", 1, len(usb)) - 1
        return secure_dir(usb[idx][0] / "VaultForge" / "wallets")
    if choice == "3":
        path = Path(input("Absolute directory: ").strip()).expanduser()
        print("Custom folder contents are not modified. Vault files are created under VaultForge/wallets.")
        if input("Confirm custom path [yes/no]: ").strip().lower() != "yes":
            raise ValueError("Canceled")
        return secure_dir(path / "VaultForge" / "wallets")
    raise ValueError("Invalid storage choice")


def number(label: str, low: int, high: int, default: int | None = None) -> int:
    while True:
        tail = f" [{default}]" if default is not None else ""
        raw = input(f"{label} ({low}-{high}){tail}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = int(raw)
            if low <= val <= high:
                return val
        except ValueError:
            pass
        print("Enter a valid number.")


def choose_coins() -> list[str]:
    print("\n30 CRYPTOCURRENCIES")
    for idx, (code, name, _, _) in enumerate(COINS, 1):
        print(f"  {idx:2}. {code:<8} {name}")
    print("Select comma-separated numbers/codes, a range (1-5), or ALL.")
    while True:
        raw = input("Coins: ").strip().upper()
        if raw == "ALL":
            return [x[0] for x in COINS]
        selected = []
        try:
            for part in raw.replace(" ", "").split(","):
                if "-" in part:
                    a, b = (int(n) for n in part.split("-", 1))
                    if not 1 <= a <= b <= len(COINS):
                        raise ValueError("Invalid range")
                    items = [COINS[n-1][0] for n in range(a, b+1)]
                elif part.isdigit():
                    n = int(part)
                    if not 1 <= n <= len(COINS):
                        raise ValueError("Number out of range")
                    items = [COINS[n-1][0]]
                elif part in COIN_BY_CODE:
                    items = [part]
                else:
                    raise ValueError("Unknown coin")
                for item in items:
                    if item not in selected:
                        selected.append(item)
            if selected:
                return selected
        except ValueError as exc:
            print(f"Invalid selection: {exc}")


def new_password() -> str:
    while True:
        one = getpass.getpass("New VAULT password (minimum 14 characters): ")
        if len(one) < 14:
            print("Password too short.")
            continue
        two = getpass.getpass("Repeat VAULT password: ")
        if not hmac.compare_digest(one, two):
            print("Passwords do not match.")
            continue
        return one


def ask_seed(scheme: str, bipsize: int) -> str:
    if input("Import your OWN existing valid phrase? [y/N]: ").strip().lower() == "y":
        print("Imported phrases are read with hidden input; never paste someone else's phrase.")
        return validate_phrase(scheme, getpass.getpass("Existing seed (hidden): "))
    return generate_monero() if scheme == "monero" else generate_bip39(bipsize)


def clear_screen():
    # local terminal only, with no shell
    os.system("cls" if os.name == "nt" else "clear >/dev/null 2>&1")


def reveal_seed_groups(groups: list[dict], first_run: bool = False):
    print("\nSECURITY: Only show this on an offline, private computer.")
    print("No screenshots, cloud notes, email, messaging apps, or clipboard backups.")
    if input("Type REVEAL to show recovery phrases (anything else skips): ").strip() != "REVEAL":
        return
    print("\n" + "=" * 55)
    for i, group in enumerate(groups, 1):
        print(f"SEED GROUP {i} — {group['scheme']} ({len(group['mnemonic'].split())} words)")
        words = group["mnemonic"].split()
        for start in range(0, len(words), 4):
            print("  " + "    ".join(f"{j+1:2}.{words[j]}" for j in range(start, min(start + 4, len(words)))))
        if group["scheme"] == "bip39":
            print("BIP39 extra passphrase: " + (repr(group["passphrase"]) if group.get("passphrase") else "NONE"))
            if group.get("passphrase"):
                print("IMPORTANT: This exact extra passphrase is required during recovery.")
        print()
    print("=" * 55)
    input("Write phrases on paper/metal. Press Enter to clear this terminal screen.")
    clear_screen()
    if first_run:
        print("Your encrypted vault is still on disk. Verify a paper backup from the menu.")


def create_wallets():
    folder = choose_storage()
    coins = choose_coins()
    repeats = number("How many INDEPENDENT wallet sets", 1, 20, 1)
    bip39_coins = [c for c in coins if c != "XMR"]
    words = 24
    if bip39_coins:
        words = 12 if input("BIP39 length [1=12 words, 2=24 words] (default 2): ").strip() == "1" else 24
    passphrase = ""
    if bip39_coins and input("Use optional advanced BIP39 passphrase? [y/N]: ").strip().lower() == "y":
        print("WARNING: losing the exact phrase/passphrase prevents recovery. The passphrase is kept inside the encrypted vault.")
        passphrase = getpass.getpass("BIP39 passphrase (hidden; may be empty): ")
        if getpass.getpass("Repeat BIP39 passphrase: ") != passphrase:
            raise ValueError("BIP39 passphrase confirmation failed")
    print("\nOne NEW BIP39 seed is shared by the selected BIP39 coins WITHIN each set.")
    print("XMR always gets its own native Monero seed, separate from BIP39.")
    print("Every set gets new randomness; repeated sets never reuse a generated seed.")
    print("Keys stay inside the encrypted vault. No unencrypted keys are exported.")
    password = new_password()
    ready = []
    for i in range(repeats):
        print(f"\nGenerating set {i+1}/{repeats} ...")
        groups = []
        entries = []
        if bip39_coins:
            phrase = ask_seed("bip39", words)
            groups.append({"scheme": "bip39", "mnemonic": phrase, "passphrase": passphrase})
            for code in bip39_coins:
                info = derive_coin(code, phrase, passphrase)
                info["seed_group"] = 0
                entries.append(info)
        if "XMR" in coins:
            phrase = ask_seed("monero", 25)
            groups.append({"scheme": "monero", "mnemonic": phrase, "passphrase": ""})
            info = derive_coin("XMR", phrase, "")
            info["seed_group"] = len(groups)-1
            entries.append(info)
        payload = {
            "format": "VaultForge-Unlocked-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
            "wallets": entries, "groups": groups,
            "warnings": ["NOT a true hardware wallet", "This program does not send transactions", "Derivation scheme matters during recovery"],
        }
        path = write_new_vault(folder, payload, password)
        ready.append((path, payload))
        print(f"[SAVED] {path}")
        for info in entries:
            print(f"  {info['coin']:8} {info['address']}")
        if input("Show this set's seed phrase(s) now? [y/N]: ").strip().lower() == "y":
            reveal_seed_groups(groups, first_run=True)
    print(f"\nCreated {len(ready)} encrypted vault(s). Protect the password AND recovery phrases.")
    print("Back up phrase(s) offline and independently of the USB; USBs can fail.")


def pick_vault() -> Path:
    folder = choose_storage()
    vaults = sorted(folder.glob("*.vault"), key=lambda p: p.name, reverse=True)
    vaults = [v for v in vaults if v.is_file() and not v.is_symlink()]
    if not vaults:
        raise ValueError("No .vault files in this location")
    for i, v in enumerate(vaults, 1):
        print(f" {i:3}) {v.name} ({v.stat().st_size:,} bytes)")
    return vaults[number("Vault file number", 1, len(vaults))-1]


def unlock(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Not a regular vault file")
    if path.stat().st_size > MAX_VAULT_BYTES:
        raise ValueError("Vault file exceeds size limit")
    password = getpass.getpass("Vault password: ")
    try:
        data = decrypt_payload(path.read_bytes(), password)
    except Exception as exc:
        raise ValueError("Unable to unlock (incorrect password or damaged vault)") from exc
    if data.get("format") != "VaultForge-Unlocked-v1":
        raise ValueError("Unknown encrypted payload version")
    return data


def print_wallets(payload: dict):
    print("\nPUBLIC RECEIVE ADDRESSES (check network and address type before receiving funds)")
    for entry in payload["wallets"]:
        print(f"\n {entry['coin']}   {entry['address']}\n       {entry['derivation']}")
    print("\nAn address here is not proof of wallet compatibility with any particular wallet app.")


def backup_check(payload: dict):
    for group in payload["groups"]:
        words = group["mnemonic"].split()
        checks = secrets.SystemRandom().sample(range(len(words)), min(3, len(words)))
        print(f"\nVerify {group['scheme']} backup ({len(words)} words). Do not read from the screen.")
        for pos in checks:
            typed = getpass.getpass(f"Enter the word at position {pos+1} (hidden): ").strip().lower()
            if not hmac.compare_digest(typed, words[pos]):
                print("[FAILED] Backup does not match this vault; review your paper backup offline.")
                return
    print("[PASS] Sampled seed words matched the encrypted vault.")
    for group in payload["groups"]:
        if group["scheme"] == "bip39" and group.get("passphrase"):
            phrase_copy = getpass.getpass("Enter the separately recorded BIP39 passphrase (hidden): ")
            if not hmac.compare_digest(phrase_copy, group["passphrase"]):
                print("[FAILED] BIP39 passphrase does NOT match. This is critical for recovery.")
                return
    print("This samples seed words, not a full recovery test. Verify all words offline.")


def self_test():
    """Crypto dependency readiness test; deterministic input used only for TESTING."""
    load_crypto()
    from bip_utils import Bip39MnemonicValidator, MoneroMnemonicValidator
    seed = "abandon " * 11 + "about"
    assert Bip39MnemonicValidator().IsValid(seed)
    xmr_seed = generate_monero()
    assert len(xmr_seed.split()) == 25
    assert MoneroMnemonicValidator().IsValid(xmr_seed)
    for code, _, _, _ in COINS:
        info = derive_coin(code, xmr_seed if code == "XMR" else seed, "")
        if not isinstance(info["address"], str) or len(info["address"]) < 20:
            raise RuntimeError(f"Address generation failed for {code}")
        print(f"  [OK] {code:8} address: {info['address'][:12]}...")
    test = {"format": "VaultForge-Unlocked-v1", "groups": [], "wallets": [], "test": "encryption"}
    blob = encrypt_payload(test, "test password only - NOT a real key")
    assert decrypt_payload(blob, "test password only - NOT a real key") == test
    try:
        decrypt_payload(blob, "wrong password")
        raise AssertionError("Authentication unexpectedly accepted invalid password")
    except Exception as e:
        from cryptography.exceptions import InvalidTag
        if not isinstance(e, InvalidTag):
            raise
    print("[PASS] 30 chains, Monero native seed, encryption, authentication checks")


def menu():
    load_crypto()
    if len(COINS) != 30 or len(COIN_BY_CODE) != 30:
        raise RuntimeError("Coin catalog integrity failed")
    print("="*66)
    print(" VAULTFORGE  v1.0  |  Windows & Linux  |  30 Coins  |  OFFLINE")
    print("="*66)
    print("SOFTWARE wallet only. USB storage is NOT a hardware secure element.")
    print("Do not fund large amounts without an independent security review.")
    while True:
        print("\n1) Generate new encrypted wallet(s)\n2) List encrypted vault files\n3) Unlock and show receiving addresses\n4) Reveal recovery phrases (explicit confirmation)\n5) Verify recovery-phrase paper backup\n6) Change vault encryption password\n7) Exit")
        choice = input("Select: ").strip()
        try:
            if choice == "1":
                create_wallets()
            elif choice == "2":
                path = choose_storage()
                names = sorted(path.glob("*.vault"))
                print(f"Vault files at {path}:")
                for f in names:
                    if f.is_file() and not f.is_symlink():
                        print("  " + f.name)
                if not names:
                    print("  (none)")
            elif choice in ("3", "4", "5", "6"):
                path = pick_vault()
                payload = unlock(path)
                if choice == "3":
                    print_wallets(payload)
                elif choice == "4":
                    reveal_seed_groups(payload["groups"])
                elif choice == "5":
                    backup_check(payload)
                else:
                    print("Rotation does not alter seeds/addresses; it re-encrypts the same vault.")
                    password = new_password()
                    from vault_security import rotate_vault_with_backup
                    # This CLI path must also preserve an encrypted rollback copy.
                    backup_dir = input("Existing separate backup folder (absolute path): ").strip()
                    backup_folder = Path(backup_dir).expanduser()
                    if not backup_folder.is_absolute() or not backup_folder.is_dir():
                        raise ValueError("Choose an existing absolute backup folder")
                    backup_file = backup_folder / (path.stem + "_rollback_" + secrets.token_hex(6) + ".vault")
                    old_password = getpass.getpass("Existing vault password again (hidden): ")
                    rotate_vault_with_backup(path, old_password, password, backup_file)
                    print("[SAVED] Password changed after encrypted rollback backup. Keep the old backup password.")
            elif choice == "7":
                print("Goodbye. Eject removable storage safely.")
                return
            else:
                print("Choose a menu number.")
        except (ValueError, OSError, KeyError) as exc:
            print(f"[ERROR] {exc}")
        except KeyboardInterrupt:
            print("\nCanceled this operation.")


if __name__ == "__main__":
    try:
        if "--self-test" in sys.argv:
            self_test()
        else:
            menu()
    except RuntimeError as err:
        print(f"[FATAL] {err}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nCanceled.")
        sys.exit(130)
