"""Read-only operations telemetry; never shows transaction payloads or secrets."""
import tkinter as tk
from tkinter import ttk

BG='#07060b';CARD='#15101e';GREEN='#47fca3';PURPLE='#9a4bea';MUTED='#a39ab6';FG='#f2edf9'

class PerformanceUI:
    def page_performance_center(self):
        self.head('Performance Center','Bounded background scheduling and operational health. No passwords, wallet secrets or transaction payloads are recorded.')
        outer=tk.Frame(self.content,bg=CARD,padx=18,pady=18,
                       highlightthickness=1,highlightbackground='#3b2654')
        outer.pack(fill='x',pady=10)
        tk.Label(outer,text='// DESKTOP WORKER POOL',font=('Consolas',15,'bold'),fg=GREEN,bg=CARD).pack(anchor='w')
        self.perf_status=tk.StringVar(value='Checking scheduler…')
        tk.Label(outer,textvariable=self.perf_status,font=('Consolas',11),fg=FG,bg=CARD,
                 justify='left',anchor='w').pack(fill='x',pady=12)
        ttk.Button(outer,text='REFRESH STATISTICS',command=self._perf_update).pack(anchor='w')
        tk.Label(outer,text='BACKGROUND LIMITS: 4 I/O workers + 2 reserved finance workers; up to 32 I/O + 8 financial waiting jobs. Duplicate balance polls coalesce.\n'
                 'Connection errors show UNAVAILABLE, never an invented zero. Queue pressure rejects excess work instead of exhausting memory.',
                 bg=CARD,fg=MUTED,justify='left',wraplength=850).pack(anchor='w',pady=13)
        box=tk.Frame(self.content,bg=CARD,padx=18,pady=18,
                     highlightthickness=1,highlightbackground='#3b2654')
        box.pack(fill='x',pady=8)
        tk.Label(box,text='// READ-ONLY BALANCE POLLING',font=('Consolas',14,'bold'),fg=PURPLE,bg=CARD).pack(anchor='w')
        tk.Label(box,text='Auto-refresh interval:',bg=CARD,fg=FG).pack(anchor='w',pady=(13,4))
        self.perf_interval=tk.StringVar(value=str(getattr(self,'lb_interval_ms',30000)//1000))
        ttk.Combobox(box,textvariable=self.perf_interval,values=('15','30','45','60','120'),
                     state='readonly',width=12).pack(anchor='w')
        ttk.Button(box,text='APPLY INTERVAL',command=self._perf_apply_interval).pack(anchor='w',pady=9)
        tk.Label(box,text='Changing the interval never changes signing, settlement, encryption or funds.',
                 bg=CARD,fg=MUTED).pack(anchor='w')
        self._perf_update()
        self.root.after(1000,self._perf_tick)

    def _perf_tick(self):
        if getattr(self,'current_page',None)!='Performance Center':return
        try:self._perf_update()
        except tk.TclError:return
        self.root.after(1000,self._perf_tick)

    def _perf_update(self):
        st=self.executor.stats()
        v=getattr(self,'perf_status',None)
        if v is not None:
            v.set(f'I/O workers: {st.running} / 4   |   I/O queue: {st.queued} / 32\n'
                  f'Finance workers: {st.financial_running} / 2   |   Finance queue: {st.financial_queued} / 8\n'
                  f'Jobs completed: {st.completed}   |   Failed: {st.failed}   |   Rejected: {st.rejected}\n'
                  f'P95 work latency (including queue): {st.p95_ms:.1f} ms   |   Peak active: {st.peak_active}\n'
                  f'Coalesced in-flight task keys: {st.busy_keys}')

    def _perf_apply_interval(self):
        seconds=int(self.perf_interval.get())
        if seconds not in (15,30,45,60,120):return
        self.lb_interval_ms=seconds*1000
        self._perf_update()
