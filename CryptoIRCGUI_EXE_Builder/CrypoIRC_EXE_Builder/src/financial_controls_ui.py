"""Tkinter production-gate dashboard; never initializes finance backends locally."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk,messagebox
from security_gates import GATES,release_status

BG='#07060b'; CARD='#15101e'; FG='#f2edf9'; GREEN='#47fca3'; PURPLE='#a977f5'; RED='#ff707a'; MUTED='#a39ab6'

class FinancialControlsUI:
    def page_financial_controls(self):
        self.head('Financial Controls','Release checklist · isolated sandbox accounting · security verification status')
        top=tk.Frame(self.content,bg='#210f25',highlightbackground='#a14452',highlightthickness=1,padx=20,pady=16)
        top.pack(fill='x',pady=(0,15))
        tk.Label(top,text='⛔  LIVE FINANCIAL OPERATIONS: NOT AUTHORIZED',bg='#210f25',fg=RED,
                 font=('Consolas',14,'bold')).pack(anchor='w')
        tk.Label(top,text='The desktop build must never treat checkout links, manually entered money or simulated ledger entries as real settled funds.',
                 bg='#210f25',fg=FG,font=('Segoe UI',10),wraplength=980,justify='left').pack(anchor='w',pady=(8,0))
        cards=tk.Frame(self.content,bg=BG);cards.pack(fill='x',pady=10)
        for title,desc,color in [
            ('PRIVATE KEY VAULT','Local only. Cryptographic audit pending.',GREEN),
            ('FIAT PAYMENTS','Approved provider backend required.',RED),
            ('SANDBOX JOURNAL','Reference engine; zero real funds.',PURPLE),
        ]:
            c=tk.Frame(cards,bg=CARD,highlightbackground='#3b2654',highlightthickness=1,padx=13,pady=14)
            c.pack(side='left',fill='both',expand=True,padx=(0,10))
            tk.Label(c,text=title,bg=CARD,fg=color,font=('Consolas',10,'bold')).pack(anchor='w')
            tk.Label(c,text=desc,bg=CARD,fg=MUTED,font=('Segoe UI',9),justify='left',wraplength=230).pack(anchor='w',pady=(8,0))
        tk.Label(self.content,text='PRODUCTION RELEASE GATES',fg=GREEN,bg=BG,font=('Consolas',13,'bold')).pack(anchor='w',pady=(12,8))
        for title,status,desc in GATES:
            r=tk.Frame(self.content,bg=CARD,padx=11,pady=9,highlightthickness=1,highlightbackground='#3b2654')
            r.pack(fill='x',pady=3)
            tk.Label(r,text='['+status+']',fg=RED if status=='BLOCKED' else PURPLE,bg=CARD,font=('Consolas',9,'bold'),width=12,anchor='w').pack(side='left')
            text=tk.Frame(r,bg=CARD);text.pack(side='left',fill='x',expand=True)
            tk.Label(text,text=title,fg=FG,bg=CARD,font=('Segoe UI',10,'bold')).pack(anchor='w')
            tk.Label(text,text=desc,fg=MUTED,bg=CARD,font=('Segoe UI',9),justify='left',wraplength=820).pack(anchor='w')
        ttk.Button(self.content,text='VIEW SECURITY LIMITATIONS',style='Purple.TButton',command=lambda:messagebox.showinfo(
            'CRYPTO NOCTURNE Security','See PRODUCTION_READINESS.md and PRODUCTION_SECURITY_V2.3.md.\n\nNo third-party audits, financial licenses, or real settlement are implied.')).pack(anchor='w',pady=13)
