"""Phase 10 read-only portfolio UI. All Tk operations are main-thread only."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from portfolio_engine import distinct_accounts, wallet_identity, summarize, query_account, Observation, public_activity
from unified_wallet import UnifiedAccountRegistry, from_vault_rows, from_watch_rows
from universal_transactions import UniversalTxJournal, display_units
from performance_runtime import QueueSaturated

CARD='#15101e'; FIELD='#0c0914'; GREEN='#47fca3'; MUTED='#a39ab6'; WARN='#ff707a'; PURPLE='#b363ff'

class PortfolioUI:
    def page_portfolio(self):
        self.head('Portfolio / Phase 10',
            'Read-only multi-account holdings and local transaction activity. '
            'Balances use connected wallet/node RPC. No exchange price or USD amount is guessed. '
            'Never treat watch-only or node-reported balances as signing or recovery proof.')
        self._p37_generation=getattr(self,'_p37_generation',0)+1
        self._p37_busy=False
        generation=self._p37_generation
        self._p37_observations={}
        self._p37_accounts=[]
        self._p37_rows={}
        self.p37_autorefresh=tk.BooleanVar(value=False)
        self.p37_overview=tk.StringVar(value='Loading public wallet references…')
        self.p37_detail=tk.StringVar(value='Select an account to review its public address and local activity.')

        header=tk.Frame(self.content,bg=CARD,padx=15,pady=14);header.pack(fill='x',pady=(0,8))
        tk.Label(header,text='01 / WALLET PORTFOLIO',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(header,textvariable=self.p37_overview,bg=CARD,fg=PURPLE,font=('Consolas',10),justify='left',wraplength=950).pack(anchor='w',pady=8)
        row=tk.Frame(header,bg=CARD);row.pack(fill='x',pady=(4,0))
        ttk.Button(row,text='REFRESH CONNECTED BALANCES',style='Accent.TButton',command=self._p37_refresh).pack(side='left',padx=(0,9))
        ttk.Button(row,text='RELOAD ACCOUNTS',command=self._p37_load).pack(side='left',padx=(0,9))
        ttk.Checkbutton(row,text='AUTO EVERY 30s',variable=self.p37_autorefresh).pack(side='left')
        tk.Label(header,text='Requires Connections for each matching account; only BTC Core, Monero RPC and matching EVM native coins can be queried here. '
            'Token Center and Chain Expansion remain separate read-only readers. No node connection means UNAVAILABLE—not zero.',
            bg=CARD,fg=WARN,justify='left',wraplength=950).pack(anchor='w',pady=(10,0))

        funds=tk.Frame(self.content,bg=CARD,padx=15,pady=13);funds.pack(fill='x',pady=7)
        tk.Label(funds,text='02 / HOLDINGS BY ASSET AND NETWORK',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.p37_group_tree=ttk.Treeview(funds,columns=('asset','network','total','reported','status'),show='headings',height=5)
        for col,width in (('asset',95),('network',145),('total',175),('reported',175),('status',190)):
            self.p37_group_tree.heading(col,text=col.upper())
            self.p37_group_tree.column(col,width=width,stretch=col=='status')
        self.p37_group_tree.pack(fill='x',pady=8)
        tk.Label(funds,text='Totals appear only when ALL accounts for that asset/network have fresh observations. '
            '“Reported available” is a node-reported amount, NOT proven spendable. Cross-network funds are NEVER added together.',
            bg=CARD,fg=MUTED,wraplength=900,justify='left').pack(anchor='w')

        accounts=tk.Frame(self.content,bg=CARD,padx=15,pady=13);accounts.pack(fill='x',pady=7)
        tk.Label(accounts,text='03 / ACCOUNTS AND OBSERVATION STATUS',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.p37_tree=ttk.Treeview(accounts,columns=('wallet','asset','network','balance','status'),show='headings',height=9,selectmode='browse')
        for col,width in (('wallet',205),('asset',75),('network',120),('balance',185),('status',150)):
            self.p37_tree.heading(col,text=col.upper());self.p37_tree.column(col,width=width,stretch=col=='wallet')
        self.p37_tree.pack(fill='x',pady=8)
        self.p37_tree.bind('<<TreeviewSelect>>',lambda _:self._p37_selected())
        tk.Label(accounts,textvariable=self.p37_detail,bg=CARD,fg=MUTED,wraplength=950,justify='left').pack(anchor='w',pady=7)
        tools=tk.Frame(accounts,bg=CARD);tools.pack(fill='x')
        ttk.Button(tools,text='OPEN UNIFIED WALLETS',command=lambda:self.show('Unified Wallets')).pack(side='left',padx=(0,8))
        ttk.Button(tools,text='OPEN TRANSACTIONS',command=lambda:self.show('Universal Transactions')).pack(side='left',padx=(0,8))
        ttk.Button(tools,text='OPEN TOKEN CENTER',command=lambda:self.show('Token Center')).pack(side='left')
        self._p37_load()
        self.root.after(30_000,lambda:self._p37_tick(generation))

    def _p37_load(self):
        if self._p37_busy:return
        try:
            accounts=list(UnifiedAccountRegistry().list())
            for path,rows in self.public_unlocked.items():accounts.extend(from_vault_rows(path,rows))
            accounts.extend(from_watch_rows(self.watch))
            self._p37_accounts=distinct_accounts(accounts)
        except (ValueError,KeyError,OSError,TypeError):
            self._p37_accounts=[]
            self.p37_overview.set('Account registry unavailable or invalid. Check Unified Wallets.')
        current={wallet_identity(a) for a in self._p37_accounts}
        self._p37_observations={k:v for k,v in self._p37_observations.items() if k in current}
        self._p37_draw()

    def _p37_config(self):
        # Capture Tk values on main thread. They are not persisted to disk.
        return dict(btc_url=self.btc_url.get().strip(),btc_cookie=self.btc_cookie.get().strip(),
            xmr_url=self.xmr_url.get().strip(),xmr_user=self.xmr_user.get().strip(),
            xmr_password=self.xmr_password.get(),evm_code=self.evm_code.get(),evm_url=self.evm_url.get().strip())

    def _p37_refresh(self):
        if self._p37_busy or getattr(self,'pending',False):return
        self._p37_load()
        generation=self._p37_generation
        accounts=self._p37_accounts[:20]  # bounded work; remaining accounts stay unavailable
        config=self._p37_config()
        self._p37_busy=True
        # Old observations cannot be presented as live during a new RPC refresh.
        self._p37_observations={}
        self._p37_draw()
        self.p37_overview.set('Checking matching accounts using read-only blockchain RPC. The interface stays responsive…')
        def work():
            results={}
            for acc in accounts:
                key=wallet_identity(acc)
                try:
                    response=query_account(acc,config)
                    results[key]=Observation.from_snapshot(acc,response)
                except Exception:
                    # Never copy RPC exception text or secrets into the UI/logs.
                    results[key]=None
            return results
        def done(results):
            if getattr(self,'current_page',None)!='Portfolio' or generation!=self._p37_generation:return
            self._p37_busy=False
            # A late response from a DIFFERENT RPC, cookie, network, or account
            # configuration must not replace current observations.
            if config!=self._p37_config():
                self._p37_observations={}
                self.p37_overview.set('Configuration changed during refresh; old results discarded. Refresh again.')
            else:
                self._p37_observations={k:v for k,v in results.items() if v is not None}
            self._p37_draw()
        def fail(_kind):
            if getattr(self,'current_page',None)=='Portfolio' and generation==self._p37_generation:
                self._p37_busy=False;self._p37_observations={};self._p37_draw()
        try:self.executor.submit(work,done,fail,lane='financial',key='portfolio-refresh')
        except (QueueSaturated,RuntimeError):
            self._p37_busy=False
            self.p37_overview.set('Balance refresh unavailable — background queue is full; retry later.')

    def _p37_draw(self):
        if getattr(self,'current_page',None)!='Portfolio':return
        report=summarize(self._p37_accounts,self._p37_observations)
        self.p37_overview.set(f"{len(report['rows'])} distinct public accounts · {report['live']} live · "
            f"{report['stale']} stale · {report['unavailable']} unavailable. "
            'No fiat portfolio valuation; no signing or spending performed.')
        tree=self.p37_group_tree
        tree.delete(*tree.get_children())
        for i,g in enumerate(report['groups']):
            ready=g['reported_total'] is not None
            tree.insert('', 'end', iid='grp'+str(i),values=(g['asset'],g['network'],
                str(g['reported_total']) if ready else 'UNAVAILABLE',
                str(g['reported_available']) if ready else 'UNAVAILABLE',
                'LIVE / COMPLETE' if ready else f"INCOMPLETE · {g['incomplete']} missing"))
        self.p37_tree.delete(*self.p37_tree.get_children());self._p37_rows={}
        for i,row in enumerate(report['rows']):
            acc=row['account'];key='acct'+str(i);self._p37_rows[key]=row
            self.p37_tree.insert('', 'end',iid=key,values=(acc.label[:44],row['asset'],row['network'],
                str(row['total']) if row['total'] is not None else '—',row['state']))

    def _p37_selected(self):
        selection=self.p37_tree.selection()
        if not selection:return
        entry=self._p37_rows.get(selection[0])
        if not entry:return
        acc=entry['account']
        activity=[]
        error=''
        try:
            history=UniversalTxJournal().list(limit=250)
            activity=public_activity(history,acc)
        except Exception:
            error='Local transaction projection unavailable.'
        recent=[]
        for tx in activity[:5]:
            try:quantity=display_units(tx['amount_units'],int(tx['decimals']))
            except (ValueError,TypeError,KeyError):quantity='unknown'
            recent.append(f"  {tx.get('status','UNKNOWN')} · {quantity} {tx.get('asset','')} · {tx.get('confirmations',0)} conf.")
        detail=f"{acc.asset} / {acc.network} · {acc.kind}\nPublic address: {acc.address}\n"
        detail+=f"Observation: {entry['state']} · "
        if entry['state']=='LIVE':
            detail+=f"total {entry['total']} · reported available {entry['reported_available']} · height {entry['height']}\n"
        else:detail+='No current trustworthy amount.\n'
        detail+='Recent LOCAL journal entries (not proof of current chain finality): '+str(len(activity))+'\n'
        detail+='\n'.join(recent) if recent else (error or '  No matching outgoing transactions in the local journal.')
        self.p37_detail.set(detail)

    def _p37_tick(self,generation):
        if self.current_page!='Portfolio' or generation!=getattr(self,'_p37_generation',None):return
        # Mark expired RPC observations stale on the same interval even offline.
        self._p37_draw()
        if self.p37_autorefresh.get() and not self._p37_busy and not getattr(self,'pending',False):
            self._p37_refresh()
        self.root.after(30_000,lambda:self._p37_tick(generation))
