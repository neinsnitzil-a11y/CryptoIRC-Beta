#!/usr/bin/env python3
"""Crypto & Creating Wallets — native Tkinter desktop suite (Windows / Linux).

Experimental self-custody software. No claims of hardware-wallet isolation or audit.
"""
from __future__ import annotations

import os, sys, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from decimal import Decimal
from enhanced import EnhancedFeatures
from professional_ui import ProfessionalUI
from financial_controls_ui import FinancialControlsUI
from operations_ui import OperationsUI
from live_crypto_ui import LiveCryptoUI
from btc_phase1_ui import BitcoinPhaseOneUI
from phase23_ui import ChainPhaseUI
from phase4_ui import PhaseFourUI
from unified_wallet_ui import UnifiedWalletUI
from chain_expansion_ui import ChainExpansionUI
from universal_transactions_ui import UniversalTransactionsUI
from token_center_ui import TokenCenterUI
from node_health_ui import NodeHealthUI
from portfolio_ui import PortfolioUI
from banking_rails_ui import BankingRailsUI
from vault_security_ui import VaultSecurityUI
from live_balance_ui import LiveBalanceUI
from performance_ui import PerformanceUI
from reliability_ui import ReliabilityUI
from financial_experience_ui import FinancialExperienceUI
from compliance_ui import ComplianceUI
from qa_ui import QAUI
from release_ops_ui import ReleaseOpsUI
from reliability_runtime import ReliabilityQueue
from performance_runtime import DesktopExecutor, QueueSaturated
from wallet_funding_ui import WalletFundingUI
from brand_theme import load_image, PURPLE, GREEN, RED
from fiat_payments_ui import FiatPaymentsUI
from exchange_ui import ExchangeUI
from peer_ui import PeerUI
from lan_chat_ui import LANChatUI
from wan_chat_ui import WANChatUI
from mesh_gui import MeshGUI
from trading_terminal_ui import TradingTerminalUI
from urllib.parse import quote
from backend import (
    tx, vf, read_vault, public_wallets, build_wallets, verify_public_address,
    load_registry, save_registry, btc_wallets, btc_receive, btc_balance_history,
    xmr_receive, xmr_balance_history, evm_receive_balance, prepare_btc,
    prepare_xmr, prepare_evm, execute_plan, EVM_TO_VAULT, TOKEN_NETWORK_ASSETS,
)

APP_NAME = 'CRYPTO  //  NOCTURNE'
BG='#07060b'; SIDE='#0b0811'; CARD='#15101e'; FG='#f2edf9'; MUTED='#a39ab6';
ACCENT='#47fca3'; ACTIVE='#302047'; FIELD='#0c0914'; BORDER='#3b2654'; WARN='#ff707a'


def styled_label(parent, text='', size=11, bold=False, fg=FG, bg=None, **kwargs):
    return tk.Label(parent,text=text,fg=fg,bg=bg or parent.cget('bg'),font=('Segoe UI',size,'bold' if bold else 'normal'),**kwargs)


def panel(parent, pad=15):
    return tk.Frame(parent,bg=CARD,highlightthickness=1,highlightbackground=BORDER,padx=pad,pady=pad)


def field(parent, label, var, width=42, secret=False, row=None, col=None):
    container=tk.Frame(parent,bg=parent.cget('bg'))
    styled_label(container,label,size=10,fg=MUTED).pack(anchor='w',pady=(0,5))
    w=ttk.Entry(container,textvariable=var,width=width,show='●' if secret else '')
    w.pack(fill='x')
    if row is not None: container.grid(row=row,column=col,sticky='ew',padx=6,pady=7)
    else: container.pack(fill='x',pady=6)
    return w


def action(parent,text,func,style='Accent.TButton'):
    b=ttk.Button(parent,text=text,command=func,style=style)
    return b


def safe_err(exc):
    # Debuggable source location with absolutely no exception values or secrets.
    from wallet_runtime import wallet_error_summary
    return wallet_error_summary(exc)


