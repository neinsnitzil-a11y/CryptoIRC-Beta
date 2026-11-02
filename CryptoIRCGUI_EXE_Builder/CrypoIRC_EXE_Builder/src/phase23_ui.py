"""Operator screens for EVM Phase 2 and Monero Phase 3.
UI does not save signing passwords, seeds or relay metadata to disk.
"""
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from decimal import Decimal
from evm_phase2 import EVMPhaseTwo, NETWORKS
from xmr_phase3 import MoneroPhaseThree
from chain_journal import ChainJournal
from core.transfer import TransferError

BG='#07060b';CARD='#15101e';GREEN='#47fca3';FG='#f2edf9';MUTED='#a39ab6'

class ChainPhaseUI:
    def _p23_panel(self,title,help_text):
        frame=tk.Frame(self.content,bg=CARD,padx=14,pady=14)
        frame.pack(fill='x',pady=8)
        tk.Label(frame,text=title,fg=GREEN,bg=CARD,font=('Consolas',13,'bold')).pack(anchor='w',pady=5)
        tk.Label(frame,text=help_text,fg=MUTED,bg=CARD,wraplength=900,justify='left').pack(anchor='w',pady=5)
        return frame
    def _p23_field(self,parent,title,var,secret=False):
        tk.Label(parent,text=title,bg=CARD,fg=MUTED,font=('Consolas',9)).pack(anchor='w',pady=(8,2))
        ttk.Entry(parent,textvariable=var,show='●' if secret else '').pack(fill='x',pady=(0,3))
    def _p23_button(self,parent,title,func):
        ttk.Button(parent,text=title,command=func,style='Accent.TButton').pack(side='left',padx=4,pady=6)
    def _p23_output(self,parent):
        t=tk.Text(parent,height=8,wrap='word',bg='#0c0914',fg=FG,insertbackground=GREEN,font=('Consolas',10))
        t.pack(fill='x',pady=6)
        return t
    def _p23_set(self,widget,message):
        if not widget.winfo_exists():return
        widget.config(state='normal');widget.delete('1.0','end');widget.insert('1.0',message);widget.config(state='disabled')
    def _evm_svc(self):
        return EVMPhaseTwo(self.p2_chain.get(),self.p2_rpc.get())

    def page_evm_phase_2(self):
        self.head('EVM Phase 2 / Verified Transfer Workflow',
                  'Ethereum, other EVM networks and ERC-20 tokens. Explicit fee cap, persistent nonce journal, no automatic resend. Start with Sepolia testnet.')
        p=self._p23_panel('01 / CHAIN / ENCRYPTED SIGNER',
                          'Select the exact network. This page never accepts seed phrases or raw private keys.')
        self.p2_chain=tk.StringVar(value='SEPOLIA')
        c=ttk.Combobox(p,state='readonly',values=list(NETWORKS.keys()),textvariable=self.p2_chain);c.pack(fill='x')
        self.p2_rpc=tk.StringVar(value='');self.p2_keystore=tk.StringVar(value='')
        self._p23_field(p,'Trusted HTTPS or local RPC',self.p2_rpc)
        self._p23_field(p,'Encrypted Ethereum V3 keystore file',self.p2_keystore)
        ttk.Button(p,text='CHOOSE KEYSTORE',command=lambda:self.p2_keystore.set(filedialog.askopenfilename(parent=self.root,title='Select encrypted Ethereum V3 keystore'))).pack(anchor='w',pady=6)
        p=self._p23_panel('02 / PREPARE & REVIEW',
                  'For token sends, verify the EXACT token contract address, expected symbol and decimals against an independent authoritative source. This is not a token allowlist.')
        self.p2_recipient=tk.StringVar();self.p2_amount=tk.StringVar();self.p2_max_fee=tk.StringVar(value='0.005')
        self.p2_token=tk.StringVar();self.p2_symbol=tk.StringVar();self.p2_decimals=tk.StringVar()
        self.p2_id=tk.StringVar()
        for name,var in [('Recipient 0x address',self.p2_recipient),('Amount in ETH/native coin OR token',self.p2_amount),
                         ('Maximum native gas fee',self.p2_max_fee),('Optional ERC-20 contract address',self.p2_token),
                         ('Expected token symbol (required for tokens)',self.p2_symbol),('Expected token decimals (required for tokens)',self.p2_decimals)]:
            self._p23_field(p,name,var)
        token_row=tk.Frame(p,bg=CARD);token_row.pack(fill='x')
        self._p23_button(token_row,'LOAD USER-PINNED TOKEN CONTRACT',self._p2_load_token_pin)
        self._p23_button(token_row,'OPEN TOKEN CENTER',lambda:self.show('Token Center'))
        row=tk.Frame(p,bg=CARD);row.pack(fill='x')
        self._p23_button(row,'PREPARE / SIMULATE',self._p2_prepare)
        self._p23_button(row,'REVIEW + SIGN + SEND',self._p2_submit)
        self._p23_button(row,'CANCEL UNBROADCAST',self._p2_cancel)
        self._p23_button(row,'RECONCILE HASH',self._p2_reconcile)
        self._p23_field(p,'Prepared request ID (non-secret)',self.p2_id)
        self.p2_output=self._p23_output(p)
        row2=tk.Frame(p,bg=CARD);row2.pack(fill='x')
        self._p23_button(row2,'CHECK CONNECTION & BALANCE',self._p2_balance)
        self._p23_button(row2,'TRANSACTION JOURNAL',lambda:self._p23_set(self.p2_output,'\n'.join(
            f"{r['id']}  {r['status']}  nonce={r['nonce']}  {r['tx_hash'] or '(unsigned)'}" for r in ChainJournal().list('EVM'))))
        self._p23_set(self.p2_output,'Nothing has been signed or sent. Sepolia is selected by default. Mainnet requires deliberate network selection and authorization.')

    def _p2_load_token_pin(self):
        from token_infrastructure import EVM_TOKEN_NETWORKS,TokenRegistry
        code=simpledialog.askstring('Load public token pin',
            'Enter the stablecoin route code, e.g. USDT-ETH or USDC-BASE.\n'
            'Only USER-PINNED metadata is loaded; verify issuer contract independently.',parent=self.root)
        if code is None:return
        code=code.strip().upper()
        if code not in EVM_TOKEN_NETWORKS:
            messagebox.showerror('Unsupported route','This signing page uses EVM ERC-20 only. SPL/TRC-20 are read-only in Token Center.',parent=self.root);return
        chain=EVM_TOKEN_NETWORKS[code]
        if self.p2_chain.get()!=chain:
            messagebox.showerror('Wrong blockchain',f'This pin belongs to {chain}, but selected EVM signer is {self.p2_chain.get()}. Select the matching chain explicitly.',parent=self.root);return
        spec=TokenRegistry().get(code,chain)
        if spec is None:
            messagebox.showerror('No public token pin','Pin contract and decimals in Token Center before importing.',parent=self.root);return
        self.p2_token.set(spec.token_id);self.p2_symbol.set(spec.symbol);self.p2_decimals.set(str(spec.decimals))
        self._p23_set(self.p2_output,'Loaded USER-PINNED contract: '+spec.token_id+"\n"+
            'The selected token is NOT issuer-certified. Independently verify its official contract before authorizing funds.')

    def _p2_prepare(self):
        code,url,ks,to,amount,fee,token,symbol,dec=(v.get().strip() for v in (
            self.p2_chain,self.p2_rpc,self.p2_keystore,self.p2_recipient,self.p2_amount,
            self.p2_max_fee,self.p2_token,self.p2_symbol,self.p2_decimals))
        if code!='SEPOLIA' and not messagebox.askyesno('REAL FUNDS / EVM MAINNET',f'You selected {code}. This may send real cryptocurrency. Prepare a transaction?',parent=self.root):return
        def work():return EVMPhaseTwo(code,url).prepare(ks,to,amount,fee,token_contract=token,expected_symbol=symbol,
                       expected_decimals=int(dec) if token and dec.isdecimal() else None)
        def done(row):
            self.p2_id.set(row['id'])
            self._p23_set(self.p2_output,'PREPARED, NOT SIGNED / NOT BROADCAST\n'
                +f"REQUEST {row['id']}\nNETWORK {code} ({row['network']})\nFROM {row['source']}\nTO {row['destination']}\n"
                +f"ASSET {row['asset']}\nAMOUNT UNITS {row['amount_units']}\nNONCE {row['nonce']}\n"
                +f"MAX GAS WEI {row['payload']['gas_max_wei']}\nVERIFY ALL DETAILS BEFORE AUTHORIZING.")
        self.run_job(work,done,'Preparing EVM transaction, checking funds & gas...')

    def _p2_submit(self):
        ident=self.p2_id.get().strip()
        try:
            row=ChainJournal().get(ident)
            if row['status']!='PREPARED':raise TransferError('Not prepared.')
            amt=Decimal(row['amount_units'])/Decimal(10**row['payload']['decimals'])
            expected=f"SEND {amt:f} {row['asset']} {row['destination'][-8:]}"
        except (TransferError,KeyError,ValueError) as e:
            messagebox.showerror('EVM Review Failed',str(e),parent=self.root);return
        if not messagebox.askyesno('EVM FINAL REVIEW',
                f"CHAIN ID: {row['network']}\nDESTINATION: {row['destination']}\nAMOUNT: {amt:f} {row['asset']}\n"
                f"NONCE: {row['nonce']}\nWORST GAS COST: {Decimal(row['payload']['gas_max_wei'])/Decimal(10**18):f} native\n\nBroadcast is irreversible. Continue?",parent=self.root):return
        typed=simpledialog.askstring('Authorize broadcast',f'Type exactly:\n{expected}',parent=self.root)
        if typed!=expected:return
        pw=simpledialog.askstring('Encrypted keystore password','Keystore password (not saved)',show='●',parent=self.root)
        if pw is None:return
        code,url,ks=self.p2_chain.get(),self.p2_rpc.get(),self.p2_keystore.get()
        def done(result):self._p23_set(self.p2_output,f"{result['status']}\nTX HASH {result['tx_hash']}\nNOT FINAL UNTIL RECONCILED")
        self.run_job(lambda:EVMPhaseTwo(code,url).submit(ident,typed,ks,pw),done,'Signing and broadcasting EVM transaction...')

    def _p2_cancel(self):
        ident=self.p2_id.get().strip();self.run_job(lambda:self._evm_svc().cancel(ident),
                  lambda r:self._p23_set(self.p2_output,'Cancelled unbroadcast intent '+r['id']),'Cancelling...')
    def _p2_reconcile(self):
        ident=self.p2_id.get().strip()
        self.run_job(lambda:self._evm_svc().reconcile(ident),
                  lambda r:self._p23_set(self.p2_output,f"STATUS {r['status']}\nTX HASH {r['tx_hash']}\nCONFIRMATIONS {r['confirmations']}"),'Reconciling on-chain EVM receipt...')
    def _p2_balance(self):
        from core.transfer import load_keystore_header
        from pathlib import Path
        code,url,ks,token=self.p2_chain.get(),self.p2_rpc.get(),self.p2_keystore.get(),self.p2_token.get().strip()
        def work():
            _,address=load_keystore_header(Path(ks))
            svc=EVMPhaseTwo(code,url);return svc.health(),address,svc.balance(address,token=token or None)
        def done(data):
            h,address,bal=data
            extra=('\nTOKEN '+bal['token_symbol']+' '+bal['token_balance']+'\nCONTRACT '+bal['token_contract']) if token else ''
            self._p23_set(self.p2_output,f"{code} CHAIN {h['chain_id']} @ BLOCK {h['block']}\nADDRESS {address}\nBALANCE {bal['native']} {bal['gas_asset']}"+extra)
        self.run_job(work,done,'Reading EVM chain and balance...')

    def page_monero_phase_3(self):
        self.head('Monero Phase 3 / Wallet-RPC',
                  'Local, authenticated Monero wallet-RPC. Wallet backup/restore must be verified independently. Prepared transactions stay offline until approved.')
        p=self._p23_panel('01 / LOCAL WALLET-RPC',
                  'The Monero wallet remains under wallet-RPC control. This application never requests native seed words here.')
        self.p3_network=tk.StringVar(value='stagenet')
        tk.Label(p,text='Monero network — stagenet for testing, mainnet for real XMR',bg=CARD,fg=MUTED).pack(anchor='w')
        ttk.Combobox(p,state='readonly',values=['stagenet','mainnet'],textvariable=self.p3_network).pack(fill='x',pady=4)
        self.p3_url=tk.StringVar(value='http://127.0.0.1:38082')
        self.p3_user=tk.StringVar(value=self.xmr_user.get())
        self._p23_field(p,'Wallet-RPC loopback URL',self.p3_url)
        self._p23_field(p,'Wallet-RPC authentication username',self.p3_user)
        self._p23_field(p,'Wallet-RPC password (session only)',self.xmr_password,secret=True)
        row=tk.Frame(p,bg=CARD);row.pack(fill='x')
        self._p23_button(row,'VERIFY WALLET + BALANCE',self._p3_balance)
        self._p23_button(row,'CREATE SUBADDRESS',self._p3_address)
        self._p23_button(row,'WALLET HISTORY',self._p3_history)
        self._p23_button(row,'VERIFY RESTORED ADDRESS',self._p3_restore_check)
        p=self._p23_panel('02 / PREPARE / CONFIRM / RELAY',
            'Monero transfers are prepared with do_not_relay=True. Relay metadata is never written to disk; restarting loses this capability.')
        self.p3_recipient=tk.StringVar();self.p3_amount=tk.StringVar();self.p3_fee=tk.StringVar(value='0.01');self.p3_id=tk.StringVar()
        for title,var in [('Destination Monero mainnet address',self.p3_recipient),('Amount (XMR)',self.p3_amount),
                          ('Maximum network fee (XMR)',self.p3_fee),('Prepared request ID',self.p3_id)]:self._p23_field(p,title,var)
        row=tk.Frame(p,bg=CARD);row.pack(fill='x')
        self._p23_button(row,'PREPARE OFFLINE',self._p3_prepare)
        self._p23_button(row,'AUTHORIZE + RELAY',self._p3_relay)
        self._p23_button(row,'RECONCILE',self._p3_reconcile)
        self._p23_button(row,'CANCEL PREPARED',self._p3_cancel)
        self.p3_output=self._p23_output(p)
        row2=tk.Frame(p,bg=CARD);row2.pack(fill='x')
        self._p23_button(row2,'VIEW JOURNAL',lambda:self._p23_set(self.p3_output,'\n'.join(
          f"{r['id']}  {r['status']}  {r['tx_hash'] or '(unrelayed)'}" for r in ChainJournal().list('XMR'))))
        self._p23_set(self.p3_output,'No transfer is prepared. An XMR wallet-RPC service must be running locally.')
        self._p3_instance=None
    def _p3_svc(self,preserve=False):
        if preserve and self._p3_instance is not None:return self._p3_instance
        return MoneroPhaseThree(self.p3_url.get(),self.p3_user.get(),self.xmr_password.get(),network=self.p3_network.get())
    def _p3_balance(self):
        self.run_job(lambda:self._p3_svc().balance(),lambda r:self._p23_set(self.p3_output,
          f"TOTAL: {r['total']} XMR\nUNLOCKED: {r['unlocked']} XMR\nLOCKED: {r['locked']} XMR\nWALLET HEIGHT: {r['wallet_height']}"),
          'Reading Monero wallet-RPC balance...')
    def _p3_address(self):
        def done(r):
            self._p23_set(self.p3_output,'NEW MONERO SUBADDRESS:\n'+r['address'])
            self.show_address({'coin':'XMR','address':r['address'],'label':'Monero subaddress','derivation':str(r['address_index'])},self.content)
        self.run_job(lambda:self._p3_svc().new_subaddress(),done,'Creating Monero receive subaddress...')
    def _p3_restore_check(self):
        expected=simpledialog.askstring('Restore address check',
             'Enter your previously recorded PRIMARY Monero public address. Never enter a seed phrase.',parent=self.root)
        if not expected:return
        self.run_job(lambda:self._p3_svc().check_restored_address(expected),
             lambda r:self._p23_set(self.p3_output,
                'RESTORED PUBLIC ADDRESS MATCHED\nWallet scanned to height '+str(r['height'])+
                '\nThis does NOT prove the seed, wallet sync, or spendability. Verify independent recovery.'),
             'Comparing restored wallet public identity...')

    def _p3_history(self):
        self.run_job(lambda:self._p3_svc().transfers(),lambda rows:self._p23_set(self.p3_output,
          '\n'.join(f"{r['type']} {r['amount']} XMR  conf={r['confirmations']}  {r['txid']}" for r in rows[:60]) or 'No history'),
          'Reading Monero transfers...')
    def _p3_prepare(self):
        if self.p3_network.get()=='mainnet' and not messagebox.askyesno('MONERO MAINNET / REAL FUNDS',
           'You selected MAINNET. Preparing can reserve REAL Monero outputs. Continue?',parent=self.root):return
        self._p3_instance=MoneroPhaseThree(self.p3_url.get(),self.p3_user.get(),self.xmr_password.get(),network=self.p3_network.get())
        to,amt,fee=self.p3_recipient.get(),self.p3_amount.get(),self.p3_fee.get()
        def done(row):
            self.p3_id.set(row['id'])
            self._p23_set(self.p3_output,f"PREPARED • NOT RELAYED\nHASH {row['tx_hash']}\nTO {row['destination']}\n"
                         f"AMOUNT {Decimal(row['amount_units'])/Decimal(10**12):f} XMR\n"
                         f"MINER FEE {Decimal(row['payload']['fee_atomic'])/Decimal(10**12):f} XMR\n"
                         'Review and authorize separately. Closing the app discards relay metadata.')
        self.run_job(lambda:self._p3_instance.prepare(to,amt,fee),done,'Preparing unrelayed Monero transfer...')
    def _p3_relay(self):
        try:
            row=ChainJournal().get(self.p3_id.get().strip())
            amount=Decimal(row['amount_units'])/Decimal(10**12)
            expected=f"SEND {amount:f} XMR {row['destination'][-8:]}"
        except Exception:
            messagebox.showwarning('No prepared transfer','Prepare a Monero transfer first.',parent=self.root);return
        if not messagebox.askyesno('MONERO FINAL REVIEW',
              f"TO: {row['destination']}\nAMOUNT: {amount:f} XMR\nTX HASH: {row['tx_hash']}\n\nRelaying is irreversible. Continue?",parent=self.root):return
        typed=simpledialog.askstring('Authorize XMR relay',f'Type exactly:\n{expected}',parent=self.root)
        if typed!=expected:return
        self.run_job(lambda:self._p3_svc(True).relay(row['id'],typed),
          lambda r:self._p23_set(self.p3_output,'MONERO '+r['status']+'\nTX HASH '+r['tx_hash']),'Relaying prepared Monero transaction...')
    def _p3_reconcile(self):
        ident=self.p3_id.get().strip()
        self.run_job(lambda:self._p3_svc().reconcile(ident),
          lambda r:self._p23_set(self.p3_output,f"MONERO {r['status']}\nHASH {r['tx_hash']}\nCONFIRMATIONS {r['confirmations']}"),
          'Checking Monero wallet-RPC status...')
    def _p3_cancel(self):
        ident=self.p3_id.get().strip()
        if not messagebox.askyesno('Cancel unrelayed transfer','This discards relay metadata but may NOT release wallet-reserved outputs immediately. Continue?',parent=self.root):return
        self.run_job(lambda:self._p3_svc(True).cancel(ident),
           lambda r:self._p23_set(self.p3_output,'Discarded prepared relay metadata. Verify wallet-RPC output availability before another send.'),
           'Cancelling unrelayed Monero transfer...')
