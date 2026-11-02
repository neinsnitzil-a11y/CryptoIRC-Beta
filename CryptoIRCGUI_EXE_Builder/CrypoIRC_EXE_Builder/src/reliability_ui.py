"""Phase 14 read-only enterprise reliability diagnostics UI."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from reliability_runtime import ReliabilityQueue, ReliabilityError
from performance_runtime import QueueSaturated

CARD='#15101e'; BG='#07060b'; GREEN='#47fca3'; PURPLE='#a977f5'; MUTED='#a39ab6'; FG='#f2edf9'; RED='#ff707a'

class ReliabilityUI:
    def page_reliability_center(self):
        self.head('Reliability Center', 'Persistent read-only maintenance · crash recovery · integrity and backup checks')
        top=tk.Frame(self.content,bg=CARD,padx=18,pady=15,highlightbackground='#3b2654',highlightthickness=1)
        top.pack(fill='x',pady=8)
        tk.Label(top,text='// DURABLE OPERATIONS QUEUE',bg=CARD,fg=GREEN,font=('Consolas',14,'bold')).pack(anchor='w')
        tk.Label(top,text='Financial transfers are NEVER retried here. No wallet keys, signed transactions, passwords, or payment payloads are stored.\n'
            'Only database integrity and sanitized transaction-attention checks can be queued.',
            bg=CARD,fg=MUTED,justify='left',wraplength=840).pack(anchor='w',pady=9)
        self.rel_summary=tk.StringVar(value='Loading operational health...')
        tk.Label(top,textvariable=self.rel_summary,fg=FG,bg=CARD,font=('Consolas',10),justify='left').pack(anchor='w',pady=8)
        actions=tk.Frame(top,bg=CARD); actions.pack(fill='x',pady=5)
        for name,command in (('QUEUE INTEGRITY CHECK',lambda:self._rel_enqueue('database_integrity')),
                             ('QUEUE TX REVIEW',lambda:self._rel_enqueue('transaction_review')),
                             ('RUN NEXT SAFE JOB',self._rel_run_one),
                             ('REFRESH',self._rel_refresh)):
            ttk.Button(actions,text=name,command=command).pack(side='left',padx=(0,8),pady=4)
        lower=tk.Frame(self.content,bg=CARD,padx=18,pady=14,highlightbackground='#3b2654',highlightthickness=1)
        lower.pack(fill='x',pady=8)
        tk.Label(lower,text='// OPERATIONAL JOURNAL BACKUP',bg=CARD,fg=PURPLE,font=('Consolas',13,'bold')).pack(anchor='w')
        tk.Label(lower,text='Create an exclusive, verified SQLite snapshot of MAINTENANCE METADATA ONLY.\n'
                 'This is not a wallet or transaction-signing backup, and it is not encrypted.',bg=CARD,fg=MUTED,
                 justify='left').pack(anchor='w',pady=10)
        ttk.Button(lower,text='BACK UP OPERATIONS JOURNAL',command=self._rel_backup).pack(anchor='w')
        self._rel_refresh()

    def _rel_refresh(self):
        try:
            state=self.reliability.stats()
            tally=state['counts']; total=sum(tally.values())
            lines=[f'Queued: {tally["queued"]}   Leased: {tally["leased"]}   Done: {tally["done"]}   Dead: {tally["dead"]}   Total: {total}']
            for item in state['recent'][:5]:
                lines.append(f'{item["kind"]}: {item["state"]}  /  {item["result"] or "awaiting result"}  (attempt {item["attempts"]})')
            self.rel_summary.set('\\n'.join(lines))
        except Exception:
            self.rel_summary.set('Operational store unavailable; check local state-directory permissions.')

    def _rel_enqueue(self,kind):
        try:
            _uid,created=self.reliability.enqueue(kind)
            self.status.set('Read-only maintenance '+('queued' if created else 'already pending'))
            self._rel_refresh()
        except Exception:
            messagebox.showerror('Maintenance unavailable','Cannot queue read-only diagnostics. Nothing was sent or signed.',parent=self.root)

    def _rel_run_one(self):
        def done(result):
            self._rel_refresh()
            if result.get('status') in ('integrity_failed','attention_required','retry_scheduled_or_dead'):
                messagebox.showwarning('Operational attention',
                    'An integrity or transaction-review check needs attention. See the status in Reliability Center.',parent=self.root)
        self.run_job(lambda:self.reliability.run_one(),done,'Running read-only operational check...')

    def _rel_backup(self):
        filename=filedialog.asksaveasfilename(parent=self.root,defaultextension='.sqlite3',
             filetypes=[('SQLite database','*.sqlite3'),('Database','*.db')],
             initialfile='nocturne_operations_backup.sqlite3')
        if not filename:return
        def done(result):
            messagebox.showinfo('Verified operations backup','Read-only operations journal verified. This is NOT a wallet backup.',parent=self.root)
            self._rel_refresh()
        self.run_job(lambda:self.reliability.backup(filename),done,'Creating operational metadata backup...')
