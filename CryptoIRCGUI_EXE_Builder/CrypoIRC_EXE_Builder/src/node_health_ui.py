"""Phase 9 blockchain health and safe read-only failover screen (Tk main thread)."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from node_health import (probe_bitcoin, probe_evm, probe_solana, probe_xrp,
                         select_read_endpoint)
from core.transfer import COIN_NETWORKS, TransferError

CARD='#15101e'; GREEN='#47fca3'; FG='#f2edf9'; MUTED='#a39ab6'; WARN='#ff707a'
NETWORKS={'BTC regtest':('BTC','regtest'),'BTC mainnet':('BTC','main'),
          'ETH Sepolia':('EVM','11155111'),
          **{f'{code} mainnet':('EVM',str(data[1])) for code,data in COIN_NETWORKS.items()},
          'Solana pinned genesis':('SOL',''),
          'XRPL pinned network':('XRP','')}

class NodeHealthUI:
    def page_blockchain_health(self):
        self.head('Blockchain Health / Phase 9',
            'Monitor node identity and synchronization. Backup failover is READ-ONLY; sends retain their explicitly selected signing endpoint.')
        p=tk.Frame(self.content,bg=CARD,padx=16,pady=15);p.pack(fill='x',pady=7)
        tk.Label(p,text='01 / NODE CONNECTION & IDENTITY',bg=CARD,fg=GREEN,
                 font=('Consolas',12,'bold')).pack(anchor='w')
        self.n36_network=tk.StringVar(value='ETH Sepolia')
        self.n36_primary=tk.StringVar(value='')
        self.n36_backup=tk.StringVar(value='')
        self.n36_pin=tk.StringVar(value='')
        self.n36_cookie=tk.StringVar(value=self.btc_cookie.get())
        self.n36_auto=tk.BooleanVar(value=False)
        tk.Label(p,text='Network (must match your wallet/account)',bg=CARD,fg=MUTED).pack(anchor='w',pady=(8,2))
        ttk.Combobox(p,textvariable=self.n36_network,values=tuple(NETWORKS),state='readonly').pack(fill='x')
        for label,var in (
            ('Trusted PRIMARY RPC endpoint; HTTPS except loopback HTTP',self.n36_primary),
            ('Trusted BACKUP RPC endpoint — optional; READ-ONLY failover',self.n36_backup),
            ('Solana GENESIS hash or XRP NETWORK ID (mandatory for those networks)',self.n36_pin),
            ('Bitcoin Core local RPC cookie file (BTC only, not stored)',self.n36_cookie)):
            tk.Label(p,text=label,bg=CARD,fg=MUTED).pack(anchor='w',pady=(9,2))
            ttk.Entry(p,textvariable=var).pack(fill='x')
        tk.Label(p,text='Identity mismatch, stale node tip or missing attestations result in NOT READY. '
                        'Backup RPCs are never substituted into wallet signing or transaction broadcast.',
                 bg=CARD,fg=WARN,wraplength=920,justify='left').pack(anchor='w',pady=12)
        a=tk.Frame(p,bg=CARD);a.pack(fill='x')
        ttk.Button(a,text='CHECK NODE / SYNC',style='Accent.TButton',command=self._n36_refresh).pack(side='left',padx=(0,10))
        ttk.Checkbutton(a,text='AUTO MONITOR (30s)',variable=self.n36_auto,
                        command=self._n36_auto_changed).pack(side='left')
        self.n36_output=tk.Text(p,height=9,bg='#0c0914',fg=FG,wrap='word',font=('Consolas',10))
        self.n36_output.pack(fill='x',pady=10)
        self._n36_print('NOT CHECKED\nSelect and verify the precise blockchain, RPC URL and identity before trusting balance or transaction data.')
        self._n36_generation=getattr(self,'_n36_generation',0)+1
        self._n36_poll(self._n36_generation)

    def _n36_print(self,message):
        widget=getattr(self,'n36_output',None)
        if widget is None or not widget.winfo_exists():return
        widget.config(state='normal');widget.delete('1.0','end')
        widget.insert('1.0',message);widget.config(state='disabled')

    def _n36_auto_changed(self):
        if self.n36_auto.get():self._n36_refresh()

    def _n36_poll(self,generation):
        if self.current_page != 'Blockchain Health' or generation != self._n36_generation:return
        if self.n36_auto.get() and not self.pending:
            self._n36_refresh()
        self.root.after(30_000,lambda:self._n36_poll(generation))

    def _n36_refresh(self):
        if self.pending:return
        choice=self.n36_network.get()
        if choice not in NETWORKS:
            messagebox.showerror('Invalid network','Choose a supported node network.',parent=self.root);return
        family,expected=NETWORKS[choice]
        primary=self.n36_primary.get().strip()
        backup=self.n36_backup.get().strip()
        pin=self.n36_pin.get().strip()
        cookie=self.n36_cookie.get().strip()
        if not primary:
            self._n36_print('UNAVAILABLE — Enter the primary endpoint.');return
        if family=='SOL':expected=pin
        if family=='XRP':
            try:expected=str(int(pin)) if pin and str(int(pin)) == pin else ''
            except ValueError:expected=''
        if not expected:
            self._n36_print('UNVERIFIED — Select a known network or pin its independent identity.');return
        endpoints=(primary,backup) if backup else (primary,)
        def probe(url):
            if family=='BTC':return probe_bitcoin(url,cookie,expected)
            if family=='EVM':return probe_evm(url,int(expected))
            if family=='SOL':return probe_solana(url,expected)
            if family=='XRP':return probe_xrp(url,int(expected))
            raise TransferError('Unsupported node type')
        def task():
            if len(endpoints)==1:
                status=probe(primary)
                if not status.ready:raise TransferError('Node not synchronized or network identity not verified: '+status.state)
                return status,False
            status=select_read_endpoint(endpoints,probe,expected_identity=expected,
                        maximum_height_gap=0 if family=='BTC' else 12)
            return status,status.endpoint != primary
        def done(result):
            if self.current_page!='Blockchain Health':return
            status,failover=result
            # never save node credentials, token PINs or any authenticated status
            self._n36_print('NODE READY / READ ONLY\n'
                f'Network: {choice}\nSource: {status.endpoint}\nIdentity: {status.identity}\n'
                f'Height / slot / ledger: {status.height}\nState: {status.state}\n'
                f'Failover: {"BACKUP READ-ONLY" if failover else "PRIMARY"}\n'
                f'Checked UTC: {__import__("datetime").datetime.fromtimestamp(status.observed_utc,__import__("datetime").timezone.utc).isoformat()}\n'
                f'{status.detail}\nThis check does not validate signer ownership or approve a send.')
        self._n36_print('PROBING NODE… Do not infer wallet balances from an unverified node.')
        self.run_job(task,done,'CHECKING NODE / CHAIN SYNCHRONIZATION…')