class CryptoSuite(TradingTerminalUI, ReleaseOpsUI, QAUI, ComplianceUI, FinancialExperienceUI, ReliabilityUI, VaultSecurityUI, BankingRailsUI, PortfolioUI, NodeHealthUI, TokenCenterUI, UniversalTransactionsUI, ChainExpansionUI, UnifiedWalletUI, PhaseFourUI, ChainPhaseUI, BitcoinPhaseOneUI, PerformanceUI, LiveBalanceUI, WalletFundingUI, LiveCryptoUI, OperationsUI, FinancialControlsUI, ProfessionalUI, MeshGUI, WANChatUI, LANChatUI, PeerUI, ExchangeUI, FiatPaymentsUI, EnhancedFeatures):
    def __init__(self):
        self.root=tk.Tk()
        self.root.title(APP_NAME+'   //   v4.5.1 · MONEY HUB')
        self.root.geometry('1440x920'); self.root.minsize(1080,720)
        self.root.configure(bg=BG)
        self._window_icon=load_image('tor_round.png',(64,64))
        if self._window_icon is not None:
            try: self.root.iconphoto(True,self._window_icon)
            except tk.TclError: pass
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.executor=DesktopExecutor(self.root,workers=4,queued=32)
        self.executor.start()
        self.reliability=ReliabilityQueue()
        self.apply_theme()
        try: self.vault_paths,self.watch=load_registry()
        except Exception: self.vault_paths,self.watch=[],[]
        self._hub_target=None
        self._last_wallet_selection=None
        self.public_unlocked={} # keys are vault paths; values PUBLIC entries only, no seed phrases
        self.current_page='Dashboard'
        self.qr_photo=None
        self.active_plan=None
        self.pending=False
        self.last_interaction=time.monotonic()
        self.root.bind_all('<KeyPress>',self.track_activity,add='+')
        self.root.bind_all('<Button>',self.track_activity,add='+')
        self.root.after(30000,self.check_idle_lock)
        self.btc_url=tk.StringVar(value='http://127.0.0.1:8332')
        self.btc_cookie=tk.StringVar(value=str(Path.home()/('AppData/Roaming/Bitcoin/.cookie' if os.name=='nt' else '.bitcoin/.cookie')))
        self.btc_name=tk.StringVar(value='')
        self.xmr_url=tk.StringVar(value='http://127.0.0.1:18082')
        self.xmr_user=tk.StringVar(value='')
        self.xmr_password=tk.StringVar(value='') # Session only, never saved
        self.evm_url=tk.StringVar(value='')
        self.evm_code=tk.StringVar(value='ETH')
        self.init_live_balance()
        self.default_folder=tk.StringVar(value=str(Path.home()/'CryptoWallets'))
        self.status=tk.StringVar(value='READY  •  No node connected  •  No secret saved in session')
        self.init_peer()
        self.init_lan_chat()
        self.init_wan()
        self.init_mesh_gui()
        self._brand_images={}  # Tk images must retain Python references
        self.left=tk.Frame(self.root,bg=SIDE,width=260)
        self.left.pack(side='left',fill='y')
        self.left.pack_propagate(False)
        tk.Frame(self.left,bg=PURPLE,height=4).pack(fill='x')
        brand_header=tk.Frame(self.left,bg=SIDE,padx=13,pady=17)
        brand_header.pack(fill='x')
        emblem=load_image('tor_round.png',(72,72))
        if emblem is not None:
            self._brand_images['tor_sidebar']=emblem
            tk.Label(brand_header,image=emblem,bg=SIDE,bd=0).pack(side='left',padx=(0,11))
        brand_words=tk.Frame(brand_header,bg=SIDE)
        brand_words.pack(side='left',fill='x')
        tk.Label(brand_words,text='C R Y P T O',fg=ACCENT,bg=SIDE,
                 font=('Consolas',15,'bold')).pack(anchor='w')
        tk.Label(brand_words,text='N O C T U R N E',fg=PURPLE,bg=SIDE,
                 font=('Consolas',9,'bold')).pack(anchor='w',pady=(5,0))
        tk.Label(brand_words,text='v4.5.1  /  SHADOW',fg=MUTED,bg=SIDE,
                 font=('Consolas',8)).pack(anchor='w',pady=(4,0))
        tk.Frame(self.left,bg='#39244f',height=1).pack(fill='x',padx=13)
        # No claim that Tor is enabled; the icon is purely visual branding.
        footer=tk.Frame(self.left,bg=SIDE)
        footer.pack(side='bottom',fill='x',padx=12,pady=(8,10))
        tk.Label(footer,text='●  WALLET FILES: LOCAL',bg=SIDE,fg=ACCENT,
                 font=('Consolas',8,'bold'),anchor='w').pack(anchor='w')
        tk.Label(footer,text='◌  TOR: NOT VERIFIED',bg=SIDE,fg=PURPLE,
                 font=('Consolas',8,'bold'),anchor='w').pack(anchor='w',pady=(5,0))
        tk.Label(footer,text='PEER CHAT ≠ PRIVATE KEYS',bg=SIDE,fg=MUTED,
                 font=('Consolas',8),anchor='w').pack(anchor='w',pady=(6,0))
        footer_mark=tk.Frame(footer,bg=SIDE)
        footer_mark.pack(fill='x',pady=(7,0))
        skull_mark=load_image('skull_green.png',(61,69))
        if skull_mark is not None:
            self._brand_images['sidebar_skull']=skull_mark
            tk.Label(footer_mark,image=skull_mark,bg=SIDE,bd=0).pack(side='left')
        tk.Label(footer_mark,text='NOCTURNE\nSHADOW SYSTEM\n—  v4.5.1',bg=SIDE,fg=PURPLE,
                 font=('Consolas',8,'bold'),justify='left').pack(side='left',padx=(7,0))
        self.nav_scrollbar=ttk.Scrollbar(self.left,orient='vertical')
        self.nav_scrollbar.pack(side='right',fill='y')
        self.nav_canvas=tk.Canvas(self.left,bg=SIDE,highlightthickness=0,borderwidth=0,
                                  yscrollcommand=self.nav_scrollbar.set)
        self.nav_canvas.pack(side='left',fill='both',expand=True)
        self.nav_scrollbar.configure(command=self.nav_canvas.yview)
        self.nav_panel=tk.Frame(self.nav_canvas,bg=SIDE)
        self.nav_window=self.nav_canvas.create_window((0,0),window=self.nav_panel,anchor='nw')
        self.nav_panel.bind('<Configure>',lambda e:self.nav_canvas.configure(scrollregion=self.nav_canvas.bbox('all')))
        self.nav_canvas.bind('<Configure>',lambda e:self.nav_canvas.itemconfigure(self.nav_window,width=e.width))
        def nav_wheel(event):
            self.nav_canvas.yview_scroll(-1 if getattr(event,'delta',0)>0 or event.num==4 else 1,'units')
            return 'break'
        self.nav_canvas.bind('<MouseWheel>',nav_wheel)
        self.nav_canvas.bind('<Button-4>',nav_wheel)
        self.nav_canvas.bind('<Button-5>',nav_wheel)
        self.nav={}
        nav_groups=(
            ('WORKSPACE', ('Dashboard','Trading Terminal','Money Hub','Portfolio','Unified Wallets','Chain Expansion','Universal Transactions','Token Center','Blockchain Health','Asset Coverage','BTC Phase 1','EVM Phase 2','Monero Phase 3','Live Crypto','Create Wallet')),
            ('ACCOUNTS', ('Fiat Accounts','Crypto Vault','Stablecoins','Wallets','Fiat Ledger')),
            ('MONEY MOVEMENT', ('Banking Rails','Phase 4 Funding','Wallet Funding','Receive','Send','Transactions','Fiat Payments','Currency Exchange')),
            ('NETWORK / P2P', ('Mesh Network','Peer to Peer','IRC LAN Chat','Internet Chat')),
            ('PROTECTION', ('Recovery','Connections','Security','Vault Security','Compliance Center','QA Center','Release Center','Financial Controls','Operations Center','Performance Center','Reliability Center')),
        )
        self.nav_scrollbar.configure(style='Vertical.TScrollbar')
        for label,items in nav_groups:
            tk.Label(self.nav_panel,text='  '+label,bg=SIDE,fg=PURPLE,
                     font=('Consolas',9,'bold'),anchor='w').pack(fill='x',padx=13,pady=(13,5))
            for item in items:
                btn=tk.Button(self.nav_panel,text='   '+item,anchor='w',bg=SIDE,fg=FG,
                              activebackground=ACTIVE,activeforeground=ACCENT,relief='flat',borderwidth=0,
                              font=('Consolas',10),cursor='hand2',highlightthickness=0,
                              command=lambda n=item:self.show(n))
                btn.pack(fill='x',padx=10,pady=1,ipady=7)
                btn.bind('<MouseWheel>',nav_wheel)
                btn.bind('<Button-4>',nav_wheel)
                btn.bind('<Button-5>',nav_wheel)
                self.nav[item]=btn
        self.body=tk.Frame(self.root,bg=BG);self.body.pack(side='left',expand=True,fill='both')
        tk.Label(self.body,textvariable=self.status,bg=SIDE,fg=MUTED,font=('Consolas',9),anchor='w',
                 padx=17,pady=8).pack(side='bottom',fill='x')
        topbar=tk.Frame(self.body,bg=SIDE,height=53,highlightbackground=BORDER,highlightthickness=1)
        topbar.pack(side='top',fill='x');topbar.pack_propagate(False)
        tk.Label(topbar,text='//  NOCTURNE    •    VAULT / FIAT / COMMS',
                 fg=PURPLE,bg=SIDE,font=('Consolas',10,'bold')).pack(side='left',padx=21)
        ttk.Button(topbar,text='LOCK PUBLIC VIEW',command=self.lock_public_view,
                   style='TButton').pack(side='right',padx=17,pady=7)
        tk.Label(topbar,text='●  SECRETS STAY LOCAL',fg=ACCENT,bg=SIDE,
                 font=('Consolas',9,'bold')).pack(side='right',padx=(0,12))
        self.viewport=tk.Canvas(self.body,bg=BG,highlightthickness=0,borderwidth=0)
        self.scrollbar=ttk.Scrollbar(self.body,orient='vertical',command=self.viewport.yview)
        self.viewport.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side='right',fill='y')
        self.viewport.pack(fill='both',expand=True)
        self.content=tk.Frame(self.viewport,bg=BG,padx=30,pady=25)
        self.canvas_window=self.viewport.create_window((0,0),window=self.content,anchor='nw')
        self.content.bind('<Configure>',lambda e:self.viewport.configure(scrollregion=self.viewport.bbox('all')))
        self.viewport.bind('<Configure>',lambda e:self.viewport.itemconfigure(self.canvas_window,width=e.width))
        self.viewport.bind('<MouseWheel>',lambda e:self.viewport.yview_scroll(-1 if e.delta>0 else 1,'units'))
        self.show('Dashboard')

    def lock_public_view(self):
        self.public_unlocked.clear()
        self.active_plan=None
        self.xmr_password.set('')
        for name in ('p_pw','p_confirm','p_extra','f_password','f_password2','newpw','repeatpw','extra','import_phrase'):
            var=getattr(self,name,None)
            if var is not None:var.set('')
        self.status.set('LOCKED  •  Public vault session cleared')
        if self.current_page in ('Wallets','Receive'):
            self.show(self.current_page)

    def apply_theme(self):
        s=ttk.Style();s.theme_use('clam')
        s.configure('TFrame',background=BG)
        s.configure('TLabel',background=BG,foreground=FG,font=('Segoe UI',10))
        s.configure('TEntry',fieldbackground=FIELD,foreground=FG,insertcolor=FG,background=FIELD,
                    bordercolor=BORDER,lightcolor=BORDER,darkcolor=BORDER,padding=8)
        s.configure('TSpinbox',fieldbackground=FIELD,foreground=FG,arrowsize=13,padding=5)
        s.configure('TCombobox',fieldbackground=FIELD,background=FIELD,foreground=FG,arrowcolor=ACCENT,
                    selectbackground=FIELD,selectforeground=FG,padding=7)
        s.map('TCombobox',fieldbackground=[('readonly',FIELD)],foreground=[('readonly',FG)],
              selectbackground=[('readonly',FIELD)],selectforeground=[('readonly',FG)],background=[('readonly',FIELD)])
        s.configure('Purple.TButton',font=('Consolas',9,'bold'),padding=(12,9),background='#442564',foreground='#f8efff',bordercolor='#603388')
        s.map('Purple.TButton',background=[('active','#673594')])
        s.configure('TButton',font=('Consolas',9,'bold'),padding=(12,9),background=CARD,foreground=FG,
                    bordercolor=BORDER)
        s.map('TButton',background=[('active',ACTIVE)])
        s.configure('Accent.TButton',background='#136a45',foreground='#ffffff',font=('Consolas',9,'bold'),padding=(14,10))
        s.map('Accent.TButton',background=[('active','#1d8b5e')])
        s.configure('Treeview',background=FIELD,foreground=FG,fieldbackground=FIELD,
                    rowheight=29,borderwidth=0,font=('Segoe UI',10))
        s.configure('Treeview.Heading',background=SIDE,foreground=ACCENT,font=('Segoe UI',10,'bold'))
        s.map('Treeview',background=[('selected',ACTIVE)],foreground=[('selected',ACCENT)])
        s.configure('TCheckbutton',background=CARD,foreground=FG,font=('Segoe UI',10))
        s.configure('Vertical.TScrollbar',background=FIELD,troughcolor=SIDE,arrowcolor=ACCENT)
        s.map('TCheckbutton',background=[('active',CARD)],foreground=[('active',ACCENT)])
        self.root.option_add('*TCombobox*Listbox.background',FIELD)
        self.root.option_add('*TCombobox*Listbox.foreground',FG)
        self.root.option_add('*TCombobox*Listbox.selectBackground',ACTIVE)

    def track_activity(self,event=None):
        self.last_interaction=time.monotonic()

    def check_idle_lock(self):
        if time.monotonic()-self.last_interaction >= 300 and not self.pending:
            self.public_unlocked.clear();self.active_plan=None
            self.xmr_password.set('')
            for secret_var in ('p_pw','p_confirm','p_extra','f_password','f_password2',
                               'newpw','repeatpw','extra','import_phrase','fiat_pay_password','fv_password','rails_token'):
                v=getattr(self,secret_var,None)
                if v is not None: v.set('')
            self.status.set('AUTO-LOCKED after 5 minutes idle • public vault views locked')
            if self.current_page=='Receive':self.show('Receive')
            self.last_interaction=time.monotonic()
        self.root.after(30000,self.check_idle_lock)

    def clear(self):
        # Tk variables outlive destroyed widgets: wipe masked fields on every view change.
        for secret_var in ('p_pw','p_confirm','p_extra','f_password','f_password2',
                           'newpw','repeatpw','extra','import_phrase',
                           'fiat_pay_password','fv_password','rails_token'):
            v=getattr(self,secret_var,None)
            if v is not None: v.set('')
        self.active_plan=None  # Changing screens discards any unsubmitted transfer
        for w in self.content.winfo_children():w.destroy()
        self.viewport.yview_moveto(0)
        self.qr_photo=None

    def show(self,page):
        if self.pending:
            messagebox.showwarning('Operation running','Complete the current operation before switching sections.');return
        if self.current_page=='Monero Phase 3' and page!='Monero Phase 3':
            svc=getattr(self,'_p3_instance',None)
            if svc is not None and svc._session_metadata:
                messagebox.showwarning('Monero transfer prepared',
                    'Authorize or CANCEL the unrelayed Monero transfer before leaving. This prevents losing in-memory relay metadata.',parent=self.root)
                return
            self._p3_instance=None
        if self.current_page=='Trading Terminal' and page!='Trading Terminal' and hasattr(self,'trade_stop'):
            self.trade_stop.set()
        self.current_page=page;self.lb_epoch+=1;self.clear()
        for n,btn in self.nav.items():btn.configure(bg=ACTIVE if n==page else SIDE,fg=ACCENT if n==page else FG)
        getattr(self,'page_'+page.lower().replace(' ','_'))()

    def head(self,title,desc):
        styled_label(self.content,'// '+title.upper(),23,True,fg=ACCENT).pack(anchor='w')
        styled_label(self.content,desc,10,fg=MUTED,wraplength=860,justify='left').pack(anchor='w',pady=(4,17))

    def info(self,parent,text,fg=MUTED):
        styled_label(parent,text,10,fg=fg,wraplength=800,justify='left').pack(anchor='w',pady=5)

    def run_job(self,func,done,working='WORKING...'):
        if self.pending:
            messagebox.showwarning('Busy','Finish the current operation first.');return
        self.pending=True;self.status.set(working)
        def deliver(result):
            self.pending=False
            self.status.set('READY')
            done(result)
        def stopped(kind):
            self.pending=False
            self.status.set('STOPPED • '+kind)
            # A background exception may carry secrets; do not show exception text.
            messagebox.showerror('Operation stopped',
                'Operation failed: '+kind+'. Check connection/settings. No wallet secrets were logged.')
        try:self.executor.submit(func,deliver,stopped,lane='financial')
        except (QueueSaturated,RuntimeError) as exc:
            self.pending=False
            self.status.set('BUSY • Background queue saturated')
            messagebox.showwarning('Busy',str(exc))

    def close(self):
        if self.pending and not messagebox.askyesno('Operation running',
            'An operation is running. A broadcast may be in flight. Close anyway?'):
            return
        self.public_unlocked.clear();self.active_plan=None
        self._hub_target=None
        self.lb_closed=True
        self.executor.close()
        svc=getattr(self,'_p3_instance',None)
        if svc is not None:svc._session_metadata.clear()
        self._p3_instance=None
        self.xmr_password.set('')
        self.chat_stop_discovery()
        self.wan_stop_connection()
        self.mesh_stop()
        if hasattr(self,'trade_stop'):self.trade_stop.set()
        if self.peer_hub: self.peer_hub.close()
        if hasattr(self,'tor_controller'):self.tor_controller.stop()
        for secret_var in ('p_pw','p_confirm','p_extra','f_password','f_password2',
                           'newpw','repeatpw','extra','import_phrase','fiat_pay_password','fv_password','rails_token'):
            v=getattr(self,secret_var,None)
            if v is not None: v.set('')
        self.root.destroy()

    def persist(self):
        save_registry(self.vault_paths,self.watch)

    def card(self):
        c=panel(self.content); c.pack(fill='x',pady=7)
        return c

    def legacy_page_dashboard(self):
        self.head('Your crypto workspace','Create encrypted wallets, receive via QR, and send through verified signing paths.')
        c=self.card()
        styled_label(c,f'{len(self.vault_paths)} encrypted vault files   •   {len(self.watch)} watch-only addresses   •   crypto, stablecoin & fiat account selection',16,True).pack(anchor='w',pady=7)
        self.info(c,'Existing crypto wallets and fiat ledgers remain encrypted. Fiat payments and exchanges require authorized external providers. Reference quotes never credit local balances.')
        quick=tk.Frame(c,bg=CARD);quick.pack(anchor='w',pady=10)
        for label,dst in (('Trading Terminal','Trading Terminal'),('Create Wallet','Create Wallet'),('Browse Wallets','Wallets'),('Add Money','Wallet Funding'),('Internet Chat','Internet Chat'),('Exchange','Currency Exchange'),('Receive Crypto','Receive')):
            action(quick,label,lambda p=dst:self.show(p)).pack(side='left',padx=(0,10))
        c2=self.card(); styled_label(c2,'NETWORK AND SIGNING COVERAGE',13,True,fg=ACCENT).pack(anchor='w')
        self.info(c2,'Create/receive: 30 native asset choices plus network-specific USDT/USDC/DAI receiving addresses; fiat bookkeeping is offline only.')
        self.info(c2,'Live sends: Bitcoin Core BTC, Monero wallet-RPC XMR, 10 EVM networks and ERC-20 tokens. Other coins are NOT send-capable in this release.')
        self.info(c2,'Transactions require your own local Bitcoin/Monero node or a trusted EVM RPC. EVM signs with a standard encrypted keystore or matching unlocked vault (password asked again).')
        c3=self.card();styled_label(c3,'BEFORE FUNDING',13,True,fg=WARN).pack(anchor='w')
        self.info(c3,'A USB-stored .vault is NOT a true hardware wallet. This software has not been security audited. Confirm the exact network/address on an independent trusted wallet, restore a test backup, and start with tiny amounts.',WARN)

    def page_wallets(self):
        return self.hub_page_wallets()

    def page_wallet_funding(self):
        return self.hub_page_funding()

    def selected_path(self):
        tree=getattr(self,'wallet_tree',None)
        chosen=tree.selection() if tree else ()
        if not chosen: raise ValueError('Select a vault first')
        return chosen[0]

    def add_vault(self):
        path=filedialog.askopenfilename(title='Select existing encrypted VaultForge wallet',filetypes=[('Encrypted VaultForge','*.vault')])
        if path:
            if Path(path).is_symlink() or not Path(path).is_file():
                messagebox.showerror('Error','Use a regular .vault file');return
            if path not in self.vault_paths:self.vault_paths.append(path);self.persist()
            self.show('Wallets')

    def scan_folder(self):
        path=filedialog.askdirectory(title='Directory with encrypted wallets')
        if path:
            for f in Path(path).glob('*.vault'):
                if not f.is_symlink() and str(f) not in self.vault_paths:
                    self.vault_paths.append(str(f))
            self.persist();self.show('Wallets')

    def remove_vault(self):
        try:p=self.selected_path()
        except ValueError as e:messagebox.showwarning('Choose wallet',str(e));return
        if messagebox.askyesno('Remove from list','Remove this wallet reference from the app? The encrypted wallet file will NOT be deleted.'):
            self.vault_paths.remove(p);self.public_unlocked.pop(p,None);self.persist();self.show('Wallets')

    def unlock_selected(self):
        try:path=self.selected_path()
        except ValueError as e:messagebox.showwarning('Choose wallet',str(e));return
        pw=simpledialog.askstring('Unlock vault','Vault encryption password (never saved):',parent=self.root,show='●')
        if not pw:return
        def run():return public_wallets(path,pw)
        def done(rows):
            self.public_unlocked[path]=rows
            self._last_wallet_selection=path
            self.show('Wallets')
            messagebox.showinfo('Unlocked public view',f'{len(rows)} public receiving address(es) loaded. Recovery secrets are not retained in this view.')
        self.run_job(run,done,'Decrypting .vault for PUBLIC addresses...')

    def choose_usb(self):
        try: drives=vf.discover_usb()
        except Exception as e: messagebox.showerror('USB detection',safe_err(e));return
        if not drives:
            messagebox.showinfo('USB','No mounted USB drives detected. You can still browse any mounted volume.');return
        win=tk.Toplevel(self.root);win.title('Choose a mounted USB');win.configure(bg=BG);win.geometry('550x260');win.transient(self.root);win.grab_set()
        styled_label(win,'Mounted removable storage',17,True,bg=BG).pack(pady=10)
        lb=tk.Listbox(win,bg=FIELD,fg=FG,selectbackground=ACTIVE,selectforeground=ACCENT,font=('Consolas',10))
        lb.pack(fill='both',expand=True,padx=15,pady=10)
        for item in drives:lb.insert('end',str(item))
        def select():
            idx=lb.curselection()
            if not idx:return
            entry=drives[idx[0]]
            base=entry.get('path') if isinstance(entry,dict) else (entry[0] if isinstance(entry,(list,tuple)) else str(entry))
            self.default_folder.set(str(Path(base)/'CryptoWallets'))
            win.destroy()
        action(win,'Use this USB volume',select).pack(pady=10)

    def legacy_page_create_wallet(self):
        self.head('Create or import wallets','Choose up to 30 chains, a device or folder, seed length and number of independent encrypted vault sets.')
        outer=tk.Frame(self.content,bg=BG);outer.pack(fill='both',expand=True)
        left=panel(outer);left.pack(side='left',fill='both',expand=True,padx=(0,12));right=panel(outer);right.pack(side='left',fill='y')
        styled_label(left,'1  •  Coin selection',14,True,fg=ACCENT).pack(anchor='w')
        items=tk.Frame(left,bg=CARD);items.pack(fill='both',expand=True,pady=10)
        self.coinlist=tk.Listbox(items,selectmode='multiple',height=13,bg=FIELD,fg=FG,selectbackground=ACTIVE,
                                 selectforeground=ACCENT,font=('Consolas',10),exportselection=False)
        self.coinlist.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(items,orient='vertical',command=self.coinlist.yview);scroll.pack(side='right',fill='y');self.coinlist.config(yscrollcommand=scroll.set)
        for coin,desc,_,_ in vf.COINS:self.coinlist.insert('end',f'{coin:8}  {desc}')
        buttonbar=tk.Frame(left,bg=CARD);buttonbar.pack(fill='x')
        action(buttonbar,'All 30',lambda:self.coinlist.selection_set(0,'end'),style='TButton').pack(side='left')
        action(buttonbar,'BTC + ETH + XMR',self.select_default_coins,style='TButton').pack(side='left',padx=6)
        action(buttonbar,'Clear',lambda:self.coinlist.selection_clear(0,'end'),style='TButton').pack(side='left')
        self.coinlist.selection_set(0)
        styled_label(right,'2  •  Storage & encryption',14,True,fg=ACCENT).pack(anchor='w')
        self.folder_entry=field(right,'Save encrypted .vault files in',self.default_folder,width=41)
        b=tk.Frame(right,bg=CARD);b.pack(fill='x')
        action(b,'Browse folder',self.pick_folder,style='TButton').pack(side='left')
        action(b,'Find USB',self.choose_usb,style='TButton').pack(side='left',padx=7)
        self.count_var=tk.StringVar(value='1');field(right,'Independent wallet sets (1-20)',self.count_var)
        self.words_var=tk.StringVar(value='24')
        row=tk.Frame(right,bg=CARD);row.pack(fill='x',pady=5)
        styled_label(row,'BIP39 seed size',10,fg=MUTED).pack(side='left',padx=(0,14))
        ttk.Combobox(row,values=['12','24'],textvariable=self.words_var,state='readonly',width=10).pack(side='left')
        self.newpw=tk.StringVar();self.repeatpw=tk.StringVar()
        field(right,'Vault encryption password (14+ chars)',self.newpw,secret=True)
        field(right,'Repeat vault encryption password',self.repeatpw,secret=True)
        self.extra=tk.StringVar()
        field(right,'Optional BIP39 extra passphrase',self.extra,secret=True)
        self.import_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(right,text='Import my existing recovery phrase',variable=self.import_var,
                        command=self.toggle_import).pack(anchor='w',pady=(10,0))
        self.import_phrase=tk.StringVar()
        self.import_widget=field(right,'Existing phrase (never saved plaintext)',self.import_phrase,secret=True)
        self.import_widget.master.pack_forget()
        action(right,'Create encrypted wallet(s)',self.create_wallet).pack(fill='x',pady=13)
        self.info(right,'XMR always gets a separate native 25-word Monero phrase. Other selected coins share one BIP39 phrase per vault set. Imported XMR must be selected alone.',WARN)

    def toggle_import(self):
        if self.import_var.get():self.import_widget.master.pack(fill='x',pady=4)
        else:self.import_widget.master.pack_forget()

    def select_default_coins(self):
        self.coinlist.selection_clear(0,'end')
        for i,c in enumerate(vf.COINS):
            if c[0] in ('BTC','ETH','XMR'):self.coinlist.selection_set(i)

    def pick_folder(self):
        folder=filedialog.askdirectory(title='Choose computer or mounted USB storage')
        if folder:self.default_folder.set(folder)

    def create_wallet(self):
        coins=[vf.COINS[i][0] for i in self.coinlist.curselection()]
        pw=self.newpw.get();re=self.repeatpw.get();phrase=self.import_phrase.get().strip() if self.import_var.get() else ''
        try:
            count=int(self.count_var.get()); words=int(self.words_var.get())
            if pw!=re:raise ValueError('Passwords do not match')
            if not coins:raise ValueError('Choose at least one currency')
            if self.import_var.get() and not phrase:raise ValueError('Import selected: enter the existing recovery phrase')
            if phrase and not messagebox.askyesno('Sensitive import','Importing an existing seed on an internet-connected or compromised computer could expose all funds. Continue?'):
                return
            if not messagebox.askyesno('Create encrypted SOFTWARE wallets',
                f'Create {count} encrypted wallet set(s) for {len(coins)} chain(s) in:\n{self.default_folder.get()}\n\nThis is NOT a hardware wallet. Confirm you can back up and restore seeds before funding.'):
                return
            folder=self.default_folder.get();extra=self.extra.get()
            self.import_phrase.set('');self.newpw.set('');self.repeatpw.set('');self.extra.set('')
            # password and phrase are in transient GUI memory; clear immediately after creating
            def worker():return build_wallets(folder,coins,count,words,pw,extra,phrase)
            def done(paths):
                self.newpw.set('');self.repeatpw.set('');self.import_phrase.set('');self.extra.set('')
                for path in paths:
                    if path not in self.vault_paths:self.vault_paths.append(path)
                self.persist()
                messagebox.showinfo('Encrypted vault(s) created',f'{len(paths)} vault file(s) saved.\n\nCRITICAL: Go to Security → Reveal / Verify recovery backup and write the seed phrase(s) offline before depositing anything.')
                self.show('Wallets')
            self.run_job(worker,done,'Generating and encrypting wallet sets locally...')
        except Exception as e:messagebox.showerror('Unable to create',safe_err(e))

    def _public_rows(self):
        rows=[]
        for path, entries in self.public_unlocked.items():
            for entry in entries:
                rows.append({'label':Path(path).name,'coin':entry['coin'],'address':entry['address'],
                            'derivation':entry.get('derivation',''),'network':entry.get('network',entry['coin']), 'warning':entry.get('warning',''),'path':path,'kind':'Vault public'})
        for entry in self.watch:
            rows.append({'label':entry['label'],'coin':entry['coin'],'address':entry['address'],
                         'derivation':'Imported watch-only public address','path':'','kind':'Watch-only'})
        return rows

    def page_receive(self):
        self.head('Receive cryptocurrency','Show receiving addresses and QR codes. A disconnected USB can still receive crypto on-chain.')
        c=self.card()
        self.receive_type=tk.StringVar(value='Vault / watch-only')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x',pady=6)
        styled_label(row,'Receive source:',fg=MUTED).pack(side='left',padx=(0,10))
        combo=ttk.Combobox(row,values=['Vault / watch-only','Bitcoin Core','Monero wallet RPC'],
                           textvariable=self.receive_type,state='readonly',width=25)
        combo.pack(side='left');combo.bind('<<ComboboxSelected>>',lambda e:self.update_receive())
        action(row,'Add watch-only address',self.add_watch,style='TButton').pack(side='left',padx=10)
        action(row,'ADD MONEY / CARD',lambda:self.show('Wallet Funding')).pack(side='left',padx=6)
        self.receive_content=tk.Frame(self.content,bg=BG);self.receive_content.pack(fill='both',expand=True)
        self.update_receive()

    def add_watch(self):
        win=tk.Toplevel(self.root);win.configure(bg=BG);win.geometry('590x340');win.title('Add watch-only receiving address');win.transient(self.root);win.grab_set()
        c=panel(win);c.pack(fill='both',expand=True,padx=14,pady=14)
        label=tk.StringVar();coin=tk.StringVar(value='BTC');addr=tk.StringVar()
        field(c,'Label',label)
        styled_label(c,'Coin or network',fg=MUTED).pack(anchor='w')
        ttk.Combobox(c,values=[x[0] for x in vf.COINS],textvariable=coin,state='readonly').pack(fill='x')
        field(c,'Public receiving address ONLY (no seed / private key)',addr)
        def add():
            if not label.get().strip() or not verify_public_address(coin.get(),addr.get().strip()):
                messagebox.showerror('Validation','Enter a label and a plausible public address. This is NOT full chain validation.',parent=win);return
            self.watch.append({'label':label.get().strip(),'coin':coin.get(),'address':addr.get().strip()});self.persist()
            win.destroy();self.update_receive()
        action(c,'Add to public address book',add).pack(anchor='w',pady=10)
        self.info(c,'Address validation for watch-only imports is only a format check. Verify ownership and network externally before receiving.',WARN)

    def update_receive(self):
        for w in self.receive_content.winfo_children():w.destroy()
        typ=self.receive_type.get()
        c=panel(self.receive_content);c.pack(fill='both',expand=True,pady=7)
        if typ=='Vault / watch-only':
            rows=self._public_rows()
            if not rows:self.info(c,'No public wallets loaded. Go to Wallets → Unlock selected, or add a watch-only address.',WARN);return
            labels=[f"{r['coin']:9} | {r['label']} | {r['address'][:16]}…" for r in rows]
            select=tk.StringVar(value=labels[0]);self.receive_row=rows
            cb=ttk.Combobox(c,values=labels,textvariable=select,state='readonly',width=70);cb.pack(fill='x',pady=8)
            cb.bind('<<ComboboxSelected>>',lambda e:self.show_address(rows[labels.index(select.get())],c))
            self.show_address(rows[0],c)
        elif typ=='Bitcoin Core':
            self.info(c,'Requires a running, synced Bitcoin Core mainnet wallet with RPC configured in Connections.')
            action(c,'Generate new BTC receiving address',lambda:self.run_job(
                lambda:btc_receive(self.btc_url.get(),self.btc_cookie.get(),self.btc_name.get()),
                lambda value:self.show_address({'coin':'BTC','address':value[0],'label':self.btc_name.get(),'derivation':value[1]},c),
                'Requesting NEW receiving address from Bitcoin Core...')).pack(anchor='w',pady=12)
        else:
            self.info(c,'Creates a NEW private-use subaddress in your currently opened Monero mainnet wallet RPC (recommended for privacy).')
            action(c,'Generate new XMR subaddress',lambda:self.run_job(
                lambda:xmr_receive(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get()),
                lambda value:self.show_address({'coin':'XMR','address':value[0],'label':'Monero wallet RPC','derivation':value[1]},c),
                'Loading Monero receiving address...')).pack(anchor='w',pady=12)

    def show_address(self, entry, parent):
        if hasattr(self,'receive_display') and self.receive_display.winfo_exists(): self.receive_display.destroy()
        holder=tk.Frame(parent,bg=CARD);holder.pack(fill='both',expand=True,pady=12)
        self.receive_display=holder
        coin=entry['coin'];address=entry['address'];self.current_address=address
        styled_label(holder,f"{coin}  •  {entry['label']}",18,True,fg=ACCENT).pack(anchor='w',pady=(4,10))
        styled_label(holder,address,13,True,wraplength=700,justify='left').pack(anchor='w',pady=9)
        self.info(holder,'Network: '+entry.get('network',coin)+'  •  '+entry.get('derivation',''))
        if entry.get('warning'):self.info(holder,entry['warning'],WARN)
        qrframe=tk.Frame(holder,bg='white',padx=14,pady=14);qrframe.pack(anchor='w',pady=14)
        try:
            import qrcode
            from PIL import ImageTk
            pic=qrcode.QRCode(version=None,box_size=5,border=2,error_correction=qrcode.constants.ERROR_CORRECT_M)
            pic.add_data(address);pic.make(fit=True)
            img=pic.make_image(fill_color='black',back_color='white').convert('RGB')
            img.thumbnail((235,235))
            self.qr_photo=ImageTk.PhotoImage(img)
            tk.Label(qrframe,image=self.qr_photo,bg='white').pack()
        except ImportError:
            styled_label(qrframe,'QR support requires pillow and qrcode',fg='#202020',bg='white').pack()
        action(holder,'Copy PUBLIC address only',lambda a=address:self.copy_public(a),style='TButton').pack(anchor='w',pady=(1,6))
        self.info(holder,'Always verify the network and full receiving address in trusted wallet software. A QR does not prove the address belongs to you.',WARN)

    def copy_public(self,address):
        self.root.clipboard_clear();self.root.clipboard_append(address)
        messagebox.showinfo('Copied PUBLIC address','Receiving address copied. Check every character on the destination device after pasting; clipboard malware can replace addresses.')

    def page_send(self):
        self.head('Send cryptocurrency','Explicit two-stage transaction review. No background transfers, seed entry, bridging, swaps or automatic sends.')
        c=self.card();c.grid_columnconfigure(0,weight=1);c.grid_columnconfigure(1,weight=1)
        self.send_kind=tk.StringVar(value='EVM native coin')
        typebar=tk.Frame(c,bg=CARD);typebar.grid(row=0,column=0,columnspan=2,sticky='ew')
        styled_label(typebar,'Transfer method',fg=MUTED).pack(side='left',padx=(0,12))
        cb=ttk.Combobox(typebar,values=['EVM native coin','ERC-20 token','Bitcoin Core BTC','Monero wallet RPC XMR'],
                         textvariable=self.send_kind,state='readonly',width=28);cb.pack(side='left')
        cb.bind('<<ComboboxSelected>>',lambda e:self.rebuild_send_source())
        self.send_source=tk.Frame(c,bg=CARD);self.send_source.grid(row=1,column=0,columnspan=2,sticky='ew',pady=6)
        self.recipient=tk.StringVar();self.amount=tk.StringVar();self.fee_cap=tk.StringVar(value='0.01');self.token_contract=tk.StringVar()
        field(c,'DESTINATION • independently verify full address',self.recipient,row=2,col=0)
        field(c,'Amount in the sending asset',self.amount,row=2,col=1)
        field(c,'Maximum permitted network fee (native coin)',self.fee_cap,row=3,col=0)
        self.token_box=tk.Frame(c,bg=CARD);self.token_box.grid(row=3,column=1,sticky='ew')
        field(self.token_box,'Verified ERC-20 contract (this chain only)',self.token_contract)
        self.token_box.grid_remove()
        self.send_buttons=tk.Frame(c,bg=CARD);self.send_buttons.grid(row=4,column=0,columnspan=2,sticky='w',pady=10)
        action(self.send_buttons,'1. Prepare & review transaction',self.prepare_send).pack(side='left')
        tip=tk.Frame(c,bg=CARD);tip.grid(row=5,column=0,columnspan=2,sticky='ew')
        self.info(tip,'Preparing an XMR transaction reserves wallet outputs without relaying. BTC creates an unsigned PSBT. EVM estimates gas but does not sign until final authorization.',WARN)
        self.rebuild_send_source()

    def rebuild_send_source(self):
        self.active_plan=None
        for w in self.send_source.winfo_children():w.destroy()
        k=self.send_kind.get()
        self.token_box.grid() if k=='ERC-20 token' else self.token_box.grid_remove()
        if k.startswith('EVM') or k.startswith('ERC'):
            r=tk.Frame(self.send_source,bg=CARD);r.pack(fill='x',pady=8)
            styled_label(r,'Network: ',fg=MUTED).pack(side='left')
            codes=list(tx.COIN_NETWORKS)
            cb=ttk.Combobox(r,values=codes,textvariable=self.evm_code,state='readonly',width=13);cb.pack(side='left',padx=(0,12))
            styled_label(r,'Signer:',fg=MUTED).pack(side='left')
            self.signer_kind=tk.StringVar(value='VaultForge .vault')
            sg=ttk.Combobox(r,values=['VaultForge .vault','Encrypted Ethereum V3 keystore'],
                            textvariable=self.signer_kind,state='readonly',width=31)
            sg.pack(side='left');sg.bind('<<ComboboxSelected>>',lambda e:self.update_signer())
            field(self.send_source,'Trusted RPC HTTPS URL (or loopback HTTP)',self.evm_url)
            self.send_asset=tk.StringVar(value='Auto')
            pick=tk.Frame(self.send_source,bg=CARD);pick.pack(fill='x',pady=6)
            styled_label(pick,'Exact source asset (when vault holds more than one seed):',fg=MUTED).pack(side='left',padx=(0,10))
            asset_choices=['Auto']+sorted(set(EVM_TO_VAULT.values())|{a for choices in TOKEN_NETWORK_ASSETS.values() for a in choices})
            ttk.Combobox(pick,values=asset_choices,textvariable=self.send_asset,state='readonly',width=23).pack(side='left')
            self.info(self.send_source,'Choose the exact funded vault asset. Auto works only if the vault has ONE supported asset for this chain. Matching contract/network is still your responsibility.',WARN)
            self.signer_frame=tk.Frame(self.send_source,bg=CARD);self.signer_frame.pack(fill='x')
            self.signing_path=tk.StringVar()
            self.update_signer()
        elif k=='Bitcoin Core BTC':
            self.info(self.send_source,'BTC sending now uses BTC Phase 1 only: durable journal, explicit network, and ambiguous-broadcast reconciliation. Legacy direct BTC sending is disabled here.')
            action(self.send_source,'OPEN BTC PHASE 1',lambda:self.show('BTC Phase 1')).pack(anchor='w',pady=8)
            self.fee_cap.set('0.0005')
            styled_label(self.send_source,'Loaded wallet: '+(self.btc_name.get() or '[Choose in Connections]'),fg=ACCENT).pack(anchor='w')
        else:
            self.info(self.send_source,'Uses the locally running authenticated Monero wallet RPC set in Connections. Funds must be unlocked and wallet synced.')
            self.fee_cap.set('0.01')
        if k in ('EVM native coin','ERC-20 token'):self.fee_cap.set('0.01')

    def update_signer(self):
        for w in self.signer_frame.winfo_children():w.destroy()
        kind=self.signer_kind.get();field(self.signer_frame,'Signing file (encrypted .vault or Ethereum V3 JSON keystore)',self.signing_path)
        bar=tk.Frame(self.signer_frame,bg=CARD);bar.pack(anchor='w')
        action(bar,'Choose signing file',self.choose_signer_file,style='TButton').pack(side='left',padx=(0,8))
        if kind=='VaultForge .vault':
            action(bar,'Use registered vault',self.select_signer_vault,style='TButton').pack(side='left')
            self.info(self.signer_frame,'Vault signing is a HOT SOFTWARE signing operation: your computer sees the decrypted private key. Verify restored address before funding.',WARN)
        else:self.info(self.signer_frame,'Keystore password is only requested after preview and authorization. Never enter raw private keys or recovery phrases.')

    def choose_signer_file(self):
        kind=self.signer_kind.get()
        path=filedialog.askopenfilename(title='Choose encrypted signing file',filetypes=[('Vault','*.vault')] if kind=='VaultForge .vault' else [('Ethereum JSON','*.json'),('All files','*.*')])
        if path:self.signing_path.set(path)

    def select_signer_vault(self):
        choices=[p for p in self.vault_paths if Path(p).is_file()]
        if not choices:messagebox.showinfo('No wallet','Register a .vault file on the Wallets page.');return
        win=tk.Toplevel(self.root);win.title('Choose encrypted vault');win.configure(bg=BG);win.geometry('650x320');win.transient(self.root);win.grab_set()
        lb=tk.Listbox(win,bg=FIELD,fg=FG,font=('Consolas',10),selectbackground=ACTIVE);lb.pack(fill='both',expand=True,padx=12,pady=12)
        for p in choices:lb.insert('end',p)
        def choose():
            ch=lb.curselection()
            if ch:self.signing_path.set(choices[ch[0]]);win.destroy()
        action(win,'Use this vault',choose).pack(pady=8)

    def prepare_send(self):
        if self.pending:return
        self.active_plan=None
        k=self.send_kind.get();dest=self.recipient.get().strip();amount=self.amount.get().strip();cap=self.fee_cap.get().strip()
        if k=='Bitcoin Core BTC':
            messagebox.showinfo('Use BTC Phase 1','BTC sends require the persistent transaction journal. Open BTC Phase 1 to prepare, authorize and monitor the transaction.',parent=self.root)
            self.show('BTC Phase 1')
            return
        if not dest or not amount or not cap:messagebox.showwarning('Missing fields','Enter destination, amount and fee cap.');return
        if k=='Monero wallet RPC XMR' and not messagebox.askyesno('Prepare only, no relay',
            'The Monero RPC will construct a transaction that is NOT broadcast. This may temporarily reserve spendable outputs. Prepare now?'):
            return
        try:
            if k in ('EVM native coin','ERC-20 token'):
                path=self.signing_path.get().strip()
                if not path:raise ValueError('Select an encrypted vault or Ethereum keystore')
                kind='vault' if self.signer_kind.get()=='VaultForge .vault' else 'keystore'
                pw=''
                if kind=='vault':
                    pw=simpledialog.askstring('Unlock SOURCE vault for public preview',
                        'Vault password (private signing key is NOT derived until final authorization):',
                        parent=self.root,show='●')
                    if pw is None:return
                code=self.evm_code.get();url=self.evm_url.get().strip();contract=self.token_contract.get().strip() if k=='ERC-20 token' else ''
                if k=='ERC-20 token' and not contract:raise ValueError('Enter the independently verified ERC-20 contract')
                if contract and not messagebox.askyesno('Verify CONTRACT address',
                    f'Have you independently verified this exact contract address on {code}?\n\n{contract}\n\nToken names and symbols are not sufficient proof.'):
                    return
                job=lambda:prepare_evm(code,url,path,kind,pw,dest,amount,cap,contract,self.send_asset.get())
            elif k=='Bitcoin Core BTC':
                job=lambda:prepare_btc(self.btc_url.get(),self.btc_cookie.get(),self.btc_name.get(),dest,amount,cap)
            else:
                job=lambda:prepare_xmr(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get(),dest,amount,cap)
            def done(plan):
                self.active_plan=plan
                self.review_dialog(plan)
            self.run_job(job,done,'Preparing transfer for detailed review; nothing broadcast...')
        except Exception as e:messagebox.showerror('Send blocked',safe_err(e))

    def review_dialog(self,plan):
        win=tk.Toplevel(self.root);win.title('FINAL ON-CHAIN TRANSACTION REVIEW');win.configure(bg=BG)
        win.geometry('790x630');win.transient(self.root);win.grab_set()
        styled_label(win,'VERIFY FULL DESTINATION & NETWORK',17,True,fg=WARN,bg=BG).pack(anchor='w',padx=22,pady=(18,10))
        c=panel(win);c.pack(fill='both',expand=True,padx=20,pady=4)
        pairs=[('NETWORK',plan.network),('SOURCE WALLET',plan.source),('FULL RECIPIENT',plan.destination),
               ('AMOUNT',f'{plan.amount:f} {plan.coin}'),('MAX NETWORK FEE',f'{plan.fee:f} {plan.fee_symbol}'),
               ('DETAILS',plan.detail)]
        for label,val in pairs:
            styled_label(c,label,9,True,fg=ACCENT).pack(anchor='w',pady=(8,0))
            styled_label(c,str(val),10,fg=FG,wraplength=720,justify='left').pack(anchor='w')
        self.info(c,'One-way transfer; no refund, no destination correction. Signing uses HOT software keys for EVM. RPCs can be malicious. Verify on an independent device.',WARN)
        challenge=tk.StringVar()
        styled_label(win,'To broadcast, TYPE this line exactly (do not blindly paste):',11,fg=MUTED,bg=BG).pack(anchor='w',padx=22,pady=(9,0))
        styled_label(win,plan.challenge,13,True,fg=ACCENT,bg=BG).pack(anchor='w',padx=22)
        entry=ttk.Entry(win,textvariable=challenge);entry.pack(fill='x',padx=22,pady=9);entry.focus_set()
        btnbar=tk.Frame(win,bg=BG);btnbar.pack(anchor='e',padx=20,pady=(0,20))
        def cancel_review():
            self.active_plan=None
            plan.context.clear()
            win.destroy()
        win.protocol('WM_DELETE_WINDOW',cancel_review)
        def authorize():
            if self.active_plan is not plan or plan.used:
                messagebox.showerror('Expired','Preview is no longer active.',parent=win);return
            if challenge.get()!=plan.challenge:
                messagebox.showerror('Authorization mismatch','Exact authorization text required.',parent=win);return
            signing_pw=''
            if plan.kind=='btc':
                signing_pw=simpledialog.askstring('BITCOIN CORE WALLET PASSPHRASE',
                    'Enter your encrypted Bitcoin Core wallet passphrase (leave blank if Core is already unlocked):',parent=win,show='●')
                if signing_pw is None:return
            if plan.kind=='evm':
                signing_pw=simpledialog.askstring('FINAL SIGNING PASSWORD',
                    'Password for encrypted keystore or VaultForge vault (never saved):',parent=win,show='●')
                if signing_pw is None:return
            if not messagebox.askyesno('FINAL IRREVERSIBLE ACTION',
                'Send this ONE transaction on the selected mainnet now?\n\nThis cannot be undone. Double-check the FULL address and network.',parent=win):
                return
            win.destroy()
            def finish(hashvalue):
                self.active_plan=None
                messagebox.showinfo('SUBMITTED — NOT CONFIRMED',
                    f'Transaction accepted for submission.\n\nTX HASH:\n{hashvalue}\n\nVerify in your original wallet and a trusted explorer. This is NOT a finality guarantee.')
                self.show('Transactions')
                self.lb_after_send(plan,hashvalue)
            self.run_job(lambda:execute_plan(plan,signing_pw),finish,'BROADCAST ATTEMPT IN FLIGHT — DO NOT RETRY IF RPC TIMES OUT')
        action(btnbar,'Cancel (do NOT broadcast)',cancel_review,style='TButton').pack(side='left',padx=9)
        action(btnbar,'AUTHORIZE AND SEND',authorize).pack(side='left')

    def page_transactions(self):
        self.head('Balances & transaction history','Reads your own Bitcoin/Monero wallet history. For EVM, checks native balances or individual transaction receipts.')
        self.live_balance_panel()
        c=self.card();self.history_kind=tk.StringVar(value='Bitcoin Core BTC')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        ttk.Combobox(row,values=['Bitcoin Core BTC','Monero wallet RPC XMR','EVM native balance','EVM transaction status'],
                     textvariable=self.history_kind,state='readonly',width=30).pack(side='left',padx=(0,8))
        action(row,'Refresh / Query',self.refresh_history).pack(side='left')
        self.history_query=tk.StringVar()
        field(c,'EVM public address or transaction hash (needed only for EVM options)',self.history_query)
        self.balance_text=tk.StringVar(value='Select a data source and refresh.')
        styled_label(c,'Results from selected node',13,True,fg=ACCENT).pack(anchor='w',pady=6)
        styled_label(c,size=11,textvariable=self.balance_text,wraplength=800,justify='left').pack(anchor='w',pady=5)
        cols=('direction','amount','confirmations','txhash')
        self.history_tree=ttk.Treeview(self.content,columns=cols,show='headings',height=13)
        for k,w in (('direction',100),('amount',160),('confirmations',110),('txhash',520)):
            self.history_tree.heading(k,text=k.capitalize());self.history_tree.column(k,width=w)
        self.history_tree.pack(fill='both',expand=True,pady=10)
        self.info(self.content,'EVM RPC endpoints do not generally provide account transaction history without an indexer. Only queried transaction status is shown; a submitted hash is not proof of confirmation.')

    def refresh_history(self):
        kind=self.history_kind.get();query=self.history_query.get().strip()
        def worker():
            if kind=='Bitcoin Core BTC':return btc_balance_history(self.btc_url.get(),self.btc_cookie.get(),self.btc_name.get())
            if kind=='Monero wallet RPC XMR':return xmr_balance_history(self.xmr_url.get(),self.xmr_user.get(),self.xmr_password.get())
            from web3 import Web3
            from backend import evm_w3
            w3=evm_w3(self.evm_code.get(),self.evm_url.get())
            if kind=='EVM native balance':
                return evm_receive_balance(self.evm_code.get(),self.evm_url.get(),query),[]
            if not query.startswith('0x') or len(query)!=66:
                raise ValueError('Enter a full 0x-prefixed 32-byte transaction hash')
            try:r=w3.eth.get_transaction_receipt(query)
            except Exception as e:
                from web3.exceptions import TransactionNotFound
                if isinstance(e,TransactionNotFound):return ('Not yet included in a block (or unknown to this RPC)',[])
                raise
            return (f"Block {r['blockNumber']} • status {'SUCCESS' if r['status']==1 else 'REVERTED'} • gas used {r['gasUsed']}",[])
        def done(result):
            bal,rows=result;self.balance_text.set(bal)
            for e in self.history_tree.get_children():self.history_tree.delete(e)
            for r in rows:self.history_tree.insert('','end',values=(r['type'],r['amount'],r['confirmations'],r['txid']))
        self.run_job(worker,done,'Querying local wallet / selected RPC...')

    def page_connections(self):
        self.head('Wallet connections','Local Bitcoin Core and Monero RPC, plus trusted HTTPS EVM RPC. Endpoints and credentials stay in session memory.')
        btc=self.card();styled_label(btc,'BITCOIN CORE — LOCAL MAINNET',13,True,fg=ACCENT).pack(anchor='w')
        field(btc,'Bitcoin RPC URL (loopback only)',self.btc_url)
        field(btc,'Bitcoin Core authentication cookie path',self.btc_cookie)
        field(btc,'Loaded Bitcoin wallet name',self.btc_name)
        action(btc,'List loaded Bitcoin wallets',self.list_btc_wallets,style='TButton').pack(anchor='w',pady=5)
        row=tk.Frame(self.content,bg=BG);row.pack(fill='both',expand=True)
        mon=panel(row);mon.pack(side='left',fill='both',expand=True,padx=(0,8),pady=8)
        styled_label(mon,'MONERO — LOCAL MAINNET WALLET RPC',12,True,fg=ACCENT).pack(anchor='w')
        field(mon,'Wallet RPC URL (loopback only)',self.xmr_url)
        field(mon,'RPC username',self.xmr_user)
        field(mon,'RPC authentication password (session only)',self.xmr_password,secret=True)
        ev=panel(row);ev.pack(side='left',fill='both',expand=True,pady=8)
        styled_label(ev,'EVM — HTTPS MAINNET RPC',12,True,fg=ACCENT).pack(anchor='w')
        styled_label(ev,'Choose chain',fg=MUTED).pack(anchor='w',pady=5)
        ttk.Combobox(ev,textvariable=self.evm_code,values=list(tx.COIN_NETWORKS),state='readonly').pack(fill='x')
        field(ev,'Trusted HTTPS URL (or loopback HTTP)',self.evm_url)
        self.info(ev,'EVM chain ID is checked on EVERY read/send. RPC provider URLs may contain secret API tokens: keep them private.')
        self.info(self.content,'None of these are saved into the application registry. On the next launch, you must enter remote RPC URLs/passwords again. Bitcoin Core signing requires a wallet loaded and unlocked using Bitcoin Core itself.')

    def list_btc_wallets(self):
        def done(names):
            if not names:messagebox.showwarning('Bitcoin Core','No wallets loaded in Bitcoin Core.');return
            win=tk.Toplevel(self.root);win.title('Loaded BTC wallets');win.configure(bg=BG);win.geometry('500x260')
            styled_label(win,'Select loaded Bitcoin Core wallet',14,True,bg=BG).pack(anchor='w',padx=15,pady=15)
            cb=ttk.Combobox(win,values=names,state='readonly');cb.pack(fill='x',padx=15)
            cb.set(names[0])
            def choose_core_wallet():
                self.btc_name.set(cb.get())
                win.destroy()
                self.lb_source.set('Bitcoin Core BTC')
                self.lb_enabled=True
                self.lb_refresh()
            action(win,'Use this Bitcoin Core wallet',choose_core_wallet).pack(padx=15,pady=12)
        self.run_job(lambda:btc_wallets(self.btc_url.get(),self.btc_cookie.get()),done,'Checking Bitcoin Core loaded wallets...')

    def page_security(self):
        badge=tk.Frame(self.content,bg=CARD,padx=16,pady=10,highlightbackground='#693046',highlightthickness=1)
        badge.pack(fill='x',pady=(0,14))
        badge_icon=load_image('hazard_red.png',(54,54))
        if badge_icon is not None:
            self._brand_images['security_hazard']=badge_icon
            tk.Label(badge,image=badge_icon,bg=CARD,bd=0).pack(side='left',padx=(0,11))
        tk.Label(badge,text='SECURITY / KEY MATERIAL',bg=CARD,fg=RED,
                 font=('Consolas',14,'bold')).pack(anchor='w')
        tk.Label(badge,text='Never paste recovery phrases into chat. Vault and banking security are independent.',
                 bg=CARD,fg=MUTED,font=('Consolas',9)).pack(anchor='w',pady=(3,0))
        self.head('Security & recovery','Review your recovery phrases only on a private computer. Verify and change encryption passwords here.')
        c=self.card()
        styled_label(c,'Encrypted wallet recovery',15,True,fg=ACCENT).pack(anchor='w')
        self.sec_vault=tk.StringVar(value=self.vault_paths[0] if self.vault_paths else '')
        ttk.Combobox(c,values=self.vault_paths,textvariable=self.sec_vault,style='TCombobox').pack(fill='x',pady=12)
        row=tk.Frame(c,bg=CARD);row.pack(anchor='w')
        action(row,'REVEAL recovery phrases',self.reveal_phrase,style='TButton').pack(side='left',padx=(0,10))
        action(row,'Verify paper backup words',self.verify_backup,style='TButton').pack(side='left',padx=(0,10))
        action(row,'Rotate + encrypted rollback backup',lambda:self.show('Vault Security'),style='TButton').pack(side='left')
        self.info(c,'Never photograph, screenshot, email, print to cloud storage, or paste recovery phrases into untrusted websites. A software vault on a USB drive is not a secure-element hardware wallet.',WARN)
        card2=self.card(); styled_label(card2,'Session privacy',15,True,fg=ACCENT).pack(anchor='w')
        action(card2,'LOCK public wallet views and clear session credentials',self.lock_session).pack(anchor='w',pady=10)
        self.info(card2,'Private keys are decrypted only during wallet creation/recovery or final EVM signing, but Python cannot guarantee memory wiping. For meaningful holdings, use a trusted external hardware signer.')
        card3=self.card();styled_label(card3,'Validation / readiness',15,True,fg=ACCENT).pack(anchor='w')
        action(card3,'Run 30-coin address-generation self-test',self.self_test,style='TButton').pack(anchor='w',pady=7)
        self.info(card3,'A passing self-test is not an independent wallet recovery test, cryptographic audit or proof a coin can be spent.')

    def secure_path(self):
        p=self.sec_vault.get().strip()
        if not p:raise ValueError('Choose an encrypted vault first')
        return p

    def reveal_phrase(self):
        try:p=self.secure_path()
        except Exception as e:messagebox.showwarning('Vault',str(e));return
        if not messagebox.askyesno('OFFLINE RECOVERY ONLY','Display recovery phrases on your SCREEN? They may be captured by malware, screen sharing or remote desktop. Use a private/offline environment.'):
            return
        challenge=simpledialog.askstring('Reveal confirmation','Type REVEAL to continue',parent=self.root)
        if challenge!='REVEAL':return
        pw=simpledialog.askstring('Vault password','Enter encryption password:',parent=self.root,show='●')
        if not pw:return
        def done(groups):
            win=tk.Toplevel(self.root);win.title('SENSITIVE RECOVERY WORDS — CLOSE WHEN RECORDED');win.configure(bg=BG);win.geometry('810x560');win.transient(self.root);win.grab_set()
            styled_label(win,'SENSITIVE • DO NOT SHARE OR SCREENSHOT',18,True,fg=WARN,bg=BG).pack(pady=16)
            text=tk.Text(win,wrap='word',bg=FIELD,fg=FG,font=('Consolas',13),relief='flat',padx=15,pady=15)
            text.pack(fill='both',expand=True,padx=18,pady=7)
            for i,g in enumerate(groups,1):
                words=g['mnemonic'].split()
                text.insert('end',f"GROUP {i}: {g['scheme']} • {len(words)} words • {g.get('asset','legacy group')}\n")
                for j,word in enumerate(words,1):text.insert('end',f'{j:02d}. {word:<16}' + ('\n' if j%4==0 else '   '))
                if g.get('passphrase'):text.insert('end','\nBIP39 EXTRA PASSPHRASE: '+g['passphrase']+'\n')
                text.insert('end','\n\n')
            text.config(state='disabled')
            def hide():
                text.config(state='normal');text.delete('1.0','end');win.destroy()
            win.protocol('WM_DELETE_WINDOW',hide)
            win.after(90000,lambda:hide() if win.winfo_exists() else None)
            action(win,'Close & clear visible recovery text',hide).pack(pady=12)
        self.run_job(lambda:read_vault(p,pw)['groups'],done,'Decrypting recovery material locally...')

    def verify_backup(self):
        try:p=self.secure_path()
        except Exception as e:messagebox.showwarning('Vault',str(e));return
        pw=simpledialog.askstring('Unlock for backup verification','Vault password:',parent=self.root,show='●')
        if not pw:return
        def done(groups):
            import secrets, hmac
            for i,g in enumerate(groups,1):
                words=g['mnemonic'].split();positions=sorted(secrets.SystemRandom().sample(range(len(words)),3))
                for index in positions:
                    entry=simpledialog.askstring('Verify OFFLINE backup',
                        f"Seed group {i} ({g['scheme']}) • enter word #{index+1} from your PAPER backup:",parent=self.root,show='●')
                    if entry is None:return
                    if not hmac.compare_digest(entry.lower().strip(),words[index]):
                        messagebox.showerror('BACKUP FAILED','A recovery word did not match. DO NOT FUND THIS WALLET.');return
                if g.get('passphrase'):
                    entry=simpledialog.askstring('Verify extra BIP39 passphrase',
                        'Enter separately recorded extra passphrase:',parent=self.root,show='●')
                    if entry is None or not hmac.compare_digest(entry,g['passphrase']):
                        messagebox.showerror('FAILED','Extra passphrase mismatch');return
            messagebox.showinfo('Sample verified','The sampled recovery words matched. Independently restore the ENTIRE phrase in a trusted wallet before funding.')
        self.run_job(lambda:read_vault(p,pw)['groups'],done,'Checking encrypted backup locally...')

    def rotate_password(self):
        self.show('Vault Security')

    def lock_session(self):
        self.public_unlocked.clear();self.active_plan=None
        self._hub_target=None
        self.xmr_password.set('')
        self.status.set('Session credentials cleared • public vault views locked')
        messagebox.showinfo('Locked','Public vault cache and Monero RPC password were cleared from application references. OS/process memory erasure is not guaranteed.')

    def self_test(self):
        def task():vf.self_test();return True
        self.run_job(task,lambda _:messagebox.showinfo('Preflight','All 30 generator address tests and encryption test passed locally. This does not prove spend/recovery compatibility.'),
                     'Testing 30 coin derivations and encryption (known TEST seed only)...')

    def run(self):self.root.mainloop()


