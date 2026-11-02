"""Phase 1 Bitcoin Core transaction workflow (regtest by default)."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from decimal import Decimal
from pathlib import Path
from btc_phase1 import BitcoinPhaseOne, BitcoinJournal, NodeConfig, state_path
from brand_theme import GREEN, PURPLE

BG='#07060b'; CARD='#15101e'; MUTED='#a39ab6'; FG='#f2edf9'; WARN='#ff707a'

class BitcoinPhaseOneUI:
    def _b1_panel(self, title):
        p=tk.Frame(self.content,bg=CARD,highlightthickness=1,highlightbackground='#3b2654',padx=16,pady=14)
        p.pack(fill='x',pady=8)
        tk.Label(p,text=title,fg=GREEN,bg=CARD,font=('Consolas',12,'bold'),anchor='w').pack(fill='x',pady=(0,9))
        return p

    def _b1_field(self,p,label,var):
        tk.Label(p,text=label,fg=MUTED,bg=CARD,font=('Consolas',9),anchor='w').pack(fill='x',pady=(8,3))
        ttk.Entry(p,textvariable=var).pack(fill='x')

    def _b1_button(self,p,label,fn):
        return ttk.Button(p,text=label,command=fn,style='Accent.TButton')

    def page_btc_phase_1(self):
        tk.Label(self.content,text='// BITCOIN  /  TRANSACTION PHASE 1',fg=GREEN,bg=BG,
                 font=('Consolas',21,'bold')).pack(anchor='w')
        tk.Label(self.content,text='Bitcoin Core signer • durable transaction journal • regtest-first • explicit authorization. '
                 'NOCTURNE does not sign from BIP39 .vault seeds on this page.',fg=MUTED,bg=BG,
                 wraplength=900,justify='left').pack(anchor='w',pady=(4,12))
        self.p1_network=tk.StringVar(value='regtest')
        self.p1_url=tk.StringVar(value='http://127.0.0.1:18443')
        self.p1_cookie=tk.StringVar(value=str(Path.home()/('AppData/Roaming/Bitcoin/regtest/.cookie' if __import__('os').name=='nt' else '.bitcoin/regtest/.cookie')))
        self.p1_wallet=tk.StringVar(value=self.btc_name.get() if hasattr(self,'btc_name') else '')
        self.p1_recipient=tk.StringVar()
        self.p1_amount=tk.StringVar(value='0.00100000')
        self.p1_fee=tk.StringVar(value='0.00010000')
        self.p1_request=tk.StringVar()
        self.p1_status=tk.StringVar(value='REGTEST mode • no node connection verified')
        self.p1_output=tk.StringVar(value='No transaction prepared. Wallet operations require a synchronized local Bitcoin Core instance.')
        settings=self._b1_panel('01 / NETWORK  •  EXPLICIT CHOICE')
        tk.Label(settings,text='Network (REGTEST by default; MAINNET sends real BTC)',fg=MUTED,bg=CARD).pack(anchor='w')
        cb=ttk.Combobox(settings,textvariable=self.p1_network,values=['regtest','main'],state='readonly')
        cb.pack(fill='x',pady=4)
        def changed(_=None):
            n=self.p1_network.get()
            self.p1_url.set('http://127.0.0.1:'+('18443' if n=='regtest' else '8332'))
            self.p1_cookie.set(str(Path.home()/('AppData/Roaming/Bitcoin/' + ('regtest/' if n=='regtest' else '') + '.cookie' if __import__('os').name=='nt' else '.bitcoin/'+('regtest/' if n=='regtest' else '')+'.cookie')))
            self.p1_request.set('');self.p1_status.set('Network switched; check node again.')
        cb.bind('<<ComboboxSelected>>',changed)
        self._b1_field(settings,'Local RPC URL (loopback only)',self.p1_url)
        self._b1_field(settings,'Bitcoin Core authentication cookie file',self.p1_cookie)
        self._b1_field(settings,'Loaded Bitcoin Core wallet name',self.p1_wallet)
        actions=tk.Frame(settings,bg=CARD);actions.pack(anchor='w',pady=9)
        self._b1_button(actions,'CHECK NODE & WALLET',self._b1_check).pack(side='left',padx=(0,7))
        self._b1_button(actions,'CHOOSE LOADED WALLET',self._b1_choose_wallet).pack(side='left',padx=(0,7))
        self._b1_button(actions,'CREATE ENCRYPTED CORE WALLET',self._b1_create_wallet).pack(side='left')
        tk.Label(settings,textvariable=self.p1_status,fg=GREEN,bg=CARD,wraplength=860,justify='left').pack(anchor='w')
        receive=self._b1_panel('02 / RECEIVE  •  TRUSTED WALLET BALANCES')
        buttons=tk.Frame(receive,bg=CARD);buttons.pack(anchor='w')
        self._b1_button(buttons,'NEW VERIFIED RECEIVE ADDRESS',self._b1_receive).pack(side='left',padx=(0,8))
        self._b1_button(buttons,'REFRESH TRUSTED / PENDING',self._b1_balance).pack(side='left',padx=(0,8))
        self.p1_auto=tk.BooleanVar(value=False)
        ttk.Checkbutton(receive,text='AUTO REFRESH BALANCE & TX (30s)',variable=self.p1_auto).pack(anchor='w',pady=(8,0))
        send=self._b1_panel('03 / SEND  •  PREPARE  →  AUTHORIZE  →  RECONCILE')
        self._b1_field(send,'Destination BTC address on selected chain',self.p1_recipient)
        self._b1_field(send,'Exact amount BTC',self.p1_amount)
        self._b1_field(send,'Maximum miner fee in BTC (hard cap)',self.p1_fee)
        bar=tk.Frame(send,bg=CARD);bar.pack(anchor='w',pady=11)
        self._b1_button(bar,'PREPARE & REVIEW PSBT',self._b1_prepare).pack(side='left',padx=(0,8))
        self._b1_button(bar,'SIGN & BROADCAST',self._b1_send).pack(side='left',padx=(0,8))
        self._b1_button(bar,'CANCEL PREPARED',self._b1_cancel).pack(side='left')
        self._b1_field(send,'Persistent transaction request ID',self.p1_request)
        bar2=tk.Frame(send,bg=CARD);bar2.pack(anchor='w',pady=8)
        self._b1_button(bar2,'RECONCILE TX STATUS',self._b1_reconcile).pack(side='left',padx=(0,8))
        self._b1_button(bar2,'RECENT JOURNAL RECORDS',self._b1_history).pack(side='left')
        self.p1_display=tk.Text(send,height=10,bg='#0c0914',fg=FG,insertbackground=GREEN,
                                font=('Consolas',10),wrap='word')
        self.p1_display.pack(fill='x',pady=7)
        self._b1_text(self.p1_output.get())
        recovery=self._b1_panel('04 / BITCOIN CORE BACKUP / REGTEST RESTORE')
        tk.Label(recovery,text='Encrypted Core wallet backups are NOT BIP39 seed phrases. '
                 'A backup is not proven restorable until an independent restore test succeeds.',
                 bg=CARD,fg=WARN,wraplength=850,justify='left').pack(anchor='w')
        b=tk.Frame(recovery,bg=CARD);b.pack(anchor='w',pady=9)
        self._b1_button(b,'CREATE BACKUP FILE',self._b1_backup).pack(side='left',padx=(0,8))
        self._b1_button(b,'TEST RESTORE (REGTEST ONLY)',self._b1_restore).pack(side='left')
        tk.Label(recovery,text='Transaction journal is kept outside the installation directory: '+str(state_path()),
                 bg=CARD,fg=MUTED,wraplength=820,justify='left').pack(anchor='w')
        self.root.after(30000,self._b1_tick)

    def _b1_text(self,value):
        if hasattr(self,'p1_display') and self.p1_display.winfo_exists():
            self.p1_display.configure(state='normal');self.p1_display.delete('1.0','end')
            self.p1_display.insert('1.0',str(value));self.p1_display.configure(state='disabled')

    def _b1_service(self):
        return BitcoinPhaseOne(NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get()))

    def _b1_run(self,fn,format_result,desc):
        # Snapshot all Tk values on main thread before entering worker.
        self.run_job(fn,lambda result:self._b1_text(format_result(result)),desc)

    def _b1_tick(self):
        if getattr(self,'current_page',None)!='BTC Phase 1' or not self.root.winfo_exists():return
        if self.p1_auto.get() and not self.pending and self.p1_wallet.get().strip():
            cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get())
            wallet=self.p1_wallet.get().strip();ident=self.p1_request.get().strip()
            def work():
                svc=BitcoinPhaseOne(cfg)
                try: b=svc.balance(wallet)
                except Exception: return None
                txdata=None
                if ident:
                    try:
                        row=svc.journal.get(ident)
                        if row['status'] in ('PENDING','UNKNOWN','CONFIRMED','CONFLICTED','REPLACED','SIGNED','BROADCASTING'):
                            txdata=svc.reconcile(ident)
                    except Exception: txdata={'status':'UNKNOWN'}
                return b,txdata
            def done(result):
                if result is None:
                    self.p1_status.set('Balance unavailable (node disconnected, unsynced or wallet inaccessible)')
                    return
                b,t=result
                msg='BLOCKCHAIN BALANCE • Trusted '+b['trusted']+' BTC | Pending '+b['untrusted_pending']+' BTC | Immature '+b['immature']+' BTC'
                if t:msg+='\nTRANSACTION '+t['status']+' | confirmations '+str(t.get('confirmations','unverified'))
                self.p1_status.set(msg)
            self.run_job(work,done,'BTC Phase 1 refreshing verified balance...')
        self.root.after(30000,self._b1_tick)

    def _b1_check(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get());wallet=self.p1_wallet.get().strip()
        def work():
            svc=BitcoinPhaseOne(cfg);h=svc.health(); bal=svc.balance(wallet)
            return h,bal
        def done(result):
            h,b=result;self.p1_status.set(f"VERIFIED {h['network'].upper()} • height {h['blocks']} • wallet {wallet}")
            self._b1_text('Trusted: '+b['trusted']+' BTC\nUntrusted pending: '+b['untrusted_pending']+' BTC\nImmature: '+b['immature']+' BTC')
        self.run_job(work,done,'Checking Core network identity and wallet...')

    def _b1_choose_wallet(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get())
        def done(names):
            if not names:
                messagebox.showinfo('No Core wallets','No loaded wallets. Create one or load it using Bitcoin Core.',parent=self.root);return
            w=tk.Toplevel(self.root);w.title('Choose loaded Core wallet');w.geometry('450x340');w.configure(bg=BG);w.transient(self.root);w.grab_set()
            lb=tk.Listbox(w,bg='#0c0914',fg=FG,font=('Consolas',11),selectbackground='#302047');lb.pack(fill='both',expand=True,padx=12,pady=12)
            for name in names:lb.insert('end',name)
            def select():
                if lb.curselection():self.p1_wallet.set(names[lb.curselection()[0]]);w.destroy()
            ttk.Button(w,text='SELECT WALLET',command=select,style='Accent.TButton').pack(pady=10)
        def worker():
            svc=BitcoinPhaseOne(cfg);svc.health();return svc.rpc().call('listwallets')
        self.run_job(worker,done,'Reading Core loaded wallets...')

    def _b1_create_wallet(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get())
        wallet=simpledialog.askstring('New encrypted Bitcoin Core wallet','New name (letters, numbers, _ or -):',parent=self.root)
        if not wallet:return
        password=simpledialog.askstring('Core wallet passphrase','New passphrase (14+ characters; NOT a 12/24-word phrase):',show='●',parent=self.root)
        if password is None:return
        verify=simpledialog.askstring('Confirm passphrase','Retype the new Bitcoin Core passphrase:',show='●',parent=self.root)
        if password!=verify:
            messagebox.showerror('Mismatch','Core passphrases do not match.',parent=self.root);return
        if not messagebox.askyesno('Create Core wallet','Network: '+cfg.network+'\nNew wallet: '+wallet+'\n\nCore maintains the keys and encrypted wallet backup. Back up and verify restoration BEFORE using real funds.',parent=self.root):return
        def done(info):
            self.p1_wallet.set(info['wallet'])
            self._b1_text('NEW ENCRYPTED BITCOIN CORE WALLET: '+info['wallet']+'\nNETWORK '+info['network']+'\nBACKUP REQUIRED. Create a backup and verify restoration.')
        self.run_job(lambda:BitcoinPhaseOne(cfg).create_encrypted_wallet(wallet,password),done,'Creating encrypted descriptor wallet inside Bitcoin Core...')

    def _b1_receive(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get());wallet=self.p1_wallet.get().strip()
        def done(addr):
            self._b1_text('New Core-owned '+cfg.network+' address:\n'+addr+'\n\nBack up and independently restore before real deposits.')
            self.show_address({'coin':'BTC','address':addr,'label':wallet,'derivation':'Bitcoin Core '+cfg.network},self.content)
        self.run_job(lambda:BitcoinPhaseOne(cfg).receiving_address(wallet),done,'Generating verified Core receiving address...')

    def _b1_balance(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get());wallet=self.p1_wallet.get().strip()
        self._b1_run(lambda:BitcoinPhaseOne(cfg).balance(wallet),lambda b:'TRUSTED '+b['trusted']+' BTC  •  PENDING '+b['untrusted_pending']+' BTC  •  IMMATURE '+b['immature']+' BTC','Refreshing real Core balances...')

    def _b1_prepare(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get())
        wallet=self.p1_wallet.get().strip();dest=self.p1_recipient.get().strip();amount=self.p1_amount.get().strip();fee=self.p1_fee.get().strip()
        if cfg.network=='main' and not messagebox.askyesno('MAINNET SEND','MAINNET uses REAL Bitcoin. Prepare an actual PSBT using local Bitcoin Core?',parent=self.root): return
        def done(r):
            self.p1_request.set(r['id'])
            self._b1_text('PREPARED (NOT BROADCAST) • '+r['network']+'\nREQUEST: '+r['id']+'\nDESTINATION: '+r['recipient']+'\nAMOUNT: '+r['amount']+' BTC\nFEE: '+r['fee']+' BTC\nTOTAL: '+r['total_debit']+' BTC\n\nOUTPUTS:\n'+'\n'.join(f'{a} : {v} BTC' for a,v in r['outputs']))
        self.run_job(lambda:BitcoinPhaseOne(cfg).prepare(wallet,dest,amount,fee),done,'Preparing funded Bitcoin PSBT...')

    def _b1_send(self):
        ident=self.p1_request.get().strip();cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get())
        if not ident:
            messagebox.showwarning('Prepare first','Prepare and review a transaction first.',parent=self.root);return
        try:
            row=BitcoinJournal().get(ident)
            expected=f"SEND {Decimal(row['amount_sats'])/Decimal(10**8):.8f} BTC {row['recipient'][-8:]}"
        except Exception:
            messagebox.showerror('Request not found','Refresh transaction request and retry.',parent=self.root);return
        if row['network']!=cfg.network:
            messagebox.showerror('Wrong network','Transaction network does not match selected Core network.',parent=self.root);return
        if not messagebox.askyesno('Review BTC send',f"NETWORK: {cfg.network}\nRECIPIENT: {row['recipient']}\nAMOUNT: {Decimal(row['amount_sats'])/Decimal(10**8):.8f} BTC\nFEE: {Decimal(row['fee_sats'])/Decimal(10**8):.8f} BTC\n\nSend is irreversible after confirmation. Continue to authorization?",parent=self.root):return
        typed=simpledialog.askstring('Type exact authorization',f'Type exactly:\n{expected}',parent=self.root)
        if typed!=expected:return
        password=simpledialog.askstring('Bitcoin Core signer passphrase','Enter wallet passphrase (leave blank if already unlocked / unencrypted). Never enter mnemonic.',parent=self.root,show='●')
        if password is None:return
        def work():
            svc=BitcoinPhaseOne(cfg)
            result=svc.sign_and_broadcast(ident,typed,password)
            try: result['balance']=svc.balance(row['wallet'])
            except Exception: result['balance']=None
            return result
        def done(result):
            balance=result.get('balance')
            label=('\nTRUSTED: '+balance['trusted']+' BTC | PENDING: '+balance['untrusted_pending']+' BTC') if balance else '\nBalance unavailable; use Refresh after Core reconnects.'
            self._b1_text('TX '+result['status']+'\nID: '+result['id']+'\nTXID: '+result['txid']+'\n'+result.get('message','Refresh/reconcile status after broadcast.')+label)
        self.run_job(work,done,'Bitcoin Core signing and broadcasting...')

    def _b1_reconcile(self):
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get());ident=self.p1_request.get().strip()
        self._b1_run(lambda:BitcoinPhaseOne(cfg).reconcile(ident),lambda r:'TX '+r['status']+'\n'+r['txid']+'\nCONFIRMATIONS '+str(r.get('confirmations','unverified'))+'\n'+r.get('message',''),'Rechecking wallet transaction against Bitcoin Core...')

    def _b1_history(self):
        try:
            rows=BitcoinJournal().list(self.p1_network.get(),self.p1_wallet.get().strip(),25)
            self._b1_text('PERSISTENT TX JOURNAL\n\n'+'\n'.join(f"{r['id']}  {r['status']}  {r['amount_sats']/1e8:.8f} BTC  conf={r['confirmations']}  {r['txid'] or '(not broadcast)'}" for r in rows))
        except Exception:
            messagebox.showwarning('Journal unavailable','Could not open the transaction journal.',parent=self.root)

    def _b1_cancel(self):
        ident=self.p1_request.get().strip();cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get())
        if not ident:return
        if not messagebox.askyesno('Cancel prepared transaction','Cancel ONLY an unbroadcast prepared PSBT and release reserved inputs?',parent=self.root):return
        self._b1_run(lambda:BitcoinPhaseOne(cfg).cancel(ident),lambda _: 'Prepared transaction cancelled; locked inputs released.','Cancelling prepared PSBT...')

    def _b1_backup(self):
        from live_crypto import backup_core_wallet
        dest=filedialog.asksaveasfilename(parent=self.root,title='Core encrypted wallet backup',defaultextension='.dat',filetypes=[('Bitcoin Core wallet backup','*.dat *.bak')])
        if not dest:return
        url,cookie,wallet,network=self.p1_url.get(),self.p1_cookie.get(),self.p1_wallet.get().strip(),self.p1_network.get()
        def worker():
            BitcoinPhaseOne(NodeConfig(url,cookie,network)).wallet_rpc(wallet)
            # Existing Core backup module has a strict mainnet gate: regtest uses Core direct RPC.
            from pathlib import Path
            p=Path(dest).expanduser().resolve()
            if p.exists() or not p.parent.is_dir() or p.suffix.lower() not in ('.dat','.bak'):
                raise ValueError('Backup target must be a new .dat/.bak file in an existing folder.')
            if p.is_relative_to(Path(__file__).resolve().parent.parent):
                raise ValueError('Store backups outside the installation/build tree.')
            svc=BitcoinPhaseOne(NodeConfig(url,cookie,network));rpc=svc.wallet_rpc(wallet)
            rpc.call('backupwallet',str(p))
            if not p.is_file() or p.stat().st_size<100:
                raise ValueError('Core backup file was not confirmed on disk.')
            return p
        self._b1_run(worker,lambda p:'Bitcoin Core backup created: '+str(p)+'\nTest restoration independently. This is NOT a BIP39 file.','Creating Bitcoin Core backup...')

    def _b1_restore(self):
        if self.p1_network.get()!='regtest':
            messagebox.showwarning('Regtest only','This convenience restore test is regtest-only. Verify mainnet recovery in a separate trusted Core environment.',parent=self.root);return
        source=filedialog.askopenfilename(parent=self.root,title='Select regtest Core wallet backup',filetypes=[('Core backup','*.dat *.bak')]);
        if not source:return
        cfg=NodeConfig(self.p1_url.get(),self.p1_cookie.get(),self.p1_network.get());wallet=self.p1_wallet.get().strip()
        self._b1_run(lambda:BitcoinPhaseOne(cfg).restore_test(wallet,source),
                     lambda r:'RESTORED TEST WALLET: '+r['restored_wallet_name']+'\nOriginal owned addresses verified: '+str(r['addresses_verified'])+'\n'+r['note'],
                     'Regtest restoring backup into a separate Core wallet...')
