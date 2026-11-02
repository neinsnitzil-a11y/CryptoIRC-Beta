"""CRYPTO // NOCTURNE — modular account workflows, no simulated banking.

The styling is aesthetic only. Provider links do not create accounts, transfer
funds or authorize a payment. Cryptocurrency creation keeps the .vault format.
"""
from __future__ import annotations

import hmac
import os
import webbrowser
from pathlib import Path
from brand_theme import load_image, PURPLE, GREEN, RED
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from core import vaultforge as vf, fiat_ledger, fiat_registry
from core.assets import BASE, TOKENS, ASSETS, FIAT
from core.extended_wallets import create_vaults
from backend import read_vault
from recovery_flow import RecoveryBackupDialog

BG = '#07060b'
CARD = '#15101e'
CARD2 = '#1b1328'
FIELD = '#0c0914'
ACCENT = '#47fca3'
FG = '#f2edf9'
MUTED = '#a39ab6'
WARN = '#ff707a'
EDGE = '#3b2654'

FIAT_PROVIDERS = {
    'Offline encrypted ledger (manual records)': None,
    'Bank / ACH (existing account connection)': 'https://plaid.com/',
    'PayPal (existing PayPal account)': 'https://www.paypal.com/',
    'Stripe (approved merchant account)': 'https://dashboard.stripe.com/',
    'Square (approved merchant account)': 'https://squareup.com/dashboard/',
    'Wise (existing eligible account)': 'https://wise.com/',
    'Revolut (existing eligible account)': 'https://www.revolut.com/',
}


def validate_storage_folder(selection: str, folder: str, usb_path: str = '') -> Path:
    """Make selection meaningful; prevent mistakenly writing PC files for USB."""
    if selection not in ('This PC', 'USB / external drive', 'Custom directory'):
        raise ValueError('Unknown storage choice')
    p = Path(folder).expanduser()
    if not p.is_absolute():
        raise ValueError('Choose an absolute storage folder')
    p = p.resolve()
    if selection == 'USB / external drive':
        if not usb_path:
            raise ValueError('Choose a removable drive before continuing')
        drive = Path(usb_path).expanduser().resolve()
        if not drive.is_dir() or (drive != p and drive not in p.parents):
            raise ValueError('Storage folder must be on the selected mounted USB drive')
    return p


def validated_wallet_parameters(family: str, asset_code: str, count: str,
                                length: str, account: str, restoring: bool) -> tuple[int,int,int]:
    if family not in ('Cryptocurrency','Stablecoin'):
        raise ValueError('Fiat accounts must never be passed to the key generator')
    if asset_code not in ASSETS or ASSETS[asset_code].category != family:
        raise ValueError('Selected asset does not belong to this wallet category')
    n, words, idx = int(count), int(length), int(account)
    if n < 1 or n > 20 or words not in (12,24) or idx < 0 or idx > 100:
        raise ValueError('Invalid wallet generation parameters')
    if restoring and n != 1:
        raise ValueError('Recovery creates one wallet at a time')
    return n, words, idx


