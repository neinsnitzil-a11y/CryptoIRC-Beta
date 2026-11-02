"""Phase 18 Release Center: local evidence, support export and incident playbook."""
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from release_ops import assess_release,write_exclusive_json,ReleaseOpsError,INCIDENT_PLAYBOOK

CARD='#15101e'; GREEN='#47fca3';PURPLE='#b363ff'; MUTED='#a39ab6'; WARN='#ff707a'

class ReleaseOpsUI:
    def page_release_center(self):
        self.head('Release Center / Phase 18',
            'Deployment safety, static upgrade policies, privacy-safe support diagnostics, and incident guidance. '
            'No auto-updates or real-money release approvals.')
        self._release_assessment=assess_release()
        self._release_summary=tk.StringVar(value='PRODUCTION: BLOCKED — external certifications not complete')
        self._release_details=tk.StringVar(value='Select a check for its current evidence and limitations.')
        area=tk.Frame(self.content,bg=CARD,padx=16,pady=15);area.pack(fill='x',pady=(0,12))
        tk.Label(area,text='01 / RELEASE READINESS',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(area,textvariable=self._release_summary,fg=WARN,bg=CARD,font=('Consolas',10,'bold'),
                 wraplength=940,justify='left').pack(anchor='w',pady=9)
        tk.Label(area,text='Local integrity checks are NOT a security audit. Real Windows installer, external key pin, '
                         'disaster recovery and mainnet/fiat certifications are still missing.',fg=MUTED,bg=CARD,
                 justify='left',wraplength=960).pack(anchor='w')
        row=tk.Frame(area,bg=CARD);row.pack(fill='x',pady=(12,0))
        ttk.Button(row,text='RUN OFFLINE DEPLOYMENT CHECKS',command=self._release_run).pack(side='left',padx=(0,10))
        ttk.Button(row,text='EXPORT SAFE SUPPORT REPORT',command=self._release_export).pack(side='left',padx=(0,10))
        ttk.Button(row,text='READ-ONLY HEALTH PULSE',command=self._release_pulse).pack(side='left')
        area=tk.Frame(self.content,bg=CARD,padx=16,pady=14);area.pack(fill='both',expand=True,pady=(0,12))
        tk.Label(area,text='02 / GATE MATRIX',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w',pady=(0,10))
        columns=('gate','result')
        table=ttk.Treeview(area,columns=columns,show='headings',height=11)
        table.heading('gate',text='Deployment requirement');table.heading('result',text='Evidence status')
        table.column('gate',width=560,stretch=True);table.column('result',width=180,stretch=False)
        table.pack(fill='both',expand=True)
        table.bind('<<TreeviewSelect>>',self._release_select)
        self._release_table=table
        tk.Label(area,textvariable=self._release_details,fg=MUTED,bg=CARD,
                 wraplength=945,justify='left').pack(anchor='w',pady=(12,0))
        runbook=tk.Frame(self.content,bg=CARD,padx=16,pady=14);runbook.pack(fill='x')
        tk.Label(runbook,text='03 / INCIDENT PROCEDURES',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w',pady=(0,8))
        for title,desc in INCIDENT_PLAYBOOK:
            tk.Label(runbook,text=title+'  /  '+desc,bg=CARD,fg=MUTED,
                     font=('Consolas',9),wraplength=990,justify='left').pack(anchor='w',pady=3)
        self._release_refresh()

    def _release_refresh(self):
        if not hasattr(self,'_release_table') or not self._release_table.winfo_exists():return
        for item in self._release_table.get_children():self._release_table.delete(item)
        for row in self._release_assessment['checks']+self._release_assessment['external_requirements']:
            self._release_table.insert('','end',iid=row['id'],values=(row['id'].replace('_',' '),row['status']))
        result=self._release_assessment
        local_pass=sum(x['status']=='PASS_LOCAL' for x in result['checks'])
        ext_blocked=sum(x['status']=='BLOCKED_EXTERNAL' for x in result['external_requirements'])
        self._release_summary.set(f'PRODUCTION: BLOCKED    •    {local_pass}/3 local checks passed    •    '
                                  f'{ext_blocked} Phase-18 external release checks blocked')

    def _release_select(self,event=None):
        selected=self._release_table.selection()
        if not selected:return
        item=next((x for x in self._release_assessment['checks']+self._release_assessment['external_requirements'] if x['id']==selected[0]),None)
        if item:self._release_details.set(item['note'])

    def _release_run(self):
        self.run_job(lambda:assess_release(), self._release_completed,'CHECKING OFFLINE RELEASE GATES...')

    def _release_completed(self,result):
        self._release_assessment=result
        self._release_refresh()
        if any(x['status']=='FAIL_LOCAL' for x in result['checks']):
            messagebox.showwarning('Release preflight', 'A local check failed; production remains blocked.',parent=self.root)

    def _release_pulse(self):
        """Explicit on-demand observation only; does not broadcast or phone home."""
        def sample():
            state=self.reliability.stats()
            db_health=self.reliability.integrity_scan()
            counts=state['counts']
            bad=any(v in ('integrity_failed','unavailable','invalid_file') for v in db_health.values())
            warning=bad or counts['dead']>0
            return {'status':'ATTENTION REQUIRED' if warning else 'LOCAL READ-ONLY CHECK COMPLETE',
                    'queued':counts['queued'],'failed_jobs':counts['dead'],
                    'data_stores':{k:v for k,v in db_health.items()}}
        def done(result):
            self._release_details.set(
                result['status']+f"  •  queued diagnostic jobs: {result['queued']}  •  failed jobs: {result['failed_jobs']}  •  "
                +', '.join(k+'='+v for k,v in result['data_stores'].items())
                +'  •  Not a node, payment provider, or backup-recovery availability test.')
        self.run_job(sample,done,'RUNNING LOCAL READ-ONLY HEALTH PULSE...')

    def _release_export(self):
        filename=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',
                    filetypes=[('JSON diagnostics','*.json')],initialfile='nocturne-v4.5-support-UNVERIFIED.json')
        if not filename:return
        try:write_exclusive_json(self._release_assessment,filename)
        except (ReleaseOpsError,OSError):
            messagebox.showwarning('Export refused','Use a new path outside the source folder; existing reports are not overwritten.',parent=self.root)
        else:
            messagebox.showinfo('Support report exported',
                'Saved only fixed diagnostic categories. No addresses, wallets, secrets, arbitrary logs or keys are included. '
                'This report is not an external release approval.',parent=self.root)
