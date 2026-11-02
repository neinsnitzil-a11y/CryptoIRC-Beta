"""Token Center: public token pinning and network-specific read-only balances.
Signing stays in independently configured EVM Phase 2; no SPL/TRC send path.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from token_infrastructure import (TOKEN_CODES,EVM_TOKEN_NETWORKS,SOL_TOKENS,TRON_TOKENS,
                                  TokenRegistry,make_spec,read_token_balance)
from core.transfer import TransferError
BG='#07060b';CARD='#15101e';FG='#f2edf9';GREEN='#47fca3';MUTED='#a39ab6';WARN='#ff707a'

class TokenCenterUI:
    def page_token_center(self):
        self.head('Token Center / Phase 7',
                  '12 stablecoin/network entries. Operator-pinned contract/mint metadata, chain-aware balances. No SPL/TRC token signing or transfers.')
        panel=tk.Frame(self.content,bg=CARD,padx=16,pady=14);panel.pack(fill='x',pady=8)
        tk.Label(panel,text='01 / TOKEN IDENTIFICATION',bg=CARD,fg=GREEN,font=('Consolas',13,'bold')).pack(anchor='w')
        tk.Label(panel,text='A token symbol is NOT a unique identity. Check the network, issuer contract/mint and decimals against an authoritative source before using real funds.',
                 bg=CARD,fg=WARN,wraplength=900,justify='left').pack(anchor='w',pady=7)
        self.t35_code=tk.StringVar(value='USDT-ETH')
        self.t35_network=tk.StringVar(value='ETH')
        self.t35_address=tk.StringVar();self.t35_token=tk.StringVar();self.t35_decimals=tk.StringVar(value='6')
        self.t35_rpc=tk.StringVar();self.t35_genesis=tk.StringVar()
        def row(label,var):
            tk.Label(panel,text=label,bg=CARD,fg=MUTED).pack(anchor='w',pady=(7,2))
            return ttk.Entry(panel,textvariable=var).pack(fill='x')
        tk.Label(panel,text='Asset / chain route',bg=CARD,fg=MUTED).pack(anchor='w',pady=(8,2))
        cb=ttk.Combobox(panel,values=TOKEN_CODES,textvariable=self.t35_code,state='readonly');cb.pack(fill='x')
        tk.Label(panel,text='Blockchain / network',bg=CARD,fg=MUTED).pack(anchor='w',pady=(8,2))
        network=ttk.Combobox(panel,textvariable=self.t35_network,state='readonly');network.pack(fill='x')
        def route(*_):
            code=self.t35_code.get()
            opts=[EVM_TOKEN_NETWORKS[code]] if code in EVM_TOKEN_NETWORKS else (['devnet','mainnet'] if code in SOL_TOKENS else ['shasta','mainnet'])
            network.config(values=opts)
            if self.t35_network.get() not in opts:self.t35_network.set(opts[0])
            self.t35_token.set('');self.t35_genesis.set('')
            self.t35_decimals.set('6' if code.startswith(('USDT','USDC')) else '18')
            self._t35_load()
        cb.bind('<<ComboboxSelected>>',route)
        network.bind('<<ComboboxSelected>>',lambda e:self._t35_load())
        row('Receiving wallet public address (not a private key)',self.t35_address)
        row('Official token contract or mint ID — manually verify before pinning',self.t35_token)
        row('Expected token decimals',self.t35_decimals)
        row('Trusted RPC endpoint (HTTPS or local loopback HTTP)',self.t35_rpc)
        row('Solana pinned cluster genesis hash (mandatory for SPL)',self.t35_genesis)
        actions=tk.Frame(panel,bg=CARD);actions.pack(fill='x',pady=12)
        ttk.Button(actions,text='PIN PUBLIC TOKEN METADATA',style='Accent.TButton',command=self._t35_pin).pack(side='left',padx=5)
        ttk.Button(actions,text='LOAD PIN',command=self._t35_load).pack(side='left',padx=5)
        ttk.Button(actions,text='UNPIN TOKEN',command=self._t35_unpin).pack(side='left',padx=5)
        ttk.Button(actions,text='READ LIVE TOKEN BALANCE',style='Accent.TButton',command=self._t35_read).pack(side='left',padx=5)
        self.t35_status=tk.Text(panel,height=7,bg='#0c0914',fg=FG,insertbackground=GREEN,wrap='word',font=('Consolas',10))
        self.t35_status.pack(fill='x',pady=6)
        self._t35_show('Token PIN: none selected. A local pin is not an independent official-issuer verification.\nAll token reads are read-only and cannot move funds.')
        route()

    def _t35_show(self,value):
        output=getattr(self,'t35_status',None)
        if output is None or not output.winfo_exists():return
        output.config(state='normal');output.delete('1.0','end');output.insert('1.0',value);output.config(state='disabled')

    def _t35_load(self):
        try:spec=TokenRegistry().get(self.t35_code.get(),self.t35_network.get())
        except (TransferError,OSError):return
        if spec:
            self.t35_token.set(spec.token_id);self.t35_decimals.set(str(spec.decimals));self.t35_genesis.set(spec.genesis)
            self._t35_show('Loaded public metadata PIN. This is user-entered, not an audited token allowlist.\n'+spec.code+' / '+spec.network+' / '+spec.token_id)

    def _t35_pin(self):
        try: spec=self._t35_spec()
        except (ValueError,TransferError):
            messagebox.showerror('Invalid token','Check the asset route, token address/mint, decimals and genesis.',parent=self.root);return
        if not messagebox.askyesno('Token address safety',
                'Have you independently compared the exact token contract/mint and decimals against an authoritative issuer or chain source?\n\n'
                'This only saves YOUR selection; it does not certify the token.',parent=self.root):return
        try:TokenRegistry().pin(spec)
        except (TransferError,OSError):
            messagebox.showerror('Pin not saved','Token identifier differs from the existing pin. Unpin explicitly before changing it.',parent=self.root);return
        self._t35_show('TOKEN PIN SAVED LOCALLY\n'+spec.code+' / '+spec.network+'\n'+spec.token_id+'\nPublic token metadata only; no secrets or network approval stored.')

    def _t35_unpin(self):
        if messagebox.askyesno('Remove public token pin','Remove saved token metadata for this route?',parent=self.root):
            TokenRegistry().unpin(self.t35_code.get(),self.t35_network.get())
            self._t35_show('Token pin removed. No wallet funds, signing keys or transactions were touched.')

    def _t35_spec(self):
        return make_spec(self.t35_code.get(),self.t35_network.get(),self.t35_token.get().strip(),
                         int(self.t35_decimals.get()),genesis=self.t35_genesis.get().strip())

    def _t35_read(self):
        try:
            spec=self._t35_spec()
            pinned=TokenRegistry().get(spec.code,spec.network)
            if spec!=pinned:raise TransferError('Pin your token address, decimals and network before reading.')
            address=self.t35_address.get().strip();endpoint=self.t35_rpc.get().strip()
        except (TransferError,ValueError):
            messagebox.showerror('Token check failed','Select a valid, locally pinned token and a public receiving address.',parent=self.root);return
        def done(r):
            self._t35_show(f'{r.code} / {r.network}\nADDRESS {r.address}\nTOKEN CONTRACT/MINT {r.token_id}\n'
                f'BALANCE {r.amount} {r.symbol} ({r.amount_units} base units)\n'
                f'NATIVE FEE COIN {r.gas_coin} / balance units: {r.gas_units if r.gas_units is not None else "NOT VERIFIED"}\n'
                f'BLOCK/SLOT {r.block_or_slot if r.block_or_slot is not None else "NOT PROVIDED"}\n'
                f'STATUS {r.state}\n{r.note}')
        self.run_job(lambda:read_token_balance(spec,address,endpoint),done,'Reading network-specific token balance...')
