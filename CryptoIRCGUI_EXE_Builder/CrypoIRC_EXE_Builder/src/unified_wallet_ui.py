"""Unified Wallets GUI: signer-bound public accounts, network probes, never seed handling."""
from __future__ import annotations
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from dataclasses import replace

from unified_wallet import (
    Account, UnifiedAccountRegistry, account_from_record, from_vault_rows, from_watch_rows,
    register_evm_keystore, register_bitcoin_core, register_monero_rpc,
    inspect_evm_account, inspect_btc_account, inspect_xmr_account, inspect_vault_evm_account,
    EVM_NETWORKS,
)
from wallet_funding import FundingTarget

BG='#07060b'; CARD='#15101e'; GREEN='#47fca3'; MUTED='#a39ab6'; WARN='#ff707a'; PURPLE='#b363ff'


class UnifiedWalletUI:
    def _uw_accounts(self) -> list[Account]:
        entries=UnifiedAccountRegistry().list()
        for path,rows in self.public_unlocked.items():
            entries.extend(from_vault_rows(path,rows))
        entries.extend(from_watch_rows(self.watch))
        return entries

    def page_unified_wallets(self):
        self.head('Unified Wallet Engine / v3.3',
            'One public account list across 30 coins and tokens, Bitcoin Core, EVM keystores, Monero wallet RPC and unlocked VaultForge vaults. '
            'A listed address is NOT proof of spendability or recovery.')
        p=tk.Frame(self.content,bg=CARD,padx=14,pady=13);p.pack(fill='x',pady=6)
        tk.Label(p,text='01 / LINK EXISTING SIGNING BACKEND',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        row=tk.Frame(p,bg=CARD);row.pack(fill='x',pady=9)
        for title,func in (
            ('BITCOIN CORE',self._uw_add_btc),('EVM KEYSTORE',self._uw_add_evm),
            ('MONERO RPC',self._uw_add_xmr),('UNLOCK .VAULT',lambda:self.show('Wallets')),
        ):
            ttk.Button(row,text=title,command=func,style='Accent.TButton').pack(side='left',padx=(0,8))
        tk.Label(p,text='Only public wallet metadata and local file paths are remembered. Passwords, RPC cookies, mnemonics, signing keys, live verification and balances are never stored in this registry.',
                 bg=CARD,fg=MUTED,wraplength=900,justify='left').pack(anchor='w')
        p2=tk.Frame(self.content,bg=CARD,padx=14,pady=12);p2.pack(fill='x',pady=7)
        tk.Label(p2,text='02 / WALLET ACCOUNTS AND NETWORK IDENTITY',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tree=ttk.Treeview(p2,columns=('asset','network','kind','status'),show='headings',height=11,selectmode='browse')
        for col,width in [('asset',100),('network',135),('kind',165),('status',410)]:
            tree.heading(col,text=col.upper());tree.column(col,width=width,stretch=col=='status')
        tree.pack(fill='x',pady=10)
        self.uw_tree=tree
        self._uw_current={}
        self._uw_verified={}
        self.uw_text=tk.StringVar(value='Choose an account to see its FULL public address and verification status.')
        self.uw_address=tk.StringVar(value='')
        tk.Label(p2,textvariable=self.uw_text,bg=CARD,fg=PURPLE,justify='left',wraplength=950).pack(anchor='w',pady=7)
        ttk.Entry(p2,textvariable=self.uw_address,state='readonly',font=('Consolas',10)).pack(fill='x',pady=(1,8))
        tools=tk.Frame(p2,bg=CARD);tools.pack(fill='x')
        for name,func in [
            ('VERIFY CONNECTION & BALANCE',self._uw_probe),('COPY ADDRESS',self._uw_copy),
            ('ADD MONEY → ACCOUNT',self._uw_fund),('OPEN SEND WORKFLOW',self._uw_send),
            ('CHAIN BALANCE / READ ONLY',self._uw_open_chain),
            ('REMOVE SAVED LINK',self._uw_remove),('REFRESH LIST',self._uw_reload),
        ]:
            ttk.Button(tools,text=name,command=func).pack(side='left',padx=(0,6),pady=3)
        tree.bind('<<TreeviewSelect>>',lambda _:self._uw_selected())
        self._uw_reload()
        p3=tk.Frame(self.content,bg=CARD,padx=14,pady=11);p3.pack(fill='x',pady=7)
        tk.Label(p3,text='03 / RECOVERY / FUNDING SAFETY',bg=CARD,fg=WARN,font=('Consolas',11,'bold')).pack(anchor='w')
        tk.Label(p3,text='An unlocked .vault does NOT become a Bitcoin Core, Monero or EVM keystore signer automatically. '
                 'BTC Core accounts may be verified against Core ownership; keystore headers do NOT prove the password is known; '
                 'Monero RPC addresses do NOT prove the wallet can spend. Independent restore-and-spend tests remain mandatory. '
                 'On-chain funding requires the exact network and asset.',
                 bg=CARD,fg=MUTED,justify='left',wraplength=1000).pack(anchor='w',pady=5)

    def _uw_reload(self, selected=None):
        if not hasattr(self,'uw_tree') or not self.uw_tree.winfo_exists():return
        try:accounts=self._uw_accounts()
        except (OSError,ValueError,TypeError) as exc:
            messagebox.showerror('Account registry','Public account list unavailable or invalid. No wallet was modified.',parent=self.root)
            return
        old=selected or (self.uw_tree.selection()[0] if self.uw_tree.selection() else '')
        self._uw_current={a.id:a for a in accounts}
        self._uw_verified={}
        for iid in self.uw_tree.get_children():self.uw_tree.delete(iid)
        for a in accounts:
            self.uw_tree.insert('','end',iid=a.id,values=(a.asset,a.network,a.kind,a.status))
        if old in self._uw_current:
            self.uw_tree.selection_set(old);self.uw_tree.see(old)
            self._uw_selected()
        else:
            self.uw_text.set(f'{len(accounts)} public accounts · no signer verification in this session')
            self.uw_address.set('')

    def _uw_chosen(self) -> Account | None:
        select=self.uw_tree.selection() if hasattr(self,'uw_tree') else ()
        return self._uw_current.get(select[0]) if select else None

    def _uw_selected(self):
        acc=self._uw_chosen()
        if not acc:return
        checked=self._uw_verified.get(acc.id,acc)
        self.uw_address.set(acc.address)
        self.uw_text.set(f'{acc.label} | {acc.asset} | {acc.network} | {acc.kind}\n'
                         f'{checked.status} — {checked.details or "No live signer verification performed."}')

    def _uw_open_chain(self):
        acc=self._uw_chosen()
        if acc is None:return
        if acc.asset not in ('LTC','DOGE','BCH','SOL','TRX','XRP'):
            messagebox.showwarning('Not supported by chain reader',
                'Select one of LTC, DOGE, BCH, SOL, TRX or XRP.',parent=self.root);return
        # Carry only the public address and asset. Network must be reselected;
        # a vault's address cannot prove which blockchain endpoint is correct.
        self._cx_selected=(acc.asset,acc.address)
        self.show('Chain Expansion')

    def _uw_copy(self):
        acc=self._uw_chosen()
        if not acc:return
        self.root.clipboard_clear();self.root.clipboard_append(acc.address)
        self.status.set('PUBLIC ADDRESS COPIED — verify exact receiving chain and address before funding')

    def _uw_add_btc(self):
        network=simpledialog.askstring('Bitcoin network','Enter regtest or main (main spends REAL BTC):',
                                       initialvalue='regtest',parent=self.root)
        if network is None:return
        network=network.strip()
        if network not in ('regtest','main'):
            messagebox.showerror('Bitcoin network','Only regtest or main allowed.',parent=self.root);return
        wallet=simpledialog.askstring('Core wallet name','Loaded Bitcoin Core wallet name:',parent=self.root)
        if not wallet:return
        default_port='18443' if network=='regtest' else '8332'
        url=simpledialog.askstring('Local Core node','Bitcoin Core loopback RPC URL:',
                                  initialvalue='http://127.0.0.1:'+default_port,parent=self.root)
        if not url:return
        default_cookie=str(Path.home()/('.bitcoin/regtest/.cookie' if network=='regtest' else '.bitcoin/.cookie'))
        if os.name=='nt': default_cookie=str(Path.home()/('AppData/Roaming/Bitcoin/regtest/.cookie' if network=='regtest' else 'AppData/Roaming/Bitcoin/.cookie'))
        cookie=filedialog.askopenfilename(title='Select Bitcoin Core RPC COOKIE (not imported or saved)',initialdir=str(Path(default_cookie).parent),parent=self.root)
        if not cookie:return
        if network=='main' and not messagebox.askyesno('REAL BTC MAINNET',
            'This selects Bitcoin MAINNET. Generate a NEW Core-owned receiving address?\nDo not fund until independent wallet recovery is tested.',parent=self.root):return
        def work():
            from btc_phase1 import BitcoinPhaseOne,NodeConfig
            svc=BitcoinPhaseOne(NodeConfig(url,cookie,network))
            addr=svc.receiving_address(wallet) # verifies Core ismine and not watch-only
            candidate=register_bitcoin_core(wallet,network,addr)
            return inspect_btc_account(candidate,url,cookie)
        def done(a):
            UnifiedAccountRegistry().add(a)
            self._uw_reload(a.id)
            self._uw_verified[a.id]=a
            self._uw_selected()
            self.status.set('BITCOIN CORE ADDRESS LINKED — BACKUP/RESTORE STILL UNVERIFIED')
        self.run_job(work,done,'Checking Core ownership and issuing a new receive address...')

    def _uw_add_evm(self):
        network=simpledialog.askstring('EVM chain','Exact EVM network code (SEPOLIA, ETH, BNB, POL, ARB, OP, BASE, etc.):',
                                      initialvalue='SEPOLIA',parent=self.root)
        if network is None:return
        network=network.strip().upper()
        if network not in EVM_NETWORKS:
            messagebox.showerror('Unsupported chain','Choose a supported EVM network code.',parent=self.root);return
        path=filedialog.askopenfilename(title='Select encrypted Ethereum V3 keystore',parent=self.root)
        if not path:return
        def work():return register_evm_keystore(path,network)
        def done(a):
            UnifiedAccountRegistry().add(a)
            self._uw_reload(a.id)
            self.uw_text.set('Encrypted keystore address linked. No secret was opened. Verify RPC before using it.')
        self.run_job(work,done,'Checking public V3 keystore address...')

    def _uw_add_xmr(self):
        network=simpledialog.askstring('Monero network','Enter stagenet or mainnet:',initialvalue='stagenet',parent=self.root)
        if network is None:return
        network=network.strip()
        if network not in ('stagenet','mainnet'):
            messagebox.showerror('Monero network','Select stagenet or mainnet.',parent=self.root);return
        if network=='mainnet' and not messagebox.askyesno('REAL XMR MAINNET','Link mainnet Monero wallet RPC? Independently validate recovery before funding.',parent=self.root):return
        url=self.xmr_url.get();user=self.xmr_user.get();pw=self.xmr_password.get()
        def work():
            from xmr_phase3 import MoneroPhaseThree
            svc=MoneroPhaseThree(url,user,pw,network=network)
            h=svc.health()
            return register_monero_rpc(network,h['address'])
        def done(a):
            UnifiedAccountRegistry().add(a)
            self._uw_reload(a.id)
            self.status.set('MONERO RPC LINKED — SPENDABILITY AND INDEPENDENT RECOVERY NOT VERIFIED')
        self.run_job(work,done,'Checking Monero wallet RPC network and address...')

    def _uw_probe(self):
        acc=self._uw_chosen()
        if not acc:return
        if acc.kind not in ('btc_core','evm_keystore','xmr_rpc','vault'):
            self.uw_text.set('NO SPENDABILITY PROOF — watch-only addresses have no signing key.')
            return
        if acc.kind=='btc_core':
            network=acc.network
            default='http://127.0.0.1:'+('18443' if network=='regtest' else '8332')
            url=simpledialog.askstring('Bitcoin Core RPC','Loopback URL for '+network,initialvalue=default,parent=self.root)
            if not url:return
            cookie=filedialog.askopenfilename(title='Select Bitcoin Core RPC cookie',parent=self.root)
            if not cookie:return
            job=lambda:inspect_btc_account(acc,url,cookie)
        elif acc.kind=='evm_keystore':
            url=simpledialog.askstring('EVM RPC','Trusted HTTPS or local RPC URL for '+acc.network,
                                       initialvalue='',parent=self.root)
            if not url:return
            job=lambda:inspect_evm_account(acc,url)
        elif acc.kind=='xmr_rpc':
            url=self.xmr_url.get();user=self.xmr_user.get();password=self.xmr_password.get()
            job=lambda:inspect_xmr_account(acc,url,user,password)
        else:
            from asset_capabilities import EVM_ALIASES,TOKEN_EVM
            chain=EVM_ALIASES.get(acc.asset) or TOKEN_EVM.get(acc.asset)
            if not chain:
                messagebox.showwarning('No supported signer',
                    'This generated vault asset has no supported in-app EVM signing path. Register a compatible external wallet only after independently checking recovery.',parent=self.root);return
            pw=simpledialog.askstring('Recheck encrypted vault','Vault password (not stored):',show='●',parent=self.root)
            if not pw:return
            url=simpledialog.askstring('Live EVM balance','Trusted chain-matched RPC for '+chain,
                                       initialvalue='',parent=self.root)
            if not url:return
            job=lambda:inspect_vault_evm_account(acc,pw,url)
        def done(verified):
            if acc.id not in self._uw_current:return
            self._uw_verified[acc.id]=verified
            self.uw_tree.set(acc.id,'status',verified.status)
            self._uw_selected()
        self.run_job(job,done,'Verifying public account identity and balance against chain RPC...')

    def _uw_fund(self):
        acc=self._uw_chosen()
        if not acc:return
        a=self._uw_verified.get(acc.id)
        if a is None or not a.can_receive:
            messagebox.showwarning('Unverified receiving address',
                'Verify this account through its connected signer and exact network first. '
                'Unverified vault/watch-only addresses cannot enter this shortcut.',parent=self.root);return
        if acc.kind=='vault':
            messagebox.showwarning('Recovery not verified','Generated .vault accounts require an independent recovery-and-spend test before using this funding shortcut. Use a verified signer account instead.',parent=self.root);return
        if acc.network in ('regtest','stagenet','SEPOLIA'):
            messagebox.showwarning('Test network','Fiat purchase providers cannot fund a test-network address.',parent=self.root);return
        if acc.kind=='evm_keystore' and acc.network!='ETH':
            messagebox.showwarning('Provider network eligibility',
                'This EVM network has not been validated with the checkout provider. '
                'Funding shortcut is limited to ETH mainnet until provider support is confirmed.',parent=self.root);return
        network={'BTC':'Bitcoin mainnet','XMR':'Monero mainnet','ETH':'Ethereum mainnet'}.get(acc.asset,acc.network)
        self._hub_target=FundingTarget(acc.asset,acc.address,network,acc.kind,acc.label,
                                       ownership_verified=a.signer_proven)
        self.show('Phase 4 Funding')

    def _uw_send(self):
        acc=self._uw_chosen()
        if not acc:return
        if acc.kind=='btc_core':page='BTC Phase 1'
        elif acc.kind=='evm_keystore':page='EVM Phase 2'
        elif acc.kind=='xmr_rpc':page='Monero Phase 3'
        else:
            messagebox.showwarning('No connected signer',
                 'This address has no verified signing route in Unified Wallets. '
                 'Do not assume you can spend funds from it.',parent=self.root);return
        if not messagebox.askyesno('Review signer',f'Open {page}?\nThe signing screen requires fresh network details and explicit authorization; it will NOT submit a transaction automatically.',parent=self.root):return
        self.show(page)
        # Transfer the public account identity only; no signing session or
        # transaction authorization is carried across pages.
        if acc.kind=='btc_core':
            self.p1_network.set(acc.network)
            self.p1_url.set('http://127.0.0.1:'+('18443' if acc.network=='regtest' else '8332'))
            self.p1_wallet.set(acc.source)
            self.p1_status.set('Selected Core account from Unified Wallets. Recheck node, backup, and fee before any send.')
        elif acc.kind=='evm_keystore':
            self.p2_chain.set(acc.network)
            self.p2_keystore.set(acc.source)
            self._p23_set(self.p2_output,
                'Selected public source: '+acc.address+'\nNETWORK '+acc.network+
                '\nVerify network RPC, amount, gas and recipient before signing. No transfer has been prepared.')
        elif acc.kind=='xmr_rpc':
            self.p3_network.set(acc.network)
            self.p3_url.set('http://127.0.0.1:'+('38082' if acc.network=='stagenet' else '18082'))
            self._p23_set(self.p3_output,
                'Selected Monero public account: '+acc.address+
                '\nRecheck wallet RPC address and spendability before making any transaction.')

    def _uw_remove(self):
        acc=self._uw_chosen()
        if not acc:return
        if acc.kind in ('vault','watch_only'):
            messagebox.showwarning('Reference only','Remove unlocked vaults from Wallets or watch-only entries through the existing watch manager.',parent=self.root);return
        if not messagebox.askyesno('Unlink public account',
            'Forget this PUBLIC account reference? No wallet, keystore, blockchain funds or private data will be deleted.',parent=self.root):return
        UnifiedAccountRegistry().remove(acc.id)
        self._uw_reload()