class ProfessionalUI:
    """Added last in MRO to override old mixed account-creation screens."""

    def _titleline(self, text: str, sub: str = ''):
        row = tk.Frame(self.content,bg=BG)
        row.pack(fill='x',pady=(0,17))
        tk.Label(row,text='// '+text.upper(),bg=BG,fg=ACCENT,
                 font=('Consolas',21,'bold'),anchor='w').pack(anchor='w')
        if sub:
            tk.Label(row,text=sub,bg=BG,fg=MUTED,anchor='w',justify='left',
                     font=('Segoe UI',10),wraplength=950).pack(anchor='w',pady=(5,0))

    def _area(self,parent=None, title='', subtitle='', pad=18):
        box=tk.Frame(parent or self.content,bg=CARD,highlightbackground=EDGE,
                     highlightthickness=1,padx=pad,pady=pad)
        box.pack(fill='x',pady=(0,12))
        if title:
            tk.Label(box,text=title.upper(),bg=CARD,fg=ACCENT,
                     font=('Consolas',11,'bold'),anchor='w').pack(anchor='w',pady=(0,4))
        if subtitle:
            tk.Label(box,text=subtitle,bg=CARD,fg=MUTED,font=('Segoe UI',9),
                     wraplength=900,justify='left',anchor='w').pack(anchor='w',pady=(0,12))
        return box

    def _item(self,parent,label,var,values=None,secret=False):
        wrap=tk.Frame(parent,bg=parent.cget('bg'))
        wrap.pack(fill='x',pady=(3,10))
        tk.Label(wrap,text=label.upper(),bg=wrap.cget('bg'),fg=MUTED,
                 font=('Consolas',9),anchor='w').pack(anchor='w',pady=(0,5))
        if values is None:
            obj=ttk.Entry(wrap,textvariable=var,show='●' if secret else '')
        else:
            obj=ttk.Combobox(wrap,textvariable=var,values=values,state='readonly')
        obj.pack(fill='x')
        return obj

    def _noteprof(self,parent,msg,warn=False):
        tk.Label(parent,text=msg,fg=WARN if warn else MUTED,bg=parent.cget('bg'),
                 wraplength=870,justify='left',font=('Segoe UI',9)).pack(anchor='w',pady=(6,7))

    def _rowbuttons(self,parent,items):
        r=tk.Frame(parent,bg=parent.cget('bg'));r.pack(fill='x',pady=(8,0))
        for name,callback,primary in items:
            ttk.Button(r,text=name,command=callback,
                       style='Accent.TButton' if primary else 'TButton').pack(side='left',padx=(0,9))

    def page_dashboard(self):
        self._titleline('The Shadow Terminal', 'CRYPTO   /   NOCTURNE v4.4   /   PRIVATE FINANCIAL WORKSPACE')
        splash=tk.Frame(self.content,bg='#110b1a',highlightbackground='#603488',highlightthickness=1)
        splash.pack(fill='x',pady=(0,16))
        green_rail=tk.Frame(splash,bg=ACCENT,width=4)
        green_rail.pack(side='left',fill='y')
        art=load_image('skull_purple.png',(225,225))
        if art is not None:
            self._brand_images['hero_skull']=art
            tk.Label(splash,image=art,bg='#110b1a',bd=0).pack(side='right',padx=(12,25),pady=5)
        text_column=tk.Frame(splash,bg='#110b1a',padx=23,pady=24)
        text_column.pack(side='left',fill='both',expand=True)
        tk.Label(text_column,text='◈  CRYPTO   //   NOCTURNE',bg='#110b1a',fg=PURPLE,
                 font=('Consolas',11,'bold')).pack(anchor='w')
        tk.Label(text_column,text='PRIVATE BY DESIGN.\nVISIBLE BY CHOICE.',bg='#110b1a',fg=FG,
                 font=('Consolas',22,'bold'),justify='left').pack(anchor='w',pady=(10,13))
        tk.Label(text_column,text='SELF-CUSTODY VAULTS  /  FIAT ACCOUNTS  /  ENCRYPTED CHAT',
                 bg='#110b1a',fg=ACCENT,font=('Consolas',9,'bold'),wraplength=570,
                 justify='left').pack(anchor='w')
        tk.Label(text_column,text='Tor onion artwork is branding. Anonymity requires a separately verified Tor connection.',
                 bg='#110b1a',fg=MUTED,font=('Segoe UI',9),wraplength=530,
                 justify='left').pack(anchor='w',pady=(11,0))
        self._rowbuttons(text_column,[('CREATE ACCOUNT',lambda:self.show('Create Wallet'),True),
                                      ('PRIVATE CHAT',lambda:self.show('Internet Chat'),False)])
        hero=self._area(title='01 / SYSTEM TELEMETRY',
                        subtitle='Local counts and connection states. No simulated fiat balances.')
        head=tk.Frame(hero,bg=CARD);head.pack(fill='x',pady=7)
        for name,value in (
            ('ENCRYPTED VAULT FILES',str(len(self.vault_paths))),
            ('WATCH-ONLY ADDRESSES',str(len(self.watch))),
            ('FIAT LEDGER FILES',str(len(fiat_registry.load()))),
            ('VERIFIED FIAT BALANCE','NOT LINKED')):
            item=tk.Frame(head,bg=FIELD,padx=13,pady=13,highlightbackground=EDGE,highlightthickness=1)
            item.pack(side='left',fill='x',expand=True,padx=(0,9))
            tk.Label(item,text=name,bg=FIELD,fg=MUTED,font=('Consolas',8),anchor='w').pack(anchor='w')
            tk.Label(item,text=value,bg=FIELD,fg=ACCENT if value!='NOT LINKED' else WARN,
                     font=('Consolas',19,'bold'),anchor='w').pack(anchor='w',pady=(6,0))
        self._noteprof(hero,'VAULT KEYS ARE LOCAL SOFTWARE KEYS. Real fiat balances require verified financial-provider integration.',warn=True)
        tools=self._area(title='02 / ACCOUNT SYSTEMS',subtitle='Select the right creation protocol. Fiat accounts never use seed phrases.')
        for text,page,desc in (
            ('01   FIAT ACCOUNTS','Fiat Accounts','Link a provider or use an encrypted bookkeeping ledger.'),
            ('02   CRYPTO VAULT','Crypto Vault','Encrypted keys, recovery and computer or USB storage.'),
            ('03   STABLECOINS','Stablecoins','Network-aware USDT, USDC and DAI token addresses.'),
        ):
            row=tk.Frame(tools,bg=CARD2,padx=12,pady=11)
            row.pack(fill='x',pady=4)
            tk.Label(row,text=text,bg=CARD2,fg=FG,font=('Consolas',11,'bold')).pack(side='left')
            ttk.Button(row,text='OPEN  ›',command=lambda p=page:self.show(p),style='Purple.TButton').pack(side='right')
            tk.Label(row,text=desc,bg=CARD2,fg=MUTED,font=('Segoe UI',9)).pack(side='right',padx=20)
        quick=self._area(title='03 / QUICK OPERATIONS',subtitle='Sending and funding require compatible wallet and provider services.')
        self._rowbuttons(quick,[('MONEY HUB — ALL WALLETS',lambda:self.show('Money Hub'),True),('LIVE CRYPTO — BTC / ETH / XMR',lambda:self.show('Live Crypto'),True),
                                ('ADD MONEY',lambda:self.show('Wallet Funding'),False),
                                ('SEND',lambda:self.show('Send'),False),
                                ('RECEIVE',lambda:self.show('Receive'),False),
                                ('WORLDWIDE CHAT',lambda:self.show('Internet Chat'),False)])
        self._noteprof(quick,'RELEASE STATUS: EXPERIMENTAL. No real fiat transfers or third-party security audit completed.',warn=True)
        return

    def page_create_wallet(self):
        self._titleline('Choose Account Type','Select the system you want. Fiat accounts do not use seed phrases; blockchain wallets do.')
        banner=tk.Frame(self.content,bg='#1b1328',highlightthickness=1,highlightbackground='#64378a',padx=17,pady=12)
        banner.pack(fill='x',pady=(0,17))
        icon=load_image('tor_round.png',(48,48))
        if icon is not None:
            self._brand_images['account_tor']=icon
            tk.Label(banner,image=icon,bg='#1b1328',bd=0).pack(side='left',padx=(0,13))
        tk.Label(banner,text='SELECT FINANCIAL RAIL  /  ISOLATED ACCOUNT SETUP',
                 bg='#1b1328',fg=PURPLE,font=('Consolas',10,'bold'),wraplength=780,
                 justify='left').pack(anchor='w')
        tk.Label(banner,text='Tor-style appearance is not a privacy guarantee. No keys are generated for fiat ledgers.',
                 bg='#1b1328',fg=MUTED,font=('Segoe UI',9),wraplength=790,
                 justify='left').pack(anchor='w',pady=(5,0))

        for title,desc,page,warning in (
            ('01   FIAT / REGULAR CURRENCY',
             'USD · GBP · EUR · INR · 164 ISO codes. Link an eligible payment provider or create an encrypted manual ledger.',
             'Fiat Accounts','No BIP39 words, crypto keys, or blockchain address.'),
            ('02   CRYPTOCURRENCY VAULT',
             'BTC · XMR · ETH · LTC · SOL and more. Independent key generation, PC/USB storage and restoration.',
             'Crypto Vault','Private keys remain local. Restoration and spending need independent verification.'),
            ('03   STABLECOINS / TOKENS',
             'USDT · USDC · DAI. Choose the underlying blockchain before creating a receiving wallet.',
             'Stablecoins','A stablecoin does not have its own separate seed algorithm.'),
        ):
            block=self._area(title=title,subtitle=desc)
            self._noteprof(block,warning)
            ttk.Button(block,text='OPEN WORKFLOW  ›',style='Accent.TButton',
                       command=lambda p=page:self.show(p)).pack(anchor='w',pady=(6,0))

    def _account_storage(self,parent):
        storage=self._area(parent,title='02 / ENCRYPTED STORAGE',subtitle='A USB wallet is removable software storage, not an isolated hardware signer.')
        self.p_storage=tk.StringVar(value='This PC')
        cb=self._item(storage,'Storage device',self.p_storage,['This PC','USB / external drive','Custom directory'])
        self.p_usb=tk.StringVar(value='No USB selected')
        self.p_usb_map={}
        usb=self._item(storage,'Removable volume',self.p_usb,['No USB selected'])
        self.p_folder=tk.StringVar(value=str(Path.home()/'CryptoWallets'))
        self._item(storage,'Destination folder',self.p_folder)
        def refresh():
            try:
                pairs=vf.discover_usb()
                self.p_usb_map={str(p)+'  ['+str(name)+']':str(p) for p,name in pairs}
                values=list(self.p_usb_map)
                usb.configure(values=values if values else ['No USB detected'])
                self.p_usb.set(values[0] if values else 'No USB detected')
                select_usb()
            except Exception as err:
                messagebox.showerror('Drive scan failed',type(err).__name__)
        def select_usb(*_):
            selected=self.p_usb_map.get(self.p_usb.get())
            if selected and self.p_storage.get()=='USB / external drive':
                self.p_folder.set(str(Path(selected)/'CryptoWallets'))
        def changed(*_):
            if self.p_storage.get()=='This PC':
                self.p_folder.set(str(Path.home()/'CryptoWallets'))
            elif self.p_storage.get()=='USB / external drive':
                refresh()
        cb.bind('<<ComboboxSelected>>',changed)
        usb.bind('<<ComboboxSelected>>',select_usb)
        self._rowbuttons(storage,[('REFRESH USB',refresh,False),('BROWSE DIRECTORY',lambda:self._browse_prof(),False)])
        return storage

    def _browse_prof(self):
        path=filedialog.askdirectory(title='Choose encrypted storage destination')
        if path:
            self.p_folder.set(path)

    def _show_wallet_form(self,family):
        title='CRYPTO VAULT' if family=='Cryptocurrency' else 'STABLECOIN / TOKEN VAULT'
        subtitle=('Create a native self-custody software wallet. Each chain has distinct recovery and signing rules.'
                  if family=='Cryptocurrency' else
                  'Select token and underlying blockchain. The token uses that chain’s address and private keys.')
        self._titleline(title,subtitle)
        vault_tag=tk.Frame(self.content,bg='#110b1a',highlightbackground='#493066',highlightthickness=1,padx=12,pady=5)
        vault_tag.pack(fill='x',pady=(0,12))
        skull_mark=load_image('skull_green.png',(63,72))
        if skull_mark is not None:
            self._brand_images['vault_skull']=skull_mark
            tk.Label(vault_tag,image=skull_mark,bg='#110b1a',bd=0).pack(side='left')
        text_tag=tk.Frame(vault_tag,bg='#110b1a')
        text_tag.pack(side='left',padx=(10,0))
        tk.Label(text_tag,text='SELF-CUSTODY / ENCRYPTED KEYSTORE',bg='#110b1a',fg=ACCENT,
                 font=('Consolas',10,'bold')).pack(anchor='w')
        tk.Label(text_tag,text='NO BANK ACCOUNT IS CREATED.  WALLET STORAGE ≠ HARDWARE ISOLATION.',
                 bg='#110b1a',fg=MUTED,font=('Consolas',9)).pack(anchor='w',pady=(5,0))
        self.p_family=family
        first=self._area(title='01 / ASSET CONFIGURATION',subtitle='Asset/network selection cannot be overridden by the shared fiat-account form.')
        if family=='Cryptocurrency':
            all_codes=list(BASE)
            self.p_coin=tk.StringVar(value=all_codes[0])
            coin_cb=self._item(first,'Cryptocurrency',self.p_coin,all_codes)
            self.p_code=tk.StringVar(value=self.p_coin.get())
            self.p_net=tk.StringVar(value=ASSETS[self.p_coin.get()].network)
            self._item(first,'Underlying chain',self.p_net,[self.p_net.get()]).configure(state='disabled')
            def update(*_):
                code=self.p_coin.get();self.p_code.set(code)
                self.p_net.set(ASSETS[code].network)
                method.set(ASSETS[code].method)
            coin_cb.bind('<<ComboboxSelected>>',update)
        else:
            symbols=sorted({t.code.split('-')[0] for t in TOKENS})
            self.p_coin=tk.StringVar(value='USDT')
            coin_cb=self._item(first,'Stablecoin',self.p_coin,symbols)
            self.p_net=tk.StringVar()
            net_cb=self._item(first,'Blockchain / token standard',self.p_net,[])
            self.p_code=tk.StringVar(value='')
            def update_networks(*_):
                matches=[t for t in TOKENS if t.code.split('-')[0]==self.p_coin.get()]
                opts=[t.network for t in matches]
                net_cb.configure(values=opts)
                self.p_net.set(opts[0] if opts else '')
                update_code()
            def update_code(*_):
                matches=[t for t in TOKENS if t.code.split('-')[0]==self.p_coin.get() and t.network==self.p_net.get()]
                self.p_code.set(matches[0].code if matches else '')
                if matches:
                    method.set(matches[0].method)
                    network_note.set(matches[0].note)
            coin_cb.bind('<<ComboboxSelected>>',update_networks)
            net_cb.bind('<<ComboboxSelected>>',update_code)
        method=tk.StringVar()
        network_note=tk.StringVar(value='')
        self._item(first,'Wallet generation method',method).configure(state='readonly')
        if family=='Stablecoin':
            tk.Label(first,textvariable=network_note,bg=CARD,fg=WARN,
                     font=('Segoe UI',9),wraplength=800,justify='left').pack(anchor='w')
            update_networks()
        else:
            method.set(ASSETS[self.p_coin.get()].method)
        self._account_storage(self.content)
        opts=self._area(title='03 / RECOVERY & ENCRYPTION',subtitle='These controls apply ONLY to self-custodied blockchain wallets.')
        self.p_mode=tk.StringVar(value='Generate new wallet')
        self._item(opts,'Action',self.p_mode,['Generate new wallet','Restore MY existing recovery phrase'])
        self.p_words=tk.StringVar(value='24')
        self._item(opts,'BIP39 length (Monero uses native 25 words)',self.p_words,['12','24'])
        self.p_account=tk.StringVar(value='0')
        self._item(opts,'Derivation account',self.p_account,[str(i) for i in range(5)])
        self.p_count=tk.StringVar(value='1')
        self._item(opts,'Independent copies (1–20)',self.p_count,[str(i) for i in range(1,21)])
        self.p_extra=tk.StringVar()
        self._item(opts,'Optional BIP39 passphrase (advanced)',self.p_extra,secret=True)
        self.p_pw=tk.StringVar();self.p_confirm=tk.StringVar()
        self._item(opts,'Local encrypted vault password (14+ characters)',self.p_pw,secret=True)
        self._item(opts,'Confirm local vault password',self.p_confirm,secret=True)
        self._noteprof(opts,'WARNING: Never enter recovery words into websites, chat or provider connections. Test independent restore before funding.',True)
        self._rowbuttons(opts,[('GENERATE / RESTORE ENCRYPTED VAULT',self._submit_prof_wallet,True),
                               ('OPEN RECOVERY CENTER',lambda:self.show('Recovery'),False)])

    def page_crypto_vault(self):
        self._show_wallet_form('Cryptocurrency')

    def page_stablecoins(self):
        self._show_wallet_form('Stablecoin')

    def _submit_prof_wallet(self):
        try:
            code=self.p_code.get()
            restore=self.p_mode.get()=='Restore MY existing recovery phrase'
            count,words,idx=validated_wallet_parameters(self.p_family,code,self.p_count.get(),
                                                          self.p_words.get(),self.p_account.get(),restore)
            folder=validate_storage_folder(self.p_storage.get(),self.p_folder.get(),
                                            self.p_usb_map.get(self.p_usb.get(),''))
            pw=self.p_pw.get()
            if len(pw)<14 or not hmac.compare_digest(pw,self.p_confirm.get()):
                raise ValueError('Use a matching vault password of at least 14 characters')
            extra=self.p_extra.get()
            phrase=''
            if restore:
                if not messagebox.askyesno('SENSITIVE KEY IMPORT','Import only your own recovery phrase on a trusted computer. Continue?'):
                    return
                phrase=simpledialog.askstring('Private phrase — never stored unencrypted',
                        'Enter your complete recovery words. Do NOT paste secrets into chat:',
                        show='●',parent=self.root)
                if not phrase:return
                phrase=vf.validate_phrase('monero' if ASSETS[code].base_coin=='XMR' else 'bip39',phrase)
            if not messagebox.askyesno('VERIFY WALLET CONFIGURATION',
                    f'Asset: {code}\nChain: {ASSETS[code].network}\nVault copies: {count}\nStorage: {folder}\n\n'
                    'Experimental SOFTWARE wallet. Not a hardware wallet. No deposits until independent restore/address verification.'):
                return
            self.p_pw.set('');self.p_confirm.set('');self.p_extra.set('')
            def make_and_prepare_recovery():
                paths=create_vaults(str(folder),[code],count,words,pw,extra,
                                    'Separate seed per asset',phrase,idx)
                # Read ONLY vaults that were just written; use their actual
                # encrypted recovery data rather than generating a second seed.
                if restore:
                    return paths, []
                groups=[]
                for path in paths:
                    try:
                        groups.append(read_vault(path,pw)['groups'])
                    except Exception:
                        # Encrypted file already exists; preserve its path and
                        # offer password-protected recovery from Security.
                        groups.append(None)
                return paths, groups

            def finish(result):
                paths, group_sets=result
                for path in paths:
                    if path not in self.vault_paths:self.vault_paths.append(path)
                self.persist()
                if restore:
                    messagebox.showinfo('Wallet restored',
                        'Encrypted vault saved. The phrase you imported was not displayed again. '
                        'Verify its receiving address in trusted wallet software before depositing.')
                    self.show('Wallets')
                    return

                def next_backup(i):
                    if i >= len(paths):
                        self.show('Wallets')
                        return
                    def backed_up(sample_checked):
                        # Sample confirmation is NOT a complete cross-wallet restore.
                        if not sample_checked:
                            messagebox.showwarning('BACKUP NOT VERIFIED',
                                'The encrypted vault exists, but its paper recovery backup is NOT verified. '
                                'Use Security → REVEAL recovery phrases before funding.')
                        next_backup(i+1)
                    try:
                        if group_sets[i] is None:
                            raise RuntimeError('Recovery display unavailable')
                        RecoveryBackupDialog(self.root,group_sets[i],backed_up,
                                             number=i+1,total=len(paths))
                    except Exception:
                        # Creation already succeeded: never discard or overwrite it.
                        messagebox.showwarning('Private backup display unavailable',
                            'Vault created but recovery display could not open. '
                            'Go to Security → REVEAL recovery phrases and unlock the vault. '
                            'Do not deposit until the recovery backup is verified.')
                        self.show('Wallets')
                next_backup(0)
            self.run_job(make_and_prepare_recovery,finish,
                         'Creating encrypted '+self.p_family.lower()+' wallet...')
        except Exception as err:
            messagebox.showerror('WALLET CREATION BLOCKED',f'{type(err).__name__}: {str(err)[:300]}')

    def page_fiat_accounts(self):
        self._titleline('Fiat Accounts','Regular money uses financial institutions and payment rails, NOT blockchain seed phrases.')
        c=self._area(title='01 / FIAT ACCOUNT MODEL',
                     subtitle='Choose a legitimate provider connection for real money, or an offline encrypted ledger for manual tracking.')
        self.fiat_currency=tk.StringVar(value='USD')
        self._item(c,'National currency / ISO 4217',self.fiat_currency,[f'{code} — {label}' for code,label in FIAT])
        # dropdown permits complete ISO list, while default is a present value
        self.fiat_currency.set(next((f'{code} — {name}' for code,name in FIAT if code=='USD'),'USD'))
        self.fiat_type=tk.StringVar(value='Bank / ACH (existing account connection)')
        cb=self._item(c,'Account type / existing provider',self.fiat_type,list(FIAT_PROVIDERS))
        self.fiat_provider_frame=tk.Frame(c,bg=CARD)
        self.fiat_provider_frame.pack(fill='x',pady=(4,0))
        cb.bind('<<ComboboxSelected>>',lambda _:self._update_fiat_form())
        self._update_fiat_form()
        n=self._area(title='02 / SAFETY BOUNDARY',subtitle='Different from cryptocurrency wallets:')
        for msg in ('NO seed phrase, no BIP39 passphrase, no crypto derivation index.',
                    'A tracking ledger is NOT spendable money and creates no routing number.',
                    'Real accounts, payments, FX and deposits are established by approved providers only.',
                    'Bank credentials and full payment-card numbers are not collected by this application.'):
            tk.Label(n,text='▸ '+msg,bg=CARD,fg=FG,font=('Segoe UI',10),anchor='w',
                     justify='left',wraplength=850).pack(anchor='w',pady=5)

    def _update_fiat_form(self):
        for w in self.fiat_provider_frame.winfo_children():w.destroy()
        prov=self.fiat_type.get()
        if FIAT_PROVIDERS[prov] is None:
            self._noteprof(self.fiat_provider_frame,'This creates an encrypted OFFLINE accounting file, not a bank account.',True)
            self.f_label=tk.StringVar(value='My personal fiat ledger')
            self.f_folder=tk.StringVar(value=str(Path.home()/'CryptoWallets'))
            self.f_password=tk.StringVar();self.f_password2=tk.StringVar()
            self._item(self.fiat_provider_frame,'Ledger name',self.f_label)
            self._item(self.fiat_provider_frame,'Encrypted file storage',self.f_folder)
            self._rowbuttons(self.fiat_provider_frame,[('CHOOSE DIRECTORY',self._pick_fiat_dir,False)])
            self._item(self.fiat_provider_frame,'File encryption password',self.f_password,secret=True)
            self._item(self.fiat_provider_frame,'Confirm password',self.f_password2,secret=True)
            self._rowbuttons(self.fiat_provider_frame,[('CREATE OFFLINE LEDGER',self._create_prof_fiat,True),
                                                        ('IMPORT EXISTING',lambda:self.show('Fiat Ledger'),False)])
        else:
            self._noteprof(self.fiat_provider_frame,
                   'A provider account must already exist or be opened with that provider. There is no automatic in-app bank account generation.',True)
            self._rowbuttons(self.fiat_provider_frame,[('OPEN OFFICIAL PROVIDER WEBSITE',self._launch_fiat_provider,True),
                                                        ('CONFIGURE PAYMENT CONNECTIONS',lambda:self.show('Fiat Payments'),False),
                                                        ('VIEW LOCAL FIAT LEDGERS',lambda:self.show('Fiat Ledger'),False)])
            self._noteprof(self.fiat_provider_frame,
                   'Provider availability, credentials, supported countries and actual account access are not verified here.')

    def _pick_fiat_dir(self):
        p=filedialog.askdirectory(title='Choose encrypted ledger destination')
        if p:self.f_folder.set(p)

    def _launch_fiat_provider(self):
        url=FIAT_PROVIDERS.get(self.fiat_type.get())
        if url and messagebox.askyesno('Open external provider',
              'Open the official provider site in your browser?\n\nNo account or balance will be created inside CRYPTO.'):
            webbrowser.open(url)

    def _create_prof_fiat(self):
        try:
            code=self.fiat_currency.get().split(' — ')[0]
            if code not in dict(FIAT):raise ValueError('Choose a supported fiat code')
            if self.fiat_type.get()!='Offline encrypted ledger (manual records)':
                raise ValueError('Provider account creation is not supported in the local ledger workflow')
            pw=self.f_password.get()
            if len(pw)<14 or not hmac.compare_digest(pw,self.f_password2.get()):
                raise ValueError('Matching encryption passwords of 14+ characters are required')
            folder=validate_storage_folder('Custom directory',self.f_folder.get())
            label=self.f_label.get().strip()
            if not messagebox.askyesno('Offline ledger confirmation',
                f'Create an encrypted {code} bookkeeping file named {label}?\n\n'
                'THIS DOES NOT CREATE A BANK ACCOUNT OR HOLD ACTUAL MONEY.'):
                return
            self.f_password.set('');self.f_password2.set('')
            def done(path):
                paths=fiat_registry.load()
                if path not in paths:paths.append(path);fiat_registry.save(paths)
                messagebox.showinfo('Offline ledger created',
                                    'Encrypted ledger saved. No deposit address or actual banking account was created.')
                self.show('Fiat Ledger')
            self.run_job(lambda:fiat_ledger.new(str(folder),code,label,pw),done,
                         'Encrypting fiat bookkeeping file...')
        except Exception as err:
            messagebox.showerror('Fiat action blocked',f'{type(err).__name__}: {str(err)[:300]}')

    def _jump_fiat_create(self):
        self.show('Fiat Accounts')
        self.fiat_type.set('Offline encrypted ledger (manual records)')
        self._update_fiat_form()

    def begin_recovery(self):
        how=self.recovery_how.get()
        if how=='From recovery phrase':
            self.show('Crypto Vault')
            self.p_mode.set('Restore MY existing recovery phrase')
            messagebox.showinfo('Recovery','Select the correct chain, recovery method and account index. If restoring a stablecoin choose the Stablecoins workflow.')
        elif how=='Open existing encrypted .vault':
            p=filedialog.askopenfilename(filetypes=[('Encrypted crypto vault','*.vault')])
            if p and Path(p).is_file() and not Path(p).is_symlink():
                if p not in self.vault_paths:self.vault_paths.append(p);self.persist()
                self.show('Wallets')
        else:
            p=filedialog.askopenfilename(filetypes=[('Encrypted fiat ledger','*.fiat')])
            if p and Path(p).is_file() and not Path(p).is_symlink():
                paths=fiat_registry.load()
                if p not in paths:paths.append(p);fiat_registry.save(paths)
                self.show('Fiat Ledger')