if __name__=='__main__':
    if '--wallet-self-test' in sys.argv:
        # PyInstaller windowed mode may set sys.stdout/sys.stderr to None.
        # Write only a secret-free status into the temporary builder-supplied file.
        from wallet_runtime import test_wallet_runtime, wallet_error_summary
        report_path = None
        try:
            offset = sys.argv.index('--wallet-self-test')
            if len(sys.argv) > offset + 1:
                report_path = Path(sys.argv[offset + 1])
            count = test_wallet_runtime()
            status = f'[PASS] Wallet runtime: {count} chains and encrypted restore operations'
            exit_code = 0
        except Exception as exc:
            status = '[FAILED] ' + wallet_error_summary(exc)
            exit_code = 71
        if report_path is not None:
            try:
                report_path.write_text(status, encoding='utf-8')
            except OSError:
                exit_code = 72
        elif sys.stdout is not None:
            print(status)
        raise SystemExit(exit_code)
    if len(sys.argv)>1 and sys.argv[1] in ('--mesh-bridge','--mesh-cli','--mesh-node'):
        if sys.stdout is None:
            try: sys.stdout=os.fdopen(os.dup(1),'w',encoding='utf-8',buffering=1)
            except OSError: sys.stdout=open(os.devnull,'w')
        if sys.stderr is None: sys.stderr=open(os.devnull,'w')
        if sys.argv[1]=='--mesh-bridge':
            from mesh_bridge import main as bridge_main
            raise SystemExit(bridge_main())
        mesh_source=str(Path(__file__).resolve().parent/'vaultmesh')
        if mesh_source not in sys.path:sys.path.insert(0,mesh_source)
        if sys.argv[1]=='--mesh-cli':
            from vaultmesh.mesh_chat import main as mesh_main
            raise SystemExit(mesh_main(sys.argv[2:]))
        from vaultmesh.node_manager import main as manager_main
        raise SystemExit(manager_main(sys.argv[2:]))
    try: CryptoSuite().run()
    except Exception as exc:
        # Avoid dumping secret plaintext into console tracebacks.
        print('Crypto GUI could not start: '+type(exc).__name__+' (details suppressed to protect credentials)',file=sys.stderr)
        sys.exit(1)
