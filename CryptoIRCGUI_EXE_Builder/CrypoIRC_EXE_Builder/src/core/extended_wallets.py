"""Backward-compatible enriched vault creation. Keys are created separately by default.

This writes the original VaultForge-Unlocked-v1 payload into the unchanged AES-GCM
Argon2id .vault file container, so legacy decryptors can read its format.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
from . import vaultforge as vf
from .assets import ASSETS


def create_vaults(folder: str, assets: list[str], count: int, words: int, password: str,
                  bip39_extra: str = '', strategy: str = 'Separate seed per asset',
                  import_seed: str = '', account_index: int = 0) -> list[str]:
    if not isinstance(count, int) or not 1 <= count <= 20: raise ValueError('Choose 1–20 sets')
    if words not in (12,24): raise ValueError('BIP39 supports 12 or 24 words')
    if len(password) < 14: raise ValueError('Encryption password requires 14+ characters')
    if not isinstance(account_index,int) or not 0 <= account_index <= 100: raise ValueError('Invalid account index')
    assets=list(dict.fromkeys(assets))
    if not assets or len(assets)>50 or any(a not in ASSETS for a in assets): raise ValueError('Select valid supported crypto assets')
    if strategy not in ('Separate seed per asset','Shared BIP39 seed (advanced)'):
        raise ValueError('Unknown seed generation strategy')
    if import_seed and (count != 1 or len(assets) != 1):
        raise ValueError('Recovery import must restore one selected asset and one set at a time')
    vf.load_crypto()
    if import_seed:
        import_seed=vf.validate_phrase('monero' if assets[0]=='XMR' else 'bip39',import_seed)
    folder_path=vf.secure_dir(Path(folder).expanduser().resolve())
    created=[]
    for _ in range(count):
        groups=[]; wallets=[]; shared_phrase=None; shared_idx=None
        for code in assets:
            asset=ASSETS[code]
            if asset.base_coin=='XMR':
                phrase=import_seed or vf.generate_monero()
                idx=len(groups)
                groups.append({'scheme':'monero','mnemonic':phrase,'passphrase':'', 'asset':code})
            elif strategy=='Shared BIP39 seed (advanced)' and not import_seed:
                if shared_phrase is None:
                    shared_phrase=vf.generate_bip39(words)
                    shared_idx=len(groups)
                    groups.append({'scheme':'bip39','mnemonic':shared_phrase,'passphrase':bip39_extra,'asset':'shared','assets':[a for a in assets if a!='XMR']})
                phrase=shared_phrase
                idx=shared_idx
            else:
                phrase=import_seed or vf.generate_bip39(words)
                idx=len(groups)
                groups.append({'scheme':'bip39','mnemonic':phrase,'passphrase':bip39_extra,'asset':code})
            # Token's receiving address is ALWAYS derived by underlying chain's
            # native address method. No invented USDT/USD key derivation exists.
            wallet=vf.derive_coin(asset.base_coin,phrase,bip39_extra if asset.base_coin!='XMR' else '',account=account_index)
            wallet.update({'coin':code,'network':asset.network,'family':asset.category,
                           'generation_method':asset.method,'underlying_coin':asset.base_coin,
                           'seed_group':idx,'account_index':account_index,'warning':asset.note})
            wallets.append(wallet)
        payload={'format':'VaultForge-Unlocked-v1','created_utc':datetime.now(timezone.utc).isoformat(),
                 'wallets':wallets,'groups':groups,
                 'warnings':['Experimental software wallet, not an isolated hardware signer',
                             'Each token requires the correct blockchain and independently verified token contract',
                             'Test restore and validate receiving address with official wallet before depositing funds']}
        created.append(str(vf.write_new_vault(folder_path,payload,password)))
    return created
