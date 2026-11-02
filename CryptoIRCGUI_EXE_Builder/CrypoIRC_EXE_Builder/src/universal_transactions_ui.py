"""Read-only universal transaction dashboard. Signing stays in chain-specific workflows."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from universal_transactions import UniversalTxJournal, sync_existing, display_units, NEEDS_REVIEW

BG='#07060b';CARD='#15101e';GREEN='#47fca3';MUTED='#a39ab6';WARN='#ff707a'

class UniversalTransactionsUI:
    def page_universal_transactions(self):
        self.head('Phase 8 / Universal Transaction Center v3.4',
            'Consolidated BTC, EVM and Monero transaction records. READ-ONLY: this page cannot sign, '
            'broadcast, repeat, replace or approve payments. All other 30-coin routes remain unverified '
            'until their chain-specific spending engines are implemented and tested.')
        p=tk.Frame(self.content,bg=CARD,padx=16,pady=15);p.pack(fill='x',pady=8)
        tk.Label(p,text='01 / AUTHORIZED TRANSACTION SOURCES',bg=CARD,fg=GREEN,font=('Consolas',11,'bold')).pack(anchor='w')
        self.utx_filter=tk.StringVar(value='ALL')
        self.utx_summary=tk.StringVar(value='Not synchronized. Balances and settlement are not inferred from this journal.')
        toolbar=tk.Frame(p,bg=CARD);toolbar.pack(fill='x',pady=9)
        ttk.Combobox(toolbar,textvariable=self.utx_filter,values=('ALL','BTC','EVM','XMR'),state='readonly',width=12).pack(side='left',padx=(0,12))
        ttk.Button(toolbar,text='SYNC LOCAL TRANSACTION JOURNALS',command=self._utx_refresh,style='Accent.TButton').pack(side='left',padx=5)
        ttk.Button(toolbar,text='VERIFY HISTORY CHECKSUMS',command=self._utx_verify).pack(side='left',padx=5)
        tk.Label(p,textvariable=self.utx_summary,bg=CARD,fg=MUTED,wraplength=1050,justify='left').pack(anchor='w',pady=5)
        tk.Label(p,text='Confirmation counts and transaction states are reported by each chain-specific engine. '
                 'A pending, unknown or unverified record is NEVER proof of delivery. Local checksums are NOT signed audit logs.',
                 bg=CARD,fg=WARN,wraplength=1040,justify='left').pack(anchor='w',pady=5)
        box=tk.Frame(self.content,bg=CARD,padx=14,pady=13);box.pack(fill='both',expand=True,pady=8)
        headings=(('chain',90),('network',115),('asset',105),('amount',150),('fee',135),('status',155),('confirmations',110))
        tree=ttk.Treeview(box,columns=[v[0] for v in headings],show='headings',height=13,selectmode='browse')
        for name,width in headings:
            tree.heading(name,text=('FEE / CAP' if name=='fee' else name.upper()));tree.column(name,width=width,stretch=name in ('amount','status'))
        tree.pack(fill='both',expand=True)
        self.utx_tree=tree;self._utx_rows={}
        self.utx_detail=tk.StringVar(value='Select a record to inspect its public transaction details.')
        tree.bind('<<TreeviewSelect>>',lambda e:self._utx_selected())
        tk.Label(box,textvariable=self.utx_detail,bg=CARD,fg=GREEN,wraplength=1000,justify='left').pack(anchor='w',pady=7)
        r=tk.Frame(box,bg=CARD);r.pack(fill='x',pady=4)
        for caption,page in [('OPEN BTC SEND / REVIEW','BTC Phase 1'),('OPEN EVM SEND / REVIEW','EVM Phase 2'),('OPEN MONERO SEND / REVIEW','Monero Phase 3')]:
            ttk.Button(r,text=caption,command=lambda p=page:self.show(p)).pack(side='left',padx=(0,10))
        self.utx_filter.trace_add('write',lambda *_:self._utx_show_rows())
        self._utx_refresh()

    def _utx_refresh(self):
        if getattr(self,'current_page',None)!='Universal Transactions':return
        self.utx_summary.set('Reading local chain journals in the background; no network request or signing...')
        def work():return sync_existing()
        def done(result):
            if getattr(self,'current_page',None)!='Universal Transactions':return
            self._utx_data=result['rows'];self._utx_show_rows()
            s=result['summary'];problems=result['errors']
            self.utx_summary.set(f"{s['total']} records · {s['confirmed']} backend-confirmed · {s['pending']} pending · "
                f"{s['review']} requiring review · {result['imported']} new updates · "
                + (f'{len(problems)} import warnings: '+problems[0] if problems else 'Local history checks passed.'))
        self.run_job(work,done,'Synchronizing existing local transaction journals...')

    def _utx_show_rows(self):
        tree=getattr(self,'utx_tree',None)
        if tree is None or not tree.winfo_exists():return
        tree.delete(*tree.get_children());self._utx_rows={}
        filter_name=self.utx_filter.get()
        for i,rec in enumerate(getattr(self,'_utx_data',[])):
            if filter_name!='ALL' and rec['chain']!=filter_name:continue
            try:
                amount=display_units(rec['amount_units'],rec['decimals'])
                fee=display_units(rec['max_fee_units'],8 if rec['chain']=='BTC' else (12 if rec['chain']=='XMR' else 18))
            except ValueError:continue
            ident=f'utx_{i}';self._utx_rows[ident]=rec
            tree.insert('', 'end', iid=ident, values=(rec['chain'],rec['network'],rec['asset'],amount,fee,rec['status'],rec['confirmations']))

    def _utx_selected(self):
        selected=self.utx_tree.selection()
        if not selected:return
        item=self._utx_rows.get(selected[0]);
        if not item:return
        status=item['status']
        notice=('REVIEW BEFORE ANOTHER SEND' if status in NEEDS_REVIEW else
                'Reported by local chain journal, not independently settled')
        self.utx_detail.set(f"{item['chain']} / {item['network']} · {item['asset']}\n"
            f"Wallet/source: {item['source']}\nRecipient: {item['destination']}\n"
            f"Transaction hash: {item['tx_hash'] or 'Not available'}\n"
            f"State: {status} · Confirmations: {item['confirmations']} · {notice}\n"
            f"Backend ID: {item['backend_id']}")

    def _utx_verify(self):
        def work():return UniversalTxJournal().verify_events()
        def done(result):
            if getattr(self,'current_page',None)=='Universal Transactions':
                messagebox.showinfo('Local history verification',
                    f"{result['records']} transaction records and {result['events']} event checksums match.\n\n"
                    +result['warning'],parent=self.root)
        self.run_job(work,done,'Verifying local transaction projection checksums...')
