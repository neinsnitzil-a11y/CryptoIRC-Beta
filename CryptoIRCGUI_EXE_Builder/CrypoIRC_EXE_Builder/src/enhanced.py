"""Tkinter extension for wallet categories, storage selectors, recovery, fiat ledgers.

No bank account provisioning; no fiat transfers. Fiat is offline encrypted bookkeeping.
"""
from __future__ import annotations
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinter as tk
from pathlib import Path
import hmac
from core import vaultforge as vf
from core.assets import ASSETS, FIAT, CATEGORIES, TOKENS, assets_for
from core.extended_wallets import create_vaults
from core import fiat_ledger, fiat_registry
from core.exchange_engine import CURRENCY_CATALOG

BG='#07060b'; CARD='#15101e'; FG='#f2edf9'; MUTED='#a39ab6'; ACCENT='#47fca3'; FIELD='#0c0914'; WARN='#ff707a'

class EnhancedFeatures:
    def _lab(self, parent, text, bright=False):
        return tk.Label(parent,text=text,bg=parent.cget('bg'),fg=ACCENT if bright else MUTED,font=('Segoe UI',10,'bold' if bright else 'normal'),anchor='w')

    def _note(self,parent,text):
        tk.Label(parent,text=text,bg=parent.cget('bg'),fg=WARN,font=('Segoe UI',9),anchor='w',justify='left',wraplength=395).pack(anchor='w',pady=5)

    def _select(self,parent,label,variable,values,fn=None,width=29):
        box=tk.Frame(parent,bg=parent.cget('bg'));box.pack(fill='x',pady=5)
        self._lab(box,label).pack(anchor='w',pady=(0,3))
        cb=ttk.Combobox(box,textvariable=variable,values=values,state='readonly',width=width)
        cb.pack(fill='x')
        if fn:cb.bind('<<ComboboxSelected>>',lambda _e:fn())
        return cb

    def _entry(self,parent,label,variable,secret=False):
        box=tk.Frame(parent,bg=parent.cget('bg'));box.pack(fill='x',pady=5)
        self._lab(box,label).pack(anchor='w',pady=(0,3))
        e=ttk.Entry(box,textvariable=variable,show='●' if secret else '')
        e.pack(fill='x');return e

    def _btn(self,parent,label,command,accent=False):
        b=ttk.Button(parent,text=label,command=command,style='Accent.TButton' if accent else 'TButton');return b

    def _assets_for_kind(self):
        return assets_for(self.family.get())

    def page_create_wallet(self):
        self.head('Create wallets / accounts','Select wallet family, chain and network separately. Each asset gets its own seed by default.')
        outer=tk.Frame(self.content,bg=BG);outer.pack(fill='both',expand=True)
        left=tk.Frame(outer,bg=CARD,padx=14,pady=15,width=425,height=1150);left.pack(side='left',fill='y',padx=(0,12));left.pack_propagate(False)
        right=tk.Frame(outer,bg=CARD,padx=14,pady=15,width=425,height=1150);right.pack(side='left',fill='y');right.pack_propagate(False)
        self._lab(left,'01  CURRENCY / NETWORK',True).pack(anchor='w')
        self.family=tk.StringVar(value='Cryptocurrency')
        self._select(left,'Account family',self.family,CATEGORIES,self.on_family_change)
        self.asset_choice=tk.StringVar(value='BTC')
        self.asset_cb=self._select(left,'Asset / currency',self.asset_choice,[],self.on_asset_change)
        self.network_choice=tk.StringVar()
        self.network_cb=self._select(left,'Network / token standard',self.network_choice,[],self.on_network_change)
        self.method_var=tk.StringVar(value='')
        self._entry(left,'Generation method (read only)',self.method_var).configure(state='readonly')
        self._lab(left,'Wallets selected for creation (multiple assets supported)',True).pack(anchor='w',pady=(10,5))
        selected_frame=tk.Frame(left,bg=CARD);selected_frame.pack(fill='x')
        self.asset_basket=tk.Listbox(selected_frame,height=6,bg=FIELD,fg=FG,selectbackground='#285c51',exportselection=False)
        self.asset_basket.pack(fill='x')
        btnrow=tk.Frame(left,bg=CARD);btnrow.pack(fill='x',pady=5)
        self._btn(btnrow,'Add asset / network',self.add_asset).pack(side='left',padx=(0,5))
        self._btn(btnrow,'Remove selected',self.remove_asset).pack(side='left')
        self.fiat_label=tk.StringVar(value='Personal cash ledger')
        self._entry(left,'Fiat account name / label (fiat only)',self.fiat_label)
        self._note(left,'Fiat ledgers are manual bookkeeping only. No bank account, routing number or deposit address is created.')
        self._lab(right,'02  STORAGE DEVICE / RECOVERY',True).pack(anchor='w')
        self.storage_choice=tk.StringVar(value='This PC')
        self._select(right,'Storage device',self.storage_choice,['This PC','USB / external drive','Custom folder'],self.on_storage_change)
        self.usb_choice=tk.StringVar(value='No USB selected');self.usb_paths={}
        row=tk.Frame(right,bg=CARD);row.pack(fill='x')
        self.usb_cb=self._select(row,'Mounted USB volume',self.usb_choice,['No USB selected'],self.on_usb_change)
        self._btn(row,'Refresh USB',self.refresh_usb).pack(anchor='w',pady=3)
        self._entry(right,'Encrypted storage folder (.vault / .fiat)',self.default_folder)
        self._btn(right,'Browse storage directory',self.pick_folder).pack(anchor='w',pady=(2,6))
        self.strategy=tk.StringVar(value='Separate seed per asset')
        self._select(right,'Recovery phrase isolation',self.strategy,['Separate seed per asset','Shared BIP39 seed (advanced)'])
        self.recovery_mode=tk.StringVar(value='Generate new seed securely')
        self._select(right,'Creation / recovery mode',self.recovery_mode,['Generate new seed securely','Restore existing recovery phrase'])
        self.words_var=tk.StringVar(value='24')
        self._select(right,'BIP39 word count (Monero uses native 25 words)',self.words_var,['12','24'])
        self.account_index=tk.StringVar(value='0')
        self._select(right,'Derivation account index',self.account_index,[str(i) for i in range(5)])
        self.count_var=tk.StringVar(value='1')
        self._select(right,'Independent vault copies to create',self.count_var,[str(i) for i in range(1,21)])
        self.extra=tk.StringVar(value='')
        self._entry(right,'Optional BIP39 passphrase (not vault password)',self.extra,True)
        self.newpw=tk.StringVar(value=''); self.repeatpw=tk.StringVar(value='')
        self._entry(right,'New encryption password (14+ chars)',self.newpw,True)
        self._entry(right,'Confirm encryption password',self.repeatpw,True)
        self._btn(right,'CREATE / RESTORE ENCRYPTED WALLET',self.create_wallet_v2,True).pack(fill='x',pady=(12,5))
        self._note(right,'2,048-word CSV = reference dictionary, NOT a seed. BIP39 uses checksummed secure randomness; tokens inherit the chain address.')
        self.on_family_change()

    def on_family_change(self):
        fam=self.family.get()
        if fam=='Fiat ledger':
            self.asset_cb.configure(values=[code+' — '+name for code,name in FIAT]);self.asset_choice.set('USD — US Dollar')
        elif fam=='Stablecoin':
            codes=list(dict.fromkeys(a.code.split('-')[0] for a in TOKENS))
            self.asset_cb.configure(values=codes);self.asset_choice.set(codes[0])
        else:
            codes=[a.code for a in assets_for(fam)]
            self.asset_cb.configure(values=codes);self.asset_choice.set(codes[0])
        self.asset_basket.delete(0,'end')
        self.on_asset_change()

    def on_asset_change(self):
        family=self.family.get();code=self.asset_choice.get().split(' — ')[0]
        if family=='Fiat ledger':
            values=['Offline encrypted bookkeeping only']
        elif family=='Stablecoin':
            values=[a.network for a in TOKENS if a.code.startswith(code+'-')]
        else:
            values=[ASSETS[code].network] if code in ASSETS else []
        self.network_cb.configure(values=values)
        self.network_choice.set(values[0] if values else '')
        self.on_network_change()

    def on_network_change(self):
        code=self.get_selected_asset_code()
        if self.family.get()=='Fiat ledger':
            method='Fiat ledger • no blockchain keys or bank provisioning'
        else:
            method=ASSETS[code].method if code in ASSETS else 'Choose valid asset/network'
        self.method_var.set(method)

    def get_selected_asset_code(self):
        code=self.asset_choice.get().split(' — ')[0]
        if self.family.get()!='Stablecoin':return code
        for a in TOKENS:
            if a.code.startswith(code+'-') and a.network==self.network_choice.get():return a.code
        return ''

    def add_asset(self):
        if self.family.get()=='Fiat ledger':
            messagebox.showinfo('Fiat','Create separate fiat accounts with the fiat form.');return
        code=self.get_selected_asset_code()
        if code not in ASSETS:messagebox.showerror('Selection','Choose a supported network.');return
        if code not in self.asset_basket.get(0,'end'):
            self.asset_basket.insert('end',code)

    def remove_asset(self):
        for i in reversed(self.asset_basket.curselection()):self.asset_basket.delete(i)

    def on_storage_change(self):
        if self.storage_choice.get()=='This PC':
            self.default_folder.set(str(Path.home()/'CryptoWallets'))
        elif self.storage_choice.get()=='USB / external drive':
            self.refresh_usb()
            self.on_usb_change()
        # Custom folder keeps current folder until user changes it.

    def refresh_usb(self):
        try: items=vf.discover_usb()
        except Exception as exc:
            messagebox.showerror('USB scan',type(exc).__name__);return
        self.usb_paths={str(path)+'  ['+str(label)+']':str(path) for path,label in items}
        values=list(self.usb_paths)
        self.usb_cb.configure(values=values or ['No USB drives detected'])
        self.usb_choice.set(values[0] if values else 'No USB drives detected')
        if self.storage_choice.get()=='USB / external drive':self.on_usb_change()

    def on_usb_change(self):
        target=self.usb_paths.get(self.usb_choice.get())
        if target:self.default_folder.set(str(Path(target)/'CryptoWallets'))

    def _create_finished(self,paths,fiat=False):
        for p in paths:
            if fiat:
                paths_list=fiat_registry.load()
                if p not in paths_list:paths_list.append(p)
                fiat_registry.save(paths_list)
            elif p not in self.vault_paths:self.vault_paths.append(p)
        if not fiat:self.persist()
        self.newpw.set('');self.repeatpw.set('');self.extra.set('')
        messagebox.showinfo('Encrypted account created',f'{len(paths)} encrypted file(s) created.\n\nBack up the recovery phrase OFFLINE and independently test recovery before any deposit.' if not fiat else f'Created {len(paths)} encrypted offline fiat ledger(s). No bank or payment account was opened.')
        self.show('Fiat Ledger' if fiat else 'Wallets')

    def create_wallet_v2(self):
        try:
            p1=self.newpw.get();p2=self.repeatpw.get()
            if len(p1)<14 or not hmac.compare_digest(p1,p2):raise ValueError('Encryption password must be 14+ characters and match')
            target=self.default_folder.get().strip()
            if not Path(target).expanduser().is_absolute():raise ValueError('Choose an absolute storage directory')
            if self.storage_choice.get()=='USB / external drive':
                drive=self.usb_paths.get(self.usb_choice.get())
                if not drive:raise ValueError('Select a mounted USB device or change storage type')
                if not Path(drive).is_dir():raise ValueError('USB is no longer mounted')
                if Path(drive) not in Path(target).parents and Path(drive)!=Path(target):
                    raise ValueError('Selected folder must be on the selected USB volume')
            if self.family.get()=='Fiat ledger':
                code=self.get_selected_asset_code();name=self.fiat_label.get().strip()
                if self.recovery_mode.get().startswith('Restore'):
                    raise ValueError('Fiat ledgers do not have seed phrase recovery. Import existing .fiat from Fiat Ledger instead')
                if not messagebox.askyesno('Fiat bookkeeping only',f'Create encrypted {code} offline ledger named {name}? This is NOT a bank account or a service for holding/transferring real fiat funds.'):
                    return
                self.run_job(lambda:[fiat_ledger.new(target,code,name,p1)],lambda paths:self._create_finished(paths,True),'Creating encrypted fiat ledger...')
                return
            assets=list(self.asset_basket.get(0,'end')) or [self.get_selected_asset_code()]
            if any(a not in ASSETS for a in assets):raise ValueError('Choose supported assets and networks')
            count=int(self.count_var.get());words=int(self.words_var.get());index=int(self.account_index.get())
            strategy=self.strategy.get();extra=self.extra.get()
            import_phrase=''
            if self.recovery_mode.get()=='Restore existing recovery phrase':
                if count!=1 or len(assets)!=1:raise ValueError('Restore one asset and one wallet at a time')
                if not messagebox.askyesno('Sensitive wallet recovery','Only import YOUR OWN recovery phrase. Any malware, clipboard watcher or remote desktop can steal it. Prefer an offline trusted PC. Continue?'):
                    return
                import_phrase=simpledialog.askstring('Wallet recovery phrase','Enter your own BIP39 12/24-word or native XMR 25-word phrase. Never use the 2,048-word CSV as a seed:',show='●',parent=self.root)
                if not import_phrase:return
                import_phrase=vf.validate_phrase('monero' if assets[0]=='XMR' else 'bip39',import_phrase)
            if not messagebox.askyesno('Confirm software wallet generation',
                f'Assets: {", ".join(assets)}\nSets: {count}\nIsolation: {strategy}\nFolder: {target}\n\nThese are ENCRYPTED SOFTWARE WALLETS, not physical hardware signers.\nTest restore before depositing funds.'):
                return
            self.newpw.set('');self.repeatpw.set('');self.extra.set('')
            self.run_job(lambda:create_vaults(target,assets,count,words,p1,extra,strategy,import_phrase,index),
                         self._create_finished,'Generating and encrypting independent wallet keys...')
        except Exception as exc:
            messagebox.showerror('Wallet creation error',f'{type(exc).__name__}: {str(exc)[:300]}')

    def page_recovery(self):
        self.head('Wallet recovery center','Recover using your own verified seed phrase or an existing encrypted vault. Different chains use different standards.')
        c=self.card()
        self._lab(c,'Recovery method',True).pack(anchor='w')
        self.recovery_how=tk.StringVar(value='From recovery phrase')
        self._select(c,'Select recovery method',self.recovery_how,['From recovery phrase','Open existing encrypted .vault','Open existing fiat .fiat'])
        self._btn(c,'START RECOVERY',self.begin_recovery,True).pack(anchor='w',pady=(12,8))
        self.info(c,'BIP39 uses 12 or 24 words here, with checksum verification. Native Monero legacy recovery uses 25 words. An optional BIP39 passphrase changes the resulting wallet; do not confuse it with vault encryption password.',WARN)
        self.info(c,'Never enter a seed in an online form. Back up the words securely and do not send them to anyone. Restoring a wallet may expose its keys to this computer.')
        c2=self.card()
        self._lab(c2,'Existing encrypted vaults',True).pack(anchor='w')
        self._btn(c2,'Wallet manager / unlock',lambda:self.show('Wallets')).pack(anchor='w',pady=4)
        self._btn(c2,'Security / reveal backup verification',lambda:self.show('Security')).pack(anchor='w',pady=4)

    def begin_recovery(self):
        how=self.recovery_how.get()
        if how=='From recovery phrase':
            self.show('Create Wallet')
            self.recovery_mode.set('Restore existing recovery phrase')
            messagebox.showinfo('Recovery','Select exactly one currency and chain, then set the BIP39 passphrase (if any). Choose Restore existing recovery phrase in Creation / recovery mode. An encrypted vault will be created.')
        elif how=='Open existing encrypted .vault':
            p=filedialog.askopenfilename(filetypes=[('Encrypted crypto wallets','*.vault')])
            if p:
                if p not in self.vault_paths:self.vault_paths.append(p);self.persist()
                self.show('Wallets')
        else:
            p=filedialog.askopenfilename(filetypes=[('Encrypted fiat ledgers','*.fiat')])
            if p and Path(p).is_file() and not Path(p).is_symlink():
                paths=fiat_registry.load()
                if p not in paths:paths.append(p);fiat_registry.save(paths)
                self.show('Fiat Ledger')

    def page_fiat_ledger(self):
        self.head('Fiat currency ledgers','164 ISO fiat currencies for encrypted offline records; real balances stay with licensed payment providers.')
        c=self.card()
        files=fiat_registry.load()
        self._lab(c,'Choose an encrypted fiat ledger',True).pack(anchor='w')
        self.fiat_path=tk.StringVar(value=files[0] if files else '')
        self._select(c,'Fiat ledger file',self.fiat_path,files)
        row=tk.Frame(c,bg=CARD);row.pack(anchor='w',pady=6)
        self._btn(row,'Create fiat ledger',lambda:self._jump_fiat_create()).pack(side='left',padx=(0,8))
        self._btn(row,'Import existing file',self._import_fiat).pack(side='left',padx=(0,8))
        self._btn(row,'Unlock & inspect',self._open_fiat,True).pack(side='left')
        self.info(c,'No USD banking details, balance claims, funds, withdrawals, or payment credentials are generated. Real-money transfers require a regulated bank or payment provider.',WARN)
        self.fiat_details=tk.Frame(self.content,bg=BG);self.fiat_details.pack(fill='both',expand=True)

    def _jump_fiat_create(self):
        self.show('Create Wallet');self.family.set('Fiat ledger');self.on_family_change()

    def _import_fiat(self):
        path=filedialog.askopenfilename(title='Import encrypted fiat ledger',filetypes=[('Fiat ledger','*.fiat')])
        if path:
            if Path(path).is_symlink() or not Path(path).is_file():
                messagebox.showerror('Invalid file','Use a regular .fiat file');return
            paths=fiat_registry.load()
            if path not in paths:paths.append(path);fiat_registry.save(paths)
            self.show('Fiat Ledger')

    def _open_fiat(self):
        path=self.fiat_path.get()
        if not path:messagebox.showerror('Select ledger','Create or import a fiat account first');return
        pw=simpledialog.askstring('Fiat ledger password','Enter encryption password (not your bank password):',show='●',parent=self.root)
        if not pw:return
        self.run_job(lambda:fiat_ledger.read(path,pw),lambda d:self._show_fiat(d,path), 'Opening encrypted local fiat bookkeeping...')

    def _show_fiat(self,d,path):
        for w in self.fiat_details.winfo_children():w.destroy()
        c=tk.Frame(self.fiat_details,bg=CARD,padx=20,pady=15);c.pack(fill='both',expand=True,pady=8)
        bal=fiat_ledger.balance(d)
        self._lab(c,f'{d["label"]} • {d["currency"]}',True).pack(anchor='w',pady=5)
        precision=CURRENCY_CATALOG[d['currency']]['precision']
        tk.Label(c,text=f'Manually tracked balance: {bal:,.{precision}f} {d["currency"]}',font=('Segoe UI',18,'bold'),bg=CARD,fg=FG).pack(anchor='w',pady=6)
        self.info(c,'This number is your local record, NOT a verified bank or blockchain balance.',WARN)
        kind=tk.StringVar(value='Money in'); amount=tk.StringVar(); memo=tk.StringVar()
        self._select(c,'Entry category',kind,['Money in','Money out','Adjustment +','Adjustment -'])
        self._entry(c,f'Amount (positive, up to {precision} decimals)',amount)
        self._entry(c,'Memo (optional)',memo)
        def post():
            password=simpledialog.askstring('Confirm ledger edit','Re-enter local ledger encryption password:',show='●',parent=self.root)
            if not password:return
            if not messagebox.askyesno('Confirm bookkeeping entry',f'{kind.get()} {amount.get()} {d["currency"]}\nMemo: {memo.get()}\n\nThis is ONLY a local record; no actual money moves.'):
                return
            self.run_job(lambda:fiat_ledger.append(path,password,kind.get(),amount.get(),memo.get()),
                         lambda data:self._show_fiat(data,path),'Saving encrypted ledger entry...')
        self._btn(c,'RECORD MANUAL ENTRY',post,True).pack(anchor='w',pady=8)
        rows=ttk.Treeview(c,columns=('timestamp','kind','amount','memo'),show='headings',height=6)
        for col,sz in (('timestamp',190),('kind',130),('amount',140),('memo',300)):
            rows.heading(col,text=col.title());rows.column(col,width=sz)
        rows.pack(fill='x',pady=10)
        for e in reversed(d['entries'][-100:]):
            rows.insert('','end',values=(e['utc'][:19],e['kind'],e['amount'],e['memo']))
