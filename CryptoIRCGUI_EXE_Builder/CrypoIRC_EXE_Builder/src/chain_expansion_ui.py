"""Phase 6 read-only chain expansion. No secrets, send actions or automatic funding."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from chain_expansion import COINS, NETWORKS, UTXO, read_balance

BG='#07060b'; CARD='#15101e'; FG='#f2edf9'; GREEN='#47fca3'; PURPLE='#b363ff'; MUTED='#a39ab6'; WARN='#ff707a'

class ChainExpansionUI:
    def page_chain_expansion(self):
        self.head('Phase 6 / Chain Expansion v3.3',
                  'Live read-only chain adapters for LTC, DOGE, BCH, SOL, TRX and XRP. '
                  'Public addresses are not proof of private-key ownership. Sending and fiat funding remain disabled.')
        p=tk.Frame(self.content,bg=CARD,padx=16,pady=14);p.pack(fill='x',pady=8)
        tk.Label(p,text='01 / SELECT BLOCKCHAIN & NETWORK',bg=CARD,fg=GREEN,font=('Consolas',11,'bold')).pack(anchor='w')
        self.cx_asset=tk.StringVar(value='SOL');self.cx_network=tk.StringVar(value='devnet')
        self.cx_address=tk.StringVar();self.cx_endpoint=tk.StringVar(value='https://api.devnet.solana.com')
        self.cx_cookie=tk.StringVar();self.cx_wallet=tk.StringVar();self.cx_genesis=tk.StringVar()
        controls=tk.Frame(p,bg=CARD);controls.pack(fill='x',pady=8)
        self.cx_coin_box=ttk.Combobox(controls,textvariable=self.cx_asset,values=COINS,state='readonly',width=12)
        self.cx_coin_box.pack(side='left',padx=(0,12))
        self.cx_net_box=ttk.Combobox(controls,textvariable=self.cx_network,values=NETWORKS['SOL'],state='readonly',width=14)
        self.cx_net_box.pack(side='left')
        self.cx_coin_box.bind('<<ComboboxSelected>>',lambda _:self._cx_asset_changed())
        self.cx_net_box.bind('<<ComboboxSelected>>',lambda _:self._cx_network_changed())
        self._cx_row(p,'Full PUBLIC address',self.cx_address)
        self._cx_row(p,'Trusted RPC endpoint (HTTPS, or local loopback HTTP)',self.cx_endpoint)
        self.cx_extra=tk.Frame(p,bg=CARD);self.cx_extra.pack(fill='x')
        self._cx_row(self.cx_extra,'For LTC/DOGE/BCH: loaded local coin wallet name',self.cx_wallet)
        local=tk.Frame(self.cx_extra,bg=CARD);local.pack(fill='x',pady=4)
        ttk.Entry(local,textvariable=self.cx_cookie).pack(side='left',fill='x',expand=True)
        ttk.Button(local,text='Select local node cookie',command=self._cx_pick_cookie).pack(side='left',padx=5)
        self._cx_row(p,'Solana: independently verified network genesis hash (required)',self.cx_genesis)
        tk.Label(p,text='No private key, seed, or RPC password should be entered here. BTC-like nodes must be running locally with an owned address and loaded wallet. '
                 'Solana refuses to display balances until its genesis hash matches your independently verified value. '
                 'TRON/XRP node network identity is NOT independently verified by this reader.',
                 bg=CARD,fg=WARN,wraplength=920,justify='left').pack(anchor='w',pady=8)
        ttk.Button(p,text='READ ON-CHAIN BALANCE (NO TRANSACTION)',command=self._cx_check,style='Accent.TButton').pack(anchor='w',pady=6)
        self.cx_result=tk.StringVar(value='READ ONLY · No account has been verified. All sends disabled.')
        r=tk.Frame(self.content,bg=CARD,padx=16,pady=14);r.pack(fill='x',pady=8)
        tk.Label(r,text='02 / NETWORK RESULT',bg=CARD,fg=GREEN,font=('Consolas',11,'bold')).pack(anchor='w')
        tk.Label(r,textvariable=self.cx_result,bg=CARD,fg=PURPLE,justify='left',wraplength=950).pack(anchor='w',pady=10)
        ttk.Button(r,text='OPEN ALL 30 ASSET CAPABILITIES',command=lambda:self.show('Asset Coverage')).pack(anchor='w')
        self._cx_asset_changed()
        chosen=getattr(self,'_cx_selected',None)
        if chosen and chosen[0] in COINS:
            self.cx_asset.set(chosen[0]);self._cx_asset_changed()
            self.cx_address.set(chosen[1])
        self._cx_selected=None

    def _cx_row(self,parent,title,var):
        tk.Label(parent,text=title.upper(),bg=CARD,fg=MUTED).pack(anchor='w',pady=(8,3))
        ttk.Entry(parent,textvariable=var).pack(fill='x')

    def _cx_asset_changed(self):
        code=self.cx_asset.get()
        self.cx_net_box.configure(values=NETWORKS[code])
        self.cx_network.set(NETWORKS[code][0])
        self._cx_network_changed()

    def _cx_network_changed(self):
        coin=self.cx_asset.get();net=self.cx_network.get()
        defaults={'SOL':{'devnet':'https://api.devnet.solana.com','mainnet':'https://api.mainnet.solana.com'},
                  'XRP':{'testnet':'https://s.altnet.rippletest.net:51234','mainnet':'https://xrplcluster.com'},
                  'TRX':{'shasta':'https://api.shasta.trongrid.io','mainnet':'https://api.trongrid.io'}}
        self.cx_endpoint.set(defaults.get(coin,{}).get(net,'http://127.0.0.1:19332' if coin in UTXO else ''))
        self.cx_genesis.set('')
        self.cx_result.set('No RPC checks performed. Read-only · signer and recovery NOT VERIFIED.')

    def _cx_pick_cookie(self):
        f=filedialog.askopenfilename(title='Choose local chain RPC cookie file',parent=self.root)
        if f:self.cx_cookie.set(f)

    def _cx_check(self):
        asset=self.cx_asset.get(); network=self.cx_network.get(); address=self.cx_address.get().strip()
        endpoint=self.cx_endpoint.get().strip(); cookie=self.cx_cookie.get().strip()
        wallet=self.cx_wallet.get().strip(); genesis=self.cx_genesis.get().strip()
        if network not in NETWORKS.get(asset,()):
            messagebox.showerror('Network','Explicit valid network required',parent=self.root);return
        if network in ('main','mainnet') and not messagebox.askyesno('REAL-MONEY NETWORK',
            'You selected a MAINNET RPC reader. This can display real funds, but this feature cannot sign or spend them. Continue to READ ONLY?',parent=self.root):return
        self.cx_result.set('Query in progress · never assume 0 for a failed RPC request...')
        def work():return read_balance(asset,network,address,endpoint,cookie_path=cookie,wallet=wallet,expected_genesis=genesis)
        def done(b):
            if not hasattr(self,'cx_result') or not self.cx_result:return
            if (self.current_page!='Chain Expansion' or self.cx_asset.get()!=asset
                or self.cx_network.get()!=network or self.cx_address.get().strip()!=address
                or self.cx_endpoint.get().strip()!=endpoint):
                self.cx_result.set('Account or network changed while querying; discarded stale response. Query again.')
                return
            self.cx_result.set(f'{b.asset} · {b.network}\n{b.address}\n'
                f'Confirmed / reported balance: {b.confirmed} {b.unit}\n'
                f'State: {b.state}\nHeight / slot: {b.height if b.height is not None else "not provided"}\n'
                f'{b.note}\nNO SIGNER · NO SEND · RECOVERY NOT VERIFIED')
        self.run_job(work,done,'Querying chain node in read-only mode...')
