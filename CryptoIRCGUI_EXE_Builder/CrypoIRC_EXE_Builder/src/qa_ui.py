"""Phase 17 QA Center: local evidence versus independently verified release gates."""
from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from qa_runtime import assess,export_report,QAError,VERSION

BG='#07060b';CARD='#15101e';FIELD='#0c0914';GREEN='#47fca3';PURPLE='#b363ff';MUTED='#a39ab6';WARN='#ff707a'

class QAUI:
    def page_qa_center(self):
        self.head('Transaction QA / Phase 17',
                  'Local regression and transaction fault evidence, with independent certification gates kept BLOCKED. '
                  'Never treat simulated transaction tests as real-money proof.')
        self._qa_report=assess(source=Path(__file__).resolve().parent)
        self._qa_status=tk.StringVar(value='PRODUCTION: BLOCKED  •  No live-mainnet or fiat authorization verified')
        self._qa_tests=tk.StringVar(value='Local tests: NOT RUN  •  Optional BTC regtest: NOT RUN')
        self._qa_detail=tk.StringVar(value='Local QA results only. Independent security and production approvals remain blocked.')

        panel=tk.Frame(self.content,bg=CARD,padx=17,pady=15)
        panel.pack(fill='x',pady=(0,12))
        tk.Label(panel,text='01 / FINANCIAL RELEASE GATES',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(panel,textvariable=self._qa_status,fg=WARN,bg=CARD,
                 font=('Consolas',11,'bold'),wraplength=1010,justify='left').pack(anchor='w',pady=(10,7))
        tk.Label(panel,textvariable=self._qa_tests,fg=PURPLE,bg=CARD,wraplength=960,justify='left').pack(anchor='w')
        tk.Label(panel,text='An empty or passing local checklist is not an independent audit. Real BTC/EVM/XMR node '
                 'transfers, recovery drills, approved provider settlement and a signed build still need external evidence.',
                 fg=MUTED,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=(9,0))

        panel=tk.Frame(self.content,bg=CARD,padx=17,pady=15)
        panel.pack(fill='x',pady=(0,12))
        tk.Label(panel,text='02 / RUN LOCAL CHECKS',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        row=tk.Frame(panel,bg=CARD);row.pack(anchor='w',fill='x',pady=(9,5))
        ttk.Button(row,text='CHECK RELEASE GATES',command=lambda:self._qa_run(tests=False)).pack(side='left',padx=(0,9))
        ttk.Button(row,text='RUN ALL SOURCE TESTS',command=lambda:self._qa_run(tests=True)).pack(side='left',padx=(0,9))
        ttk.Button(row,text='EXPORT UNSIGNED QA REPORT',command=self._qa_export).pack(side='left')
        self._qa_regtest_var=tk.BooleanVar(value=False)
        tk.Checkbutton(panel,text='Also run temporary Bitcoin Core regtest (requires verified bitcoind; NEVER mainnet)',
                       variable=self._qa_regtest_var,bg=CARD,fg=MUTED,selectcolor=FIELD,
                       activebackground=CARD,activeforeground=GREEN).pack(anchor='w',pady=6)
        tk.Label(panel,textvariable=self._qa_detail,bg=CARD,fg=MUTED,wraplength=990,justify='left').pack(anchor='w',pady=4)
        tk.Label(panel,text='Source tests cannot run from the frozen Windows EXE because application tests are deliberately '
                 'excluded from the installer. Run this check in the unpacked source/build environment.',
                 fg=MUTED,bg=CARD,wraplength=990,justify='left').pack(anchor='w',pady=4)

        panel=tk.Frame(self.content,bg=CARD,padx=17,pady=14)
        panel.pack(fill='both',expand=True,pady=6)
        tk.Label(panel,text='03 / RELEASE GATE MATRIX',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w',pady=(0,8))
        columns=('gate','result','authority')
        table=ttk.Treeview(panel,columns=columns,show='headings',height=16)
        table.heading('gate',text='Requirement')
        table.heading('result',text='Status')
        table.heading('authority',text='Proof type')
        table.column('gate',width=535,stretch=True)
        table.column('result',width=150,stretch=False)
        table.column('authority',width=125,stretch=False)
        table.pack(fill='both',expand=True)
        self._qa_table=table
        table.bind('<<TreeviewSelect>>',self._qa_selected)
        self._qa_describe=tk.StringVar(value='Select a gate to view its acceptance requirement.')
        tk.Label(panel,textvariable=self._qa_describe,bg=CARD,fg=MUTED,justify='left',
                 wraplength=990).pack(anchor='w',pady=(9,3))
        self._qa_refresh()

    def _qa_refresh(self):
        report=self._qa_report
        if not hasattr(self,'_qa_table') or not self._qa_table.winfo_exists():return
        for item in self._qa_table.get_children():self._qa_table.delete(item)
        for gate in report['gates']:
            self._qa_table.insert('', 'end',iid=gate['id'],values=(gate['name'],gate['status'],gate['kind'].upper()))
        s=report['summary'];stats=report['tests']
        self._qa_status.set('PRODUCTION: BLOCKED  •  '+str(s['BLOCKED_EXTERNAL'])+
                 ' independent requirements remain blocked • 0 verified mainnet routes')
        self._qa_tests.set(f"Local: {stats['regression']['total']} tests ({stats['regression']['skipped']} skipped)  •  "
              f"Passed local gates: {s['PASS_LOCAL']}  •  Failed local gates: {s['FAIL_LOCAL']}")
        self._qa_detail.set('A PASS_LOCAL only verifies a local source run; it does NOT approve real-money handling. '
             'An exported report is SHA-256 checksummed, but is NOT signed or independently authenticated.')

    def _qa_selected(self,event=None):
        selected=self._qa_table.selection()
        if not selected:return
        gate=next((g for g in self._qa_report['gates'] if g['id']==selected[0]),None)
        if gate:
            self._qa_describe.set(gate['id']+': '+gate['requirement']+'  •  '+gate['note'])

    def _qa_run(self,*,tests):
        if self._qa_regtest_var.get() and not messagebox.askyesno('Optional isolated regtest',
                'Run a local, disposable Bitcoin Core REGTEST node using the installed bitcoind? '
                'This never uses mainnet coins, but starts a temporary node process.',parent=self.root):
            return
        source=Path(__file__).resolve().parent
        use_regtest=bool(self._qa_regtest_var.get())  # capture Tk state on the UI thread
        self.run_job(lambda:assess(source=source,run_tests=tests,run_btc_regtest=use_regtest),
                     self._qa_completed,'RUNNING SOURCE QA; NO FINANCIAL TRANSACTIONS...')

    def _qa_completed(self,report):
        self._qa_report=report
        self._qa_refresh()
        if report['summary']['FAIL_LOCAL']:
            messagebox.showwarning('Local QA failures',
                 'One or more local QA checks failed. The release remains blocked.',parent=self.root)

    def _qa_export(self):
        if not hasattr(self,'_qa_report'):
            return
        chosen=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',
            filetypes=[('QA Report JSON','*.json')],initialfile='nocturne-v4.5-qa-UNVERIFIED.json')
        if not chosen:return
        try:export_report(self._qa_report,chosen)
        except (QAError,OSError):
            messagebox.showwarning('QA export refused','Choose a new local file path. Existing reports are never overwritten.',parent=self.root)
        else:
            messagebox.showinfo('Unsigned QA report saved',
                 'Saved local test evidence. This SHA-256 report is not a security certification or authorization to move real funds.',parent=self.root)
