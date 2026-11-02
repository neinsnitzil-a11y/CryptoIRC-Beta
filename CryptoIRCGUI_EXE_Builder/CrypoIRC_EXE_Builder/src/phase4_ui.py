"""Coin coverage and Phase 4 purchase/cash-out request desktop UI.

No vendor secret, payment card, account credential or fake fiat balance.
Client-side requests are tracked but cannot be marked paid by the client.
"""
from __future__ import annotations
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import uuid
import webbrowser
from asset_capabilities import CAPABILITIES,catalog_stats
from funding_orders import FundingOrders,OrderError
from wallet_funding import FundingTarget, target_from_row, validate_payment, provider_homepage, ALLOWED_FIAT

BG='#07060b'; CARD='#15101e'; GREEN='#47fca3'; PURPLE='#b363ff'; MUTED='#a39ab6'; WARN='#ff707a'

def _orders_path():
    base = Path(os.environ.get('LOCALAPPDATA',os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local'/'share'))))/'CRYPTO_NOCTURNE'
    return base/'funding_requests.sqlite3'

class PhaseFourUI:
    def page_asset_coverage(self):
        self.head('30 cryptocurrencies + stablecoins',
                  'Every wallet type remains selectable. GENERATE ≠ VERIFIED SEND / RECEIVE. Select an asset to see its actual signing path.')
        s=catalog_stats()
        strip=tk.Frame(self.content,bg=CARD,padx=15,pady=12);strip.pack(fill='x',pady=6)
        tk.Label(strip,text=f'{s["base_coins"]} BASE CRYPTO     •     {s["token_networks"]} TOKEN NETWORKS     •     {s["connected_signer_routes"]} CONDITIONAL SIGNER ROUTES',
                 bg=CARD,fg=GREEN,font=('Consolas',11,'bold')).pack(anchor='w')
        tk.Label(strip,text='0 routes independently certified for real-money release. Some listed addresses are not spendable in the app.',
                 bg=CARD,fg=WARN,wraplength=870).pack(anchor='w',pady=(5,0))
        tree=ttk.Treeview(self.content,columns=('code','type','chain','method'),show='headings',height=17,selectmode='browse')
        for col,width in (('code',125),('type',135),('chain',170),('method',475)):
            tree.heading(col,text=col.title());tree.column(col,width=width,stretch=col=='method')
        tree.pack(fill='x',pady=12)
        for cap in CAPABILITIES.values():
            tree.insert('','end',iid=cap.code,values=(cap.code,cap.category,cap.network,
                     ('NODE / SIGNER REQUIRED' if cap.can_spend_if_connected else ('READ-ONLY NODE RPC / NO SIGNER' if cap.code in ('LTC','DOGE','BCH','SOL','TRX','XRP') else 'ADDRESS ONLY — NOT SPEND-READY'))))
        details=tk.StringVar(value='Select an asset for exact transaction and recovery limitations.')
        tk.Label(self.content,textvariable=details,bg=BG,fg=PURPLE,wraplength=980,justify='left').pack(anchor='w',pady=8)
        def changed(_=None):
            if tree.selection():
                cap=CAPABILITIES[tree.selection()[0]]
                details.set(f'{cap.code} | {cap.sign_method}\n{cap.note}\nMainnet independently verified: NO')
        tree.bind('<<TreeviewSelect>>',changed)
        ttk.Button(self.content,text='READ LIVE CHAIN BALANCES / PHASE 6',command=lambda:self.show('Chain Expansion')).pack(anchor='w',pady=5)
        ttk.Button(self.content,text='CREATE / IMPORT WALLET',command=lambda:self.show('Create Wallet'),style='Accent.TButton').pack(anchor='w',pady=10)

    def page_phase_4_funding(self):
        self.head('Phase 4 — Fiat ⇄ Cryptocurrency',
            'Wallet-bound funding request tracking, approved provider handoff and separate Cash Out. No cards or provider keys stored here.')
        panel=tk.Frame(self.content,bg=CARD,padx=16,pady=14);panel.pack(fill='x',pady=8)
        tk.Label(panel,text='01 / SELECT EXACT DESTINATION ASSET AND WALLET',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        rows=[]
        for row in self._public_rows():
            try: rows.append(target_from_row(row))
            except (ValueError,KeyError):pass
        current=getattr(self,'_hub_target',None)
        if current and all(not (r.asset==current.asset and r.address==current.address) for r in rows):
            rows.insert(0,current)
        self.p4_wallet_choice=tk.StringVar(value='Select wallet')
        labels=['Select wallet']+[f'{r.asset} · {r.network} · {r.address[:15]}…{r.address[-8:]}' for r in rows]
        combo=ttk.Combobox(panel,textvariable=self.p4_wallet_choice,values=labels,state='readonly',width=95)
        combo.current(0);combo.pack(fill='x',pady=8)
        self.p4_destination=tk.StringVar(value='No receiving address selected.')
        tk.Label(panel,textvariable=self.p4_destination,bg=CARD,fg=PURPLE,justify='left',wraplength=900).pack(anchor='w',pady=7)
        def chosen(_=None):
            i=combo.current()
            target=rows[i-1] if 1<=i<=len(rows) else None
            self._p4_selected_target=target
            self.p4_destination.set((f'Asset: {target.asset}\nNetwork: {target.network}\nAddress: {target.address}\n'
                +('Signer/ownership evidence available through connected wallet; verify recovery independently.' if target.ownership_verified
                else 'UNVERIFIED .vault address — DO NOT deposit until signing and recovery have been independently confirmed.')) if target else 'No receiving address selected.')
        combo.bind('<<ComboboxSelected>>',chosen)
        self._p4_selected_target=None
        if current:
            for i,r in enumerate(rows):
                if r.asset==current.asset and r.address==current.address:
                    combo.current(i+1);chosen();break
        tk.Label(panel,text='Choose a wallet from Wallets first, or unlock your encrypted .vault. Never enter a recovery phrase here.',
                 bg=CARD,fg=WARN,wraplength=900,justify='left').pack(anchor='w',pady=(4,0))
        panel2=tk.Frame(self.content,bg=CARD,padx=16,pady=14);panel2.pack(fill='x',pady=8)
        tk.Label(panel2,text='02 / BUY CRYPTO WITH FIAT',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.p4_fiat=tk.StringVar(value='USD');self.p4_amount=tk.StringVar(value='50.00')
        self._p4_field(panel2,'Pay with',self.p4_fiat,ALLOWED_FIAT)
        self._p4_field(panel2,'Fiat amount',self.p4_amount)
        actions=tk.Frame(panel2,bg=CARD);actions.pack(fill='x',pady=(8,0))
        ttk.Button(actions,text='REVIEW & OPEN OFFICIAL BUY PROVIDER',command=self._p4_buy,style='Accent.TButton').pack(side='left',padx=(0,9))
        ttk.Button(actions,text='CASH OUT → OFFICIAL SELL PROVIDER',command=self._p4_sell).pack(side='left')
        ttk.Button(panel2,text='APPROVED PARTNER TEST CHECKOUT (SANDBOX ONLY)',command=self._p4_partner_sandbox).pack(anchor='w',pady=8)
        tk.Label(panel2,text='BUY: provider confirms price, eligibility and payout. SELL: provider issues a unique deposit address for each order; never reuse it.\nThe desktop never treats opening checkout as a received or paid transaction.',
                 bg=CARD,fg=WARN,justify='left',wraplength=900).pack(anchor='w',pady=(10,0))
        panel3=tk.Frame(self.content,bg=CARD,padx=16,pady=13);panel3.pack(fill='x',pady=8)
        tk.Label(panel3,text='03 / LOCAL PAYMENT REQUEST JOURNAL (UNVERIFIED)',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.p4_orders=tk.StringVar(value='No saved funding requests.')
        tk.Label(panel3,textvariable=self.p4_orders,bg=CARD,fg=MUTED,justify='left',wraplength=960).pack(anchor='w',pady=9)
        ttk.Button(panel3,text='REFRESH REQUEST STATUS',command=self._p4_refresh).pack(anchor='w')
        self._p4_refresh()

    def _p4_field(self,parent,label,var,choices=None):
        tk.Label(parent,text=label.upper(),bg=CARD,fg=MUTED).pack(anchor='w',pady=(8,1))
        (ttk.Combobox(parent,textvariable=var,values=choices,state='readonly') if choices else ttk.Entry(parent,textvariable=var)).pack(fill='x')

    def _p4_refresh(self):
        try:
            orders=FundingOrders(_orders_path()).list(8)
            self.p4_orders.set('\n'.join(f'{x["created_at"]}   {x["amount"]} {x["fiat"]} → {x["asset"]}   {x["status"]}  /  {x["id"][:8]}' for x in orders)
                if orders else 'No requests. The journal tracks handoffs only, not deposited money.')
        except (OSError,ValueError) as exc:
            self.p4_orders.set('Funding history unavailable. Check local storage permissions.')

    def _p4_buy(self):
        target=self._p4_selected_target
        if not target:
            messagebox.showwarning('Select wallet','Choose the exact receiving wallet and blockchain first.',parent=self.root);return
        try: amount=validate_payment(self.p4_amount.get(),self.p4_fiat.get())
        except ValueError as exc:
            messagebox.showerror('Invalid amount',str(exc),parent=self.root);return
        if not messagebox.askyesno('UNVERIFIED ADDRESS — CONFIRM RECOVERY',
            f'Purchase request: {amount} {self.p4_fiat.get()} → {target.asset} on {target.network}\n\n'
            f'Destination: {target.address}\n\n'
            'Have you VERIFIED that this wallet can restore and SPEND from this address?\n'
            'A standalone .vault address may not have a connected signer.\n'
            'This only opens an external provider. No payment will be initiated in NOCTURNE.',parent=self.root):return
        try:
            journal=FundingOrders(_orders_path())
            order=journal.create(flow='BUY',provider='MoonPay — official website',target=target,
                fiat=self.p4_fiat.get(),amount=str(amount),idempotency=str(uuid.uuid4()))
            webbrowser.open(provider_homepage('MoonPay — official website'))
            journal.state(order['id'],'PROVIDER_OPENED')
            self._p4_refresh()
            self.status.set('PROVIDER OPENED — NO VERIFIED PURCHASE OR DEPOSIT')
        except (OrderError,ValueError,OSError,KeyError):
            messagebox.showerror('Handoff failed','Could not record funding request. No payment was initiated.',parent=self.root)

    def _p4_partner_sandbox(self):
        target=self._p4_selected_target
        if not target:
            messagebox.showwarning('Select wallet','Select the destination wallet first.',parent=self.root);return
        try:amount=validate_payment(self.p4_amount.get(),self.p4_fiat.get())
        except ValueError as exc:
            messagebox.showerror('Invalid amount',str(exc),parent=self.root);return
        if not messagebox.askyesno('SANDBOX ONLY',
            'This checks an approved MoonPay TEST partner session. It is NOT a real purchase.\n'
            'An authorized partner backend and its TEST keys must already be configured. Continue?',parent=self.root):return
        base=simpledialog.askstring('Partner sandbox service',
            'Partner service URL (HTTPS or local http://127.0.0.1:18440):',parent=self.root)
        if not base:return
        token=simpledialog.askstring('Ephemeral sandbox session token',
            'Enter your partner-service session token (NOT a MoonPay API secret):',show='*',parent=self.root)
        if not token:return
        from partner_bridge_client import fetch_sandbox_checkout
        source_fiat=self.p4_fiat.get()  # capture Tk state on GUI thread
        def work():
            return fetch_sandbox_checkout(base,token,target.asset,target.address,source_fiat,str(amount))
        def done(url):
            if messagebox.askyesno('OPEN SIGNED TEST CHECKOUT',
                f'MoonPay SANDBOX\n{target.asset} · {target.network}\n{target.address}\n'
                'No real card charges or funds will move. Open sandbox checkout?',parent=self.root):
                webbrowser.open(url)
                self.status.set('MOONPAY SANDBOX CHECKOUT OPENED — NO MONEY RECEIVED')
        self.run_job(work,done,'Requesting signed TEST checkout from authorized partner server...')

    def _p4_sell(self):
        target=self._p4_selected_target
        if not target:
            messagebox.showwarning('Select asset','Choose your sending asset first.',parent=self.root);return
        if not messagebox.askyesno('CASH OUT — EXTERNAL PROVIDER',
            f'Sell {target.asset} on {target.network} at the official provider?\n\n'
            'You must create a NEW sell order there and verify their unique deposit address, fees, and payout method.\n'
            'NOCTURNE does not initiate a crypto transfer or fiat payout automatically.',parent=self.root):return
        webbrowser.open('https://www.moonpay.com/sell')
        self.status.set('EXTERNAL CASH-OUT SITE OPENED — NO PAYOUT INITIATED')
