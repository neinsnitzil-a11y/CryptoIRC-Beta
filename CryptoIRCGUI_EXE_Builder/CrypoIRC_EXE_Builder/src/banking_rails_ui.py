"""NOCTURNE Phase 11 sandbox payment rails desktop UI.
Never display test provider status as real money or a verified bank balance.
"""
from __future__ import annotations
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from banking_rails import RailRequests,SandboxRailsClient,RailError,printable_amount

CARD='#15101e';GREEN='#47fca3';PURPLE='#b363ff';MUTED='#a39ab6';WARN='#ff707a'


def _store_path():
    folder=Path(os.environ.get('LOCALAPPDATA',os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local'/'share'))))/'CRYPTO_NOCTURNE'
    return folder/'banking_rail_requests.sqlite3'

class BankingRailsUI:
    def page_banking_rails(self):
        self.head('Phase 11 / Banking & Payment Rails',
            'Server-backed sandbox intent tracking and authenticated reconciliation. '
            'NOT an actual bank, linked bank balance, ACH payout, or live payment processor.')
        block=tk.Frame(self.content,bg=CARD,padx=16,pady=15)
        block.pack(fill='x',pady=7)
        tk.Label(block,text='01 / PAYMENT-RAIL REQUEST',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(block,text='No card numbers, routing numbers, IBANs, SSNs or passwords. Use only a public label, e.g. “My checking”.',
                 bg=CARD,fg=WARN,justify='left',wraplength=900).pack(anchor='w',pady=5)
        self.rail_flow=tk.StringVar(value='DEPOSIT')
        self.rail_currency=tk.StringVar(value='USD')
        self.rail_amount=tk.StringVar(value='25.00')
        self.rail_label=tk.StringVar(value='Personal account')
        for label,var,choices in (('Request type',self.rail_flow,('DEPOSIT','WITHDRAWAL')),
            ('Fiat currency',self.rail_currency,('USD','EUR','GBP','CAD','AUD','JPY')),
            ('Amount',self.rail_amount,None),('Public account label (no numbers)',self.rail_label,None)):
            tk.Label(block,text=label.upper(),bg=CARD,fg=MUTED).pack(anchor='w',pady=(6,1))
            inp=ttk.Combobox(block,textvariable=var,values=choices,state='readonly') if choices else ttk.Entry(block,textvariable=var)
            inp.pack(fill='x')
        buttons=tk.Frame(block,bg=CARD);buttons.pack(fill='x',pady=10)
        ttk.Button(buttons,text='CREATE LOCAL REQUEST',style='Accent.TButton',command=self._rail_create).pack(side='left',padx=(0,9))
        ttk.Button(buttons,text='VIEW REQUEST JOURNAL',command=self._rail_refresh).pack(side='left')

        connect=tk.Frame(self.content,bg=CARD,padx=16,pady=15);connect.pack(fill='x',pady=7)
        tk.Label(connect,text='02 / TEST GATEWAY · NOT REAL FUNDS',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.rails_url=tk.StringVar(value='http://127.0.0.1:18450')
        self.rails_token=tk.StringVar(value='')
        tk.Label(connect,text='Loopback-only sandbox service endpoint',bg=CARD,fg=MUTED).pack(anchor='w',pady=(7,1))
        ttk.Entry(connect,textvariable=self.rails_url).pack(fill='x')
        tk.Label(connect,text='Sandbox access token (session only — not saved)',bg=CARD,fg=MUTED).pack(anchor='w',pady=(7,1))
        ttk.Entry(connect,textvariable=self.rails_token,show='●').pack(fill='x')
        tools=tk.Frame(connect,bg=CARD);tools.pack(fill='x',pady=(10,0))
        ttk.Button(tools,text='SUBMIT SELECTED TO TEST GATEWAY',command=self._rail_submit).pack(side='left',padx=(0,9))
        ttk.Button(tools,text='QUERY GATEWAY STATUS',command=self._rail_status).pack(side='left')
        tk.Label(connect,text='Signed test webhooks can update gateway evidence only. A TEST_SETTLED state is not a bank deposit, '
            'withdrawal, wallet credit, or completed fiat-to-crypto purchase.',
            bg=CARD,fg=WARN,wraplength=900,justify='left').pack(anchor='w',pady=(9,1))

        report=tk.Frame(self.content,bg=CARD,padx=16,pady=14);report.pack(fill='x',pady=7)
        tk.Label(report,text='03 / LOCAL REQUESTS · ALWAYS UNVERIFIED',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.rail_tree=ttk.Treeview(report,columns=('id','type','amount','label','local'),show='headings',height=8,selectmode='browse')
        for col,width in (('id',150),('type',120),('amount',145),('label',240),('local',180)):
            self.rail_tree.heading(col,text=col.upper());self.rail_tree.column(col,width=width,stretch=col=='label')
        self.rail_tree.pack(fill='x',pady=9)
        self.rail_detail=tk.StringVar(value='Select a request. A desktop request is never proof of money movement.')
        tk.Label(report,textvariable=self.rail_detail,bg=CARD,fg=PURPLE,justify='left',wraplength=950).pack(anchor='w')
        self._rail_refresh()

    def _rail_db(self):return RailRequests(_store_path())
    def _rail_refresh(self):
        if getattr(self,'current_page',None)!='Banking Rails':return
        self.rail_tree.delete(*self.rail_tree.get_children())
        try:
            for r in self._rail_db().list(80):
                self.rail_tree.insert('','end',iid=r['id'],values=(r['id'][:13],r['flow'],
                    f"{printable_amount(r['minor'],r['currency'])} {r['currency']}",r['label'],r['status']))
        except (OSError,ValueError,KeyError):
            self.rail_detail.set('Local request journal unavailable. No funds have been moved.')
    def _rail_create(self):
        try:
            db=self._rail_db();rec=db.create(flow=self.rail_flow.get(),currency=self.rail_currency.get(),
                amount=self.rail_amount.get(),label=self.rail_label.get())
            self._rail_refresh()
            if rec['id'] in self.rail_tree.get_children():self.rail_tree.selection_set(rec['id'])
            self.rail_detail.set(f"LOCAL DRAFT  ·  {rec['id']}\nNo payment initiated, no provider contacted, no balance credited.")
        except (RailError,OSError,ValueError) as exc:
            messagebox.showerror('Invalid request',str(exc) if isinstance(exc,RailError) else 'Could not save request.',parent=self.root)
    def _rail_selected(self):
        sel=self.rail_tree.selection()
        if not sel:
            messagebox.showwarning('Select request','Select an existing local payment request.',parent=self.root);return None
        return self._rail_db().get(sel[0])
    def _rail_submit(self):
        rec=self._rail_selected()
        if rec is None:return
        try:
            endpoint=self.rails_url.get();token=self.rails_token.get()
            client=SandboxRailsClient(endpoint,token)
        except RailError as exc:
            messagebox.showerror('Sandbox connection',str(exc),parent=self.root);return
        if not messagebox.askyesno('TEST ONLY',
           'Submit this intent to your local SANDBOX gateway?\n\nNo real banking, ACH, card processing, or cash payout occurs.',parent=self.root):return
        def work():return client.create(rec)
        def done(result):
            try:self._rail_db().state(rec['id'],'SUBMITTED_TO_SANDBOX')
            except (OSError,RailError):pass
            if self.current_page!='Banking Rails':return
            self._rail_refresh()
            self.rail_detail.set(f"GATEWAY: {result['state']}  ·  {result['id']}\nTEST ONLY — real funds transferred: NO")
        self.run_job(work,done,'CONTACTING SANDBOX GATEWAY…')
    def _rail_status(self):
        rec=self._rail_selected()
        if rec is None:return
        try:client=SandboxRailsClient(self.rails_url.get(),self.rails_token.get())
        except RailError as exc:
            messagebox.showerror('Sandbox connection',str(exc),parent=self.root);return
        def done(result):
            if self.current_page!='Banking Rails':return
            if (result.get('id')!=rec['id'] or result.get('currency')!=rec['currency']
                or result.get('minor')!=rec['minor'] or result.get('flow')!=rec['flow']):
                self.rail_detail.set('PROVIDER RESPONSE DOES NOT MATCH LOCAL REQUEST — MANUAL REVIEW');return
            self.rail_detail.set(f"SERVER REPORTED: {result['state']}  ·  {rec['id']}\n"
                'SANDBOX EVIDENCE ONLY — never spendable fiat, a completed withdrawal, or wallet credit.')
        self.run_job(lambda:client.status(rec['id']),done,'CHECKING TEST PROVIDER EVIDENCE…')
