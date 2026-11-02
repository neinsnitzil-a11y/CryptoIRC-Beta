"""Wallet-first receive + fiat-to-crypto provider handoff GUI."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from wallet_funding import FundingTarget, target_from_row, validate_payment, PROVIDER_URLS, ALLOWED_FIAT, provider_homepage
from pathlib import Path

BG='#07060b'; CARD='#15101e'; FG='#f2edf9'; GREEN='#47fca3'; MUTED='#a39ab6'; PURPLE='#9a4bea'; WARN='#ff707a'

class WalletFundingUI:
    def hub_page_wallets(self):
        self.head('Wallet manager / receive', 'Pick an encrypted wallet, unlock its public address, then receive or buy the exact selected cryptocurrency.')
        self.live_balance_panel()
        controls=tk.Frame(self.content,bg=BG);controls.pack(fill='x',pady=6)
        self._hub_btn(controls,'Add existing .vault',self.add_vault)
        self._hub_btn(controls,'Scan directory',self.scan_folder)
        self._hub_btn(controls,'UNLOCK SELECTED',self.unlock_selected,True)
        self._hub_btn(controls,'Remove from list',self.remove_vault)
        self._hub_btn(controls,'BITCOIN CORE',lambda:self.show('Live Crypto'))
        self._hub_btn(controls,'UNIFIED ACCOUNTS',lambda:self.show('Unified Wallets'),True)
        tree=ttk.Treeview(self.content,columns=('file','status','coins','location'),show='headings',height=7,selectmode='browse')
        for col,width in (('file',255),('status',115),('coins',145),('location',330)):
            tree.heading(col,text=col.capitalize());tree.column(col,width=width,stretch=col=='location')
        tree.pack(fill='x',pady=10)
        self.wallet_tree=tree
        for path in self.vault_paths:
            p=Path(path); rows=self.public_unlocked.get(path,[])
            tree.insert('','end',iid=path,values=(p.name,'UNLOCKED' if path in self.public_unlocked else ('ENCRYPTED' if p.is_file() else 'MISSING'),
                        ', '.join(x['coin'] for x in rows) if rows else '—',str(p.parent)))
        tree.bind('<<TreeviewSelect>>',self._hub_wallet_selected)
        info=tk.Frame(self.content,bg=CARD,padx=17,pady=12,highlightthickness=1,highlightbackground='#3b2654')
        info.pack(fill='x',pady=9)
        tk.Label(info,text='// SELECTED WALLET · PUBLIC RECEIVING ADDRESS',font=('Consolas',12,'bold'),bg=CARD,fg=GREEN).pack(anchor='w')
        self.wallet_public_panel=tk.Frame(info,bg=CARD)
        self.wallet_public_panel.pack(fill='x',pady=(7,2))
        tk.Label(self.wallet_public_panel,text='Select a wallet above. Unlock it to display receiving addresses; passwords and seeds remain hidden.',bg=CARD,fg=MUTED,wraplength=760,justify='left').pack(anchor='w')
        previous=getattr(self,'_last_wallet_selection',None)
        if previous in self.vault_paths:
            tree.selection_set(previous);tree.see(previous);self._hub_wallet_selected()

    def _hub_btn(self,parent,label,fn,primary=False):
        button=ttk.Button(parent,text=label,command=fn,style='Accent.TButton' if primary else 'TButton')
        button.pack(side='left',padx=(0,9),pady=4)
        return button

    def _hub_wallet_selected(self,event=None):
        selection=self.wallet_tree.selection()
        for w in self.wallet_public_panel.winfo_children():w.destroy()
        if not selection:return
        path=selection[0];self._last_wallet_selection=path
        public_rows=self.public_unlocked.get(path)
        if public_rows is None:
            tk.Label(self.wallet_public_panel,text='LOCKED — Click UNLOCK SELECTED to inspect public addresses.',bg=CARD,fg=WARN,font=('Consolas',10)).pack(anchor='w')
            return
        if not public_rows:
            tk.Label(self.wallet_public_panel,text='No public addresses found in this vault.',bg=CARD,fg=WARN).pack(anchor='w');return
        rows=[dict(e,kind='Vault public',label=Path(path).name,path=path) for e in public_rows]
        choice=tk.StringVar(value='0')
        select=ttk.Combobox(self.wallet_public_panel,textvariable=choice,state='readonly',width=90,values=[f'{i} · {e["coin"]} · {e.get("network",e["coin"])} · {e["address"]}' for i,e in enumerate(rows)])
        select.current(0);select.pack(fill='x',pady=(4,7))
        address_text=tk.StringVar()
        asset_info=tk.StringVar()
        tk.Label(self.wallet_public_panel,textvariable=asset_info,bg=CARD,fg=GREEN,font=('Consolas',11,'bold'),anchor='w').pack(fill='x')
        entry=ttk.Entry(self.wallet_public_panel,textvariable=address_text,state='readonly',font=('Consolas',10))
        entry.pack(fill='x',pady=(3,7))
        bar=tk.Frame(self.wallet_public_panel,bg=CARD);bar.pack(fill='x')
        def selected_row():
            idx=select.current()
            return rows[idx] if idx>=0 else rows[0]
        def render(event=None):
            row=selected_row();address_text.set(row['address'])
            asset_info.set(f'{row["coin"]}  |  {row.get("network",row["coin"])}')
            self.lb_use_public_row(row)
        select.bind('<<ComboboxSelected>>',render);render()
        self._hub_btn(bar,'COPY PUBLIC ADDRESS',lambda:self.copy_public(selected_row()['address']))
        self._hub_btn(bar,'SHOW QR / RECEIVE',lambda:self._hub_show_receive(selected_row()))
        self._hub_btn(bar,'ADD MONEY → THIS WALLET',lambda:self._hub_use_target(selected_row()),True)
        tk.Label(self.wallet_public_panel,text='An unlocked .vault address has NOT been independently verified for recovery/spending. Confirm ownership before depositing real funds.',bg=CARD,fg=WARN,wraplength=900,justify='left').pack(anchor='w',pady=(8,0))

    def _hub_show_receive(self,row):
        self.show('Receive')
        if hasattr(self,'receive_type'):
            self.receive_type.set('Vault / watch-only');self.update_receive()
            for r in self._public_rows():
                if r['address']==row['address'] and r['coin']==row['coin']:
                    self.show_address(r,self.receive_content)
                    break

    def _hub_use_target(self,row):
        try:target=target_from_row(row)
        except Exception as exc:
            messagebox.showerror('Unsupported address','Selected wallet address is not valid for this asset/network.');return
        self._hub_target=target
        self.show('Phase 4 Funding')

    def hub_page_funding(self):
        self.head('Add Money / Buy Crypto', 'Pay with regular money through an approved provider; crypto is delivered to your selected public wallet address.')
        self.live_balance_panel()
        p=self._hub_panel('01 / CHOOSE YOUR DESTINATION WALLET')
        rows=[]
        for row in self._public_rows():
            try:target=target_from_row(row)
            except ValueError:continue
            rows.append(target)
        # Bitcoin Core public address only after node confirms ownership.
        choice_options=['Choose a public wallet…']+[f'{r.asset} / {r.network} / {r.label} / …{r.address[-10:]}' for r in rows]+['Bitcoin Core — new verified BTC address','Monero RPC — new subaddress']
        self.hub_choices=rows
        self.hub_choice=tk.StringVar(value=choice_options[0])
        combo=ttk.Combobox(p,textvariable=self.hub_choice,values=choice_options,state='readonly');combo.pack(fill='x',pady=8)
        self.hub_asset=tk.StringVar(value='NOT SELECTED')
        self.hub_network=tk.StringVar(value='—')
        self.hub_address=tk.StringVar(value='')
        tk.Label(p,textvariable=self.hub_asset,bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w',pady=(6,2))
        tk.Label(p,textvariable=self.hub_network,bg=CARD,fg=MUTED,font=('Consolas',10)).pack(anchor='w')
        ttk.Entry(p,textvariable=self.hub_address,state='readonly',font=('Consolas',10)).pack(fill='x',pady=(9,5))
        bar=tk.Frame(p,bg=CARD);bar.pack(fill='x',pady=4)
        self._hub_btn(bar,'COPY ADDRESS',self._hub_copy_address)
        self._hub_btn(bar,'SHOW QR',self._hub_show_qr)
        self._hub_btn(bar,'VERIFY ON-CHAIN RECEIPT',self._hub_check_receipt)
        self.hub_ownership=tk.StringVar(value='No receiving wallet selected.')
        tk.Label(p,textvariable=self.hub_ownership,bg=CARD,fg=WARN,wraplength=900,justify='left').pack(anchor='w',pady=6)
        def select(event=None):
            idx=combo.current()
            if 1<=idx<=len(rows): self._hub_fill_target(rows[idx-1]);return
            if idx==len(rows)+1:
                self.run_job(lambda: self._hub_create_core_address(),self._hub_fill_target,'Getting BTC address from synced Bitcoin Core...');return
            if idx==len(rows)+2:
                self.run_job(lambda: self._hub_create_xmr_address(),self._hub_fill_target,'Getting Monero subaddress from wallet RPC...');return
            self._hub_fill_target(None)
        combo.bind('<<ComboboxSelected>>',select)
        if getattr(self,'_hub_target',None) is not None:
            self._hub_fill_target(self._hub_target)
            for i,r in enumerate(rows):
                if r.address==self._hub_target.address and r.asset==self._hub_target.asset:
                    combo.current(i+1);break
        p2=self._hub_panel('02 / PAY WITH FIAT → RECEIVE CRYPTO')
        form=tk.Frame(p2,bg=CARD);form.pack(fill='x')
        self.hub_fiat=tk.StringVar(value='USD')
        self.hub_amount=tk.StringVar(value='50.00')
        self.hub_provider=tk.StringVar(value=next(iter(PROVIDER_URLS)))
        self._hub_field(form,'Pay with fiat currency',self.hub_fiat,'choice',list(ALLOWED_FIAT))
        self._hub_field(form,'Fiat amount to spend',self.hub_amount)
        self._hub_field(form,'Licensed purchase provider',self.hub_provider,'choice',list(PROVIDER_URLS))
        self.hub_review=tk.StringVar(value='No order or quote created. Checkout occurs at the payment provider.')
        tk.Label(p2,textvariable=self.hub_review,bg=CARD,fg=MUTED,wraplength=880,justify='left').pack(anchor='w',pady=(9,5))
        self._hub_btn(p2,'OPEN PROVIDER TO BUY SELECTED CRYPTO',self._hub_checkout,True)
        tk.Label(p2,text='The provider quotes the crypto quantity, exchange rate and fees at checkout. Enter card/bank data ONLY with the provider. No automatic balance credit is performed by CRYPTO.',bg=CARD,fg=WARN,wraplength=880,justify='left').pack(anchor='w',pady=(8,0))

    def _hub_panel(self,title):
        p=tk.Frame(self.content,bg=CARD,padx=17,pady=13,highlightbackground='#3b2654',highlightthickness=1)
        p.pack(fill='x',pady=8)
        tk.Label(p,text=title,bg=CARD,fg=GREEN,font=('Consolas',13,'bold')).pack(anchor='w')
        return p

    def _hub_field(self,parent,label,var,kind='text',values=None):
        outer=tk.Frame(parent,bg=CARD);outer.pack(fill='x',pady=6)
        tk.Label(outer,text=label,bg=CARD,fg=MUTED).pack(anchor='w')
        if kind=='choice': w=ttk.Combobox(outer,textvariable=var,values=values,state='readonly')
        else:w=ttk.Entry(outer,textvariable=var)
        w.pack(fill='x',pady=3)
        return w

    def _hub_fill_target(self,target):
        self._hub_target=target
        if target is None:
            self.hub_asset.set('SELECT A WALLET');self.hub_network.set('—');self.hub_address.set('')
            self.hub_ownership.set('No address loaded.')
            return
        self.hub_asset.set(target.asset+' · '+target.label)
        self.hub_network.set('NETWORK: '+target.network)
        self.hub_address.set(target.address)
        self.hub_ownership.set('ADDRESS CONFIRMED AS CORE WALLET-OWNED — Independently test recovery and backup.' if target.ownership_verified else
            'ADDRESS NOT INDEPENDENTLY VERIFIED — Confirm the exact chain, address and recovery in trusted wallet software before spending any fiat.')

    def _hub_create_core_address(self):
        from backend import btc_receive
        addr,note=btc_receive(self.btc_url.get(),self.btc_cookie.get(),self.btc_name.get().strip())
        return FundingTarget('BTC',addr,'Bitcoin mainnet','Bitcoin Core verified',self.btc_name.get().strip(),True)

    def _hub_create_xmr_address(self):
        from backend import xmr_receive
        addr,note=xmr_receive(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get())
        return FundingTarget('XMR',addr,'Monero mainnet','Monero RPC', 'Monero wallet RPC', True)

    def _hub_copy_address(self):
        target=getattr(self,'_hub_target',None)
        if not target:
            messagebox.showwarning('Choose wallet','Select a receiving wallet first.');return
        self.copy_public(target.address)

    def _hub_show_qr(self):
        target=getattr(self,'_hub_target',None)
        if not target:
            messagebox.showwarning('Choose wallet','Select a receiving wallet first.');return
        w=tk.Toplevel(self.root);w.title('Public receiving address · QR');w.configure(bg=BG)
        w.geometry('570x570');w.transient(self.root)
        tk.Label(w,text=target.asset+' / '+target.network,bg=BG,fg=GREEN,font=('Consolas',14,'bold')).pack(pady=13)
        tk.Label(w,text=target.address,bg=BG,fg=FG,wraplength=510).pack(pady=6)
        try:
            import qrcode
            from PIL import ImageTk
            qr=qrcode.make(target.address).convert('RGB');qr.thumbnail((275,275))
            photo=ImageTk.PhotoImage(qr);w._qr_photo=photo
            tk.Label(w,image=photo,bg='white').pack(pady=14)
        except ImportError:tk.Label(w,text='Install qrcode and Pillow to display a QR.',bg=BG,fg=WARN).pack()
        tk.Label(w,text='Only the public address is encoded. Verify the full address independently.',bg=BG,fg=WARN,wraplength=480).pack()

    def _hub_check_receipt(self):
        target=getattr(self,'_hub_target',None)
        if not target:
            messagebox.showwarning('Choose wallet','Select a receiving wallet first.');return
        # Never infer that a completed checkout equals an on-chain deposit.
        if target.origin == 'Bitcoin Core verified':
            from backend import btc_balance_history
            self.run_job(lambda: btc_balance_history(self.btc_url.get(),self.btc_cookie.get(),self.btc_name.get().strip()),
                         lambda result: messagebox.showinfo('Confirmed by Bitcoin Core',result[0]+'\n\nSee Live Crypto for transaction history.'),
                         'Checking BTC confirmed and pending wallet balances...')
        elif target.origin == 'Monero RPC':
            from backend import xmr_balance_history
            self.run_job(lambda: xmr_balance_history(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get()),
                         lambda result: messagebox.showinfo('Reported by Monero wallet RPC',result[0]),
                         'Checking Monero wallet RPC balance...')
        elif target.asset=='ETH' and target.network in ('Ethereum mainnet','Ethereum','ETH') and self.evm_url.get().strip():
            from backend import evm_receive_balance
            self.run_job(lambda:evm_receive_balance('ETH',self.evm_url.get(),target.address),
                         lambda result:messagebox.showinfo('Ethereum RPC balance',str(result)),
                         'Checking ETH native balance from RPC...')
        else:
            messagebox.showinfo('No verified on-chain balance yet',
                'This account is not linked to a verified wallet node for this asset/network. '
                'Use Live Crypto with a supported RPC or trusted wallet software. '
                'A provider order confirmation is NOT proof of blockchain delivery.')

    def _hub_checkout(self):
        target=getattr(self,'_hub_target',None)
        if not target:
            messagebox.showerror('Choose wallet','Choose a receiving wallet first.');return
        try:amount=validate_payment(self.hub_amount.get(),self.hub_fiat.get())
        except ValueError as exc:
            messagebox.showerror('Invalid funding amount',str(exc));return
        # Do not guess provider asset/network availability; user must explicitly
        # confirm it from provider's live offer BEFORE authorizing a payment.
        confirm=(f'PAY: {amount} {self.hub_fiat.get()}\n'
                 f'RECEIVE: {target.asset} on {target.network}\n'
                 f'PUBLIC WALLET: {target.address}\n\n'
                 'This opens the official provider WEBSITE. CRYPTO does not charge your card, obtain a price, or send money.\n'
                 'Select the exact asset/network in checkout and enter/verify the full address there.\n'
                 'No deposit is recorded until delivery is independently verified.\n\n'
                 'Open provider now?')
        if not messagebox.askyesno('REVIEW BEFORE EXTERNAL PURCHASE',confirm,parent=self.root):return
        # Provider homepage without automatic address injection. Signed
        # integration requires a partner account and server-side signing.
        url=provider_homepage(self.hub_provider.get())
        webbrowser.open(url)
        self.hub_review.set(f'EXTERNAL CHECKOUT OPENED — Requested {amount} {self.hub_fiat.get()} to buy {target.asset} on {target.network}. NO PAYMENT CONFIRMED. Provider sets actual price/fees and sends crypto after its own checks.')
        self.status.set('PROVIDER OPENED • NO CRYPTO RECEIVED / NO BALANCE CREDITED')
