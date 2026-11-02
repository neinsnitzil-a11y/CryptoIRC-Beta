"""Read-only operator readiness UI. Never opens the isolated financial ledger."""
from __future__ import annotations
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from security_gates import release_status

BG='#07060b'; CARD='#15101e'; TEXT='#f2edf9'; MUTED='#a39ab6'; GREEN='#47fca3'; PURPLE='#a977f5'; RED='#ff707a'

class OperationsUI:
    def page_operations_center(self):
        self.head('Operations Center', 'Resilience • reconciliation • recovery • release controls')
        banner=tk.Frame(self.content,bg='#240e20',highlightbackground=RED,highlightthickness=1,padx=15,pady=14)
        banner.pack(fill='x',pady=(0,16))
        tk.Label(banner,text='●  SANDBOX / INTERNAL CONTROLS  •  REAL MONEY DISABLED',
                 bg='#240e20',fg=RED,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(banner,text='No live service health, provider settlements, bank funds, or audit approvals are asserted by this screen.',
                 bg='#240e20',fg=TEXT,font=('Segoe UI',10),wraplength=850,justify='left').pack(anchor='w',pady=(7,0))
        cards=tk.Frame(self.content,bg=BG)
        cards.pack(fill='x',pady=4)
        for title,detail,accent in [
            ('DURABLE EVENTS','Atomic outbox + worker leases + dead letters',GREEN),
            ('RECONCILIATION','Statement deduplication + independent reviewers',PURPLE),
            ('DISASTER RECOVERY','Verified SQLite sandbox backup/restore',GREEN),
        ]:
            c=tk.Frame(cards,bg=CARD,padx=13,pady=14,highlightbackground='#3b2654',highlightthickness=1)
            c.pack(side='left',fill='both',expand=True,padx=(0,9))
            tk.Label(c,text=title,bg=CARD,fg=accent,font=('Consolas',10,'bold')).pack(anchor='w')
            tk.Label(c,text=detail,bg=CARD,fg=MUTED,font=('Segoe UI',9),wraplength=195,justify='left').pack(anchor='w',pady=(8,0))
            tk.Label(c,text='BACKEND REFERENCE — NOT DEPLOYED',bg=CARD,fg=RED,font=('Consolas',8)).pack(anchor='w',pady=(9,0))
        tk.Label(self.content,text='CONTROLS / RELEASE STATUS',bg=BG,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w',pady=(16,8))
        for heading,detail in [
            ('Provider integrations','Merchant credentials must stay on a separate approved server.'),
            ('Settlement and account balances','Only verified provider events may change real-money bookkeeping; no live service exists yet.'),
            ('Signing and release integrity','Authenticode workflow is provided; certificate and external verification remain required.'),
            ('Authentication and trust','MFA reference exists; production IAM, device attestation, and independent audit remain outstanding.'),
            ('Operating procedures','The Financial Controls page shows release blockers. See the root README for safety limits.'),
        ]:
            row=tk.Frame(self.content,bg=CARD,padx=12,pady=10,highlightbackground='#3b2654',highlightthickness=1)
            row.pack(fill='x',pady=3)
            tk.Label(row,text='◇  '+heading,bg=CARD,fg=TEXT,font=('Consolas',10,'bold')).pack(anchor='w')
            tk.Label(row,text=detail,bg=CARD,fg=MUTED,font=('Segoe UI',9),wraplength=830,justify='left').pack(anchor='w',pady=(5,0))
        actions=tk.Frame(self.content,bg=BG);actions.pack(fill='x',pady=17)
        def export():
            filename=filedialog.asksaveasfilename(parent=self.root,title='Export launch gate report',
                defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='NOCTURNE_release_gates.json')
            if not filename: return
            try:
                report={'application':'CRYPTO NOCTURNE v4.5.1','type':'INTERNAL READINESS ONLY',
                        'financial_operational_status':'NOT LIVE',**release_status()}
                with open(filename,'x',encoding='utf-8') as stream:
                    json.dump(report,stream,indent=2)
                messagebox.showinfo('Report created','Readiness status exported. This is not an audit certificate.',parent=self.root)
            except (OSError,ValueError):
                messagebox.showerror('Export blocked','Unable to create report. Existing files are never overwritten.',parent=self.root)
        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append('python -m financial_backend.operations_cli demo\n'
                'python build_release.py test\npython build_release.py check')
            self.status.set('SANDBOX COMMANDS COPIED  •  no payment operations executed')
        tk.Button(actions,text='EXPORT RELEASE GATES',bg='#302047',fg=TEXT,
                  activebackground=PURPLE,relief='flat',padx=15,pady=9,command=export).pack(side='left',padx=(0,9))
        tk.Button(actions,text='COPY SANDBOX DIAGNOSTICS',bg='#143629',fg=GREEN,
                  activebackground='#225a43',relief='flat',padx=15,pady=9,command=copy).pack(side='left')
        tk.Label(self.content,text='The isolated financial_backend/ source is intentionally excluded from the Windows installer.',
                 bg=BG,fg=MUTED,font=('Consolas',9)).pack(anchor='w')
