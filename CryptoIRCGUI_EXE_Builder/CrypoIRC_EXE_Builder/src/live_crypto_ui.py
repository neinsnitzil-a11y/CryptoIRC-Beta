"""Unified mainnet cryptocurrency UI. No fake balances and no unverified sends."""
from __future__ import annotations
from decimal import Decimal
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, filedialog, messagebox
from live_crypto import node_summary, create_encrypted_core_wallet, backup_core_wallet, wallet_transaction_status
from backend import btc_receive, btc_balance_history, xmr_receive, xmr_balance_history, evm_w3, evm_receive_balance
from core.transfer import COIN_NETWORKS
from brand_theme import GREEN,PURPLE

CARD='#15101e'; FG='#f2edf9'; MUTED='#a39ab6'; BG='#07060b'; WARN='#ff707a'

class LiveCryptoUI:
    def _live_area(self, title):
        c=tk.Frame(self.content,bg=CARD,highlightthickness=1,highlightbackground='#3b2654',padx=17,pady=17)
        c.pack(fill='x',pady=9)
        tk.Label(c,text=title,fg=GREEN,bg=CARD,font=('Consolas',13,'bold'),anchor='w').pack(fill='x',pady=(0,12))
        return c

    def _live_line(self,parent,text):
        tk.Label(parent,text=text,bg=CARD,fg=MUTED,font=('Segoe UI',10),anchor='w',justify='left',wraplength=850).pack(fill='x',pady=4)

    def _live_button(self,parent,text,command):
        ttk.Button(parent,text=text,command=command,style='Accent.TButton').pack(side='left',padx=(0,8),pady=5)

    def page_live_crypto(self):
        tk.Label(self.content,text='// LIVE CRYPTO  /  MAINNET',fg=GREEN,bg=BG,
                 font=('Consolas',22,'bold'),anchor='w').pack(fill='x')
        tk.Label(self.content,text='Real balances and transfers through your own Bitcoin Core / Monero wallet or a trusted EVM RPC. Only provider-confirmed network data is displayed.',
                 fg=MUTED,bg=BG,font=('Segoe UI',10),anchor='w',justify='left',wraplength=940).pack(fill='x',pady=(4,13))
        self.live_balance_panel()
        row=self._live_area('01 / SELECT COIN & NETWORK')
        self.live_kind=tk.StringVar(value='BTC / Bitcoin Core')
        combo=ttk.Combobox(row,textvariable=self.live_kind,state='readonly',values=['BTC / Bitcoin Core','ETH and EVM networks','XMR / Monero wallet RPC'])
        combo.pack(fill='x',pady=6)
        combo.bind('<<ComboboxSelected>>',lambda e:self._live_switch())
        self.live_body=tk.Frame(self.content,bg=BG)
        self.live_body.pack(fill='x')
        self._live_switch()
        foot=self._live_area('IMPORTANT / ASSET OWNERSHIP')
        self._live_line(foot,'A BTC address inside a VaultForge .vault is NOT the same wallet as a Bitcoin Core wallet. Bitcoin Core cannot automatically spend VaultForge BIP39 BTC seeds. DO NOT send BTC to a .vault address unless recovery and signing are independently verified.')
        self._live_line(foot,'Bitcoin Core uses its own encrypted wallet database and backup file, NOT the 12/24-word NOCTURNE recovery screen. Mainnet sends require a complete fee and destination review.')
        self._live_line(foot,'No fiat-money account is created here. Fiat deposits or purchases require approved external financial providers.')

    def _live_switch(self):
        for obj in self.live_body.winfo_children():obj.destroy()
        kind=self.live_kind.get()
        if kind.startswith('BTC'): self._live_btc()
        elif kind.startswith('ETH'): self._live_evm()
        else:self._live_xmr()

    def _live_btc(self):
        c=tk.Frame(self.live_body,bg=CARD,highlightbackground='#3b2654',highlightthickness=1,padx=17,pady=16)
        c.pack(fill='x',pady=7)
        tk.Label(c,text='BITCOIN CORE  •  MAINNET  •  SELF-CUSTODY',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self._live_line(c,'Requires the official Bitcoin Core application, a fully synced node, and an authenticated local RPC. It does not use an online custodial exchange.')
        self._live_entry(c,'RPC endpoint (127.0.0.1:8332)',self.btc_url)
        self._live_entry(c,'Bitcoin Core .cookie location',self.btc_cookie)
        self._live_entry(c,'Loaded Bitcoin Core wallet name',self.btc_name)
        btn=tk.Frame(c,bg=CARD);btn.pack(fill='x',pady=8)
        self._live_button(btn,'CHECK NODE / WALLETS',self._live_check_btc)
        self._live_button(btn,'SELECT LOADED WALLET',self.list_btc_wallets)
        self._live_button(btn,'CREATE ENCRYPTED BTC WALLET',self._live_create_btc)
        self.live_btc_status=tk.StringVar(value='DISCONNECTED • No blockchain data verified yet')
        tk.Label(c,textvariable=self.live_btc_status,bg=CARD,fg=GREEN,wraplength=850,justify='left').pack(anchor='w',pady=8)
        more=self._live_area('02 / RECEIVE • BALANCE • SEND • BACKUP')
        bar=tk.Frame(more,bg=CARD);bar.pack(fill='x')
        self._live_button(bar,'NEW RECEIVE ADDRESS',self._live_receive_btc)
        self._live_button(bar,'REFRESH BALANCE & HISTORY',self._live_balance_btc)
        self._live_button(bar,'SEND BTC',lambda:self._live_go_send('Bitcoin Core BTC'))
        self._live_button(bar,'BACKUP CORE WALLET',self._live_backup_btc)
        self.live_results=tk.Text(more,height=8,bg='#0c0914',fg=FG,insertbackground=GREEN,font=('Consolas',10),wrap='word')
        self.live_results.pack(fill='x',pady=(7,4));self.live_results.insert('1.0','Connect your own Bitcoin Core wallet. No balance is shown until its mainnet RPC responds.');self.live_results.configure(state='disabled')
        txbar=tk.Frame(more,bg=CARD);txbar.pack(fill='x',pady=9)
        self.live_btc_txid=tk.StringVar()
        ttk.Entry(txbar,textvariable=self.live_btc_txid,width=68).pack(side='left',padx=(0,9))
        self._live_button(txbar,'CHECK BTC TX CONFIRMATIONS',self._live_txstatus_btc)

    def _live_entry(self,parent,title,var):
        tk.Label(parent,text=title,bg=CARD,fg=MUTED,font=('Consolas',9)).pack(anchor='w',pady=(9,3))
        ttk.Entry(parent,textvariable=var).pack(fill='x')

    def _live_set_text(self,value):
        if not hasattr(self,'live_results') or not self.live_results.winfo_exists(): return
        self.live_results.configure(state='normal');self.live_results.delete('1.0','end')
        self.live_results.insert('1.0',str(value));self.live_results.configure(state='disabled')

    def _live_check_btc(self):
        def done(info):
            self.live_btc_status.set('MAINNET SYNCED • Block height: '+str(info['height'])+' • '+str(len(info['wallets']))+' loaded wallet(s)')
            self._live_set_text('Loaded wallets:\n'+('\n'.join(info['wallets']) or '(none)')+'\n\nIf no wallet is loaded, create one or load it through Bitcoin Core.')
        self.run_job(lambda:node_summary(self.btc_url.get(),self.btc_cookie.get()),done,'Checking official Bitcoin Core mainnet...')

    def _live_create_btc(self):
        name=simpledialog.askstring('Bitcoin Core Wallet Name','Choose a NEW Bitcoin Core wallet name (letters, numbers, _ or -).',parent=self.root)
        if not name:return
        password=simpledialog.askstring('Encrypt NEW Core wallet','Use a NEW 14+ character wallet passphrase. This is NOT a BIP39 recovery phrase.',show='●',parent=self.root)
        if password is None:return
        confirm=simpledialog.askstring('Confirm Core wallet passphrase','Retype exactly. The wallet cannot be recovered if the passphrase and backup are lost.',show='●',parent=self.root)
        if confirm is None:return
        if password!=confirm:
            messagebox.showerror('Mismatch','Wallet passphrase does not match.');return
        if not messagebox.askyesno('CREATE A REAL BITCOIN CORE WALLET',
            'This creates an actual ENCRYPTED descriptor wallet inside your locally running Bitcoin Core.\n\n'
            'It does not generate 12/24 recovery words. You MUST create a Core wallet backup before funding.\n\nProceed?',parent=self.root):return
        def done(info):
            self.btc_name.set(info['wallet'])
            self._live_set_text('Created ENCRYPTED Core wallet: '+info['wallet']+'\nBACKUP REQUIRED: click BACKUP CORE WALLET before receiving any BTC.')
            messagebox.showwarning('BACKUP REQUIRED','Wallet created in Bitcoin Core.\n\nCreate an encrypted Bitcoin Core wallet backup now before receiving funds.',parent=self.root)
        self.run_job(lambda:create_encrypted_core_wallet(self.btc_url.get(),self.btc_cookie.get(),name,password),done,'Creating encrypted Bitcoin Core wallet...')

    def _live_backup_btc(self):
        name=self.btc_name.get().strip()
        if not name:
            messagebox.showwarning('Choose Core wallet','Select your loaded Bitcoin Core wallet first.');return
        dest=filedialog.asksaveasfilename(parent=self.root,title='Save a Bitcoin Core encrypted wallet backup (prefer an offline external drive)',defaultextension='.dat',filetypes=[('Bitcoin wallet backup','*.dat'),('Backup','*.bak')])
        if not dest:return
        def done(path):
            self._live_set_text('Bitcoin Core confirmed backup created at:\n'+str(path)+'\nStore this backup offline, separately from its wallet passphrase. Verify a restore with Bitcoin Core before funding.')
            messagebox.showinfo('Bitcoin Core backup','Wallet backup written. Do an independent restore test before funding.',parent=self.root)
        self.run_job(lambda:backup_core_wallet(self.btc_url.get(),self.btc_cookie.get(),name,dest),done,'Bitcoin Core is backing up wallet...')

    def _live_receive_btc(self):
        name=self.btc_name.get().strip()
        def done(value):
            self._live_set_text('NEW BTC MAINNET RECEIVING ADDRESS:\n'+value[0]+'\n\nCopy carefully; only fund after verifying the Core wallet backup.')
            self.show_address({'coin':'BTC','address':value[0],'label':name,'derivation':value[1]},self.live_results.master)
        self.run_job(lambda:btc_receive(self.btc_url.get(),self.btc_cookie.get(),name),done,'Getting fresh BTC mainnet address...')

    def _live_balance_btc(self):
        name=self.btc_name.get().strip()
        def done(result):
            bal,rows=result
            content=bal+'\n\nLAST 25 TRANSACTIONS (provided by Bitcoin Core):\n'
            content+='\n'.join(f"{r['type']:10} {r['amount']:>16} BTC  confirmations:{r['confirmations']:>5}  {r['txid']}" for r in rows[:25]) or '(no transactions)'
            self._live_set_text(content)
        self.run_job(lambda:btc_balance_history(self.btc_url.get(),self.btc_cookie.get(),name),done,'Reading Bitcoin Core on-chain wallet balance...')

    def _live_txstatus_btc(self):
        name=self.btc_name.get().strip();txid=self.live_btc_txid.get().strip()
        def done(data):self._live_set_text('ON-CHAIN WALLET TX: '+data['txid']+'\n'+data['status']+' • confirmations: '+str(data['confirmations'])+'\nAmount: '+data['amount']+' BTC')
        self.run_job(lambda:wallet_transaction_status(self.btc_url.get(),self.btc_cookie.get(),name,txid),done,'Reading Bitcoin transaction confirmations...')

    def _live_go_send(self,kind):
        if kind == 'Bitcoin Core BTC':
            self.show('BTC Phase 1'); return
        self.show('Send')
        self.send_kind.set(kind)
        self.rebuild_send_source()

    def _live_evm(self):
        c=self._live_area('ETH / EVM / MAINNET')
        self._live_line(c,'Supported live EVM networks use on-chain RPC state, chain-ID checks, an encrypted signer and explicit confirmation. Other 30-coin addresses are not spend-enabled.')
        ttk.Combobox(c,textvariable=self.evm_code,values=list(COIN_NETWORKS),state='readonly').pack(fill='x',pady=6)
        self._live_entry(c,'Trusted EVM HTTPS RPC endpoint (not stored)',self.evm_url)
        self.live_public_evm=tk.StringVar()
        self._live_entry(c,'Your PUBLIC EVM 0x receiving address',self.live_public_evm)
        bar=tk.Frame(c,bg=CARD);bar.pack(fill='x',pady=9)
        self._live_button(bar,'VERIFY CHAIN & BALANCE',self._live_balance_evm)
        self._live_button(bar,'SEND ETH / NATIVE COIN',lambda:self._live_go_send('EVM native coin'))
        self._live_button(bar,'SEND ERC-20 TOKEN',lambda:self._live_go_send('ERC-20 token'))
        self.live_evm_status=tk.StringVar(value='No EVM network balance verified.')
        tk.Label(c,textvariable=self.live_evm_status,bg=CARD,fg=GREEN,wraplength=850,justify='left').pack(anchor='w',pady=12)
        self._live_line(c,'ETH and ERC-20 use Ethereum or another selected EVM chain, and network fees are paid in its native coin. A USDT or USDC token is NOT itself a distinct seed-based wallet.')
        self._live_line(c,'Use an existing registered .vault or encrypted Ethereum V3 keystore on the Send page. A public receiving address alone cannot authorize a spend.')
        self._live_line(c,'For a verified ERC-20 token balance, use a trusted explorer or contract method; this page displays native-coin balances only.')

    def _live_balance_evm(self):
        code=self.evm_code.get();url=self.evm_url.get().strip();address=self.live_public_evm.get().strip()
        def worker():
            w3=evm_w3(code,url)
            return (int(w3.eth.chain_id),int(w3.eth.block_number),evm_receive_balance(code,url,address))
        def done(data):self.live_evm_status.set(f'ON-CHAIN {code}: chain ID {data[0]}, block {data[1]} • {data[2]}')
        self.run_job(worker,done,'Checking EVM chain ID and native asset balance...')

    def _live_xmr(self):
        c=self._live_area('XMR / MONERO WALLET RPC / MAINNET')
        self._live_line(c,'Uses your locally running authenticated Monero wallet-RPC and its synchronized wallet file. NOCTURNE does not import Monero seeds into this service.')
        self._live_entry(c,'Monero wallet RPC URL (127.0.0.1)',self.xmr_url)
        self._live_entry(c,'RPC username',self.xmr_user)
        bar=tk.Frame(c,bg=CARD);bar.pack(fill='x',pady=8)
        self._live_button(bar,'REFRESH XMR BALANCE',self._live_balance_xmr)
        self._live_button(bar,'NEW MONERO SUBADDRESS',self._live_receive_xmr)
        self._live_button(bar,'SEND XMR',lambda:self._live_go_send('Monero wallet RPC XMR'))
        self.live_xmr_status=tk.StringVar(value='No Monero balance verified yet.')
        tk.Label(c,textvariable=self.live_xmr_status,bg=CARD,fg=GREEN,justify='left',wraplength=850).pack(anchor='w',pady=10)
        self._live_line(c,'If Monero wallet RPC uses a password, set it under Connections. It is kept in session memory only.')

    def _live_balance_xmr(self):
        def done(result):self.live_xmr_status.set(result[0]+' • '+str(len(result[1]))+' transfer records from wallet RPC')
        self.run_job(lambda:xmr_balance_history(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get()),done,'Reading Monero wallet RPC...')

    def _live_receive_xmr(self):
        def done(result):
            self.live_xmr_status.set('NEW MONERO SUBADDRESS: '+result[0]);self.show_address({'coin':'XMR','address':result[0],'label':'Monero RPC','derivation':result[1]},self.live_body)
        self.run_job(lambda:xmr_receive(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get()),done,'Requesting Monero subaddress...')
