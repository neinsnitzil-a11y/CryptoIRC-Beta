#!/usr/bin/env python3
"""Tkinter GUI controller for Windows PyInstaller + Inno Setup release workflow."""
from __future__ import annotations
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import build_release as build

ROOT=Path(__file__).resolve().parent
BG='#07060b'; PANEL='#14101e'; FIELD='#0e0b14'; BORDER='#39254f'
TEXT='#f0e9f8'; SUB='#a69bb9'; GREEN='#47fca3'; PURPLE='#b363ff'; RED='#ff6f7e'

class BuilderGUI:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title('CRYPTO // NOCTURNE - RELEASE COMPILER')
        self.root.geometry('1080x730');self.root.minsize(860,610)
        self.root.configure(bg=BG)
        try:
            self.root.iconbitmap(str(ROOT/'brand_assets'/'CRYPTO_NOCTURNE.ico'))
        except (tk.TclError,OSError):pass
        self.q=queue.Queue();self.proc=None;self.active=False
        self.loglines=[]
        style=ttk.Style(self.root)
        if 'clam' in style.theme_names():style.theme_use('clam')
        style.configure('TButton',font=('Consolas',10,'bold'),padding=9,background=FIELD,foreground=TEXT,bordercolor=BORDER)
        style.map('TButton',background=[('active','#2b1c3c')])
        style.configure('Accent.TButton',background='#1b5043',foreground=GREEN,bordercolor='#25644f')
        style.map('Accent.TButton',background=[('active','#236b50')])
        header=tk.Frame(self.root,bg=FIELD,height=92)
        header.pack(fill='x');header.pack_propagate(False)
        try:
            from PIL import Image,ImageTk
            with Image.open(ROOT/'brand_assets'/'tor_round.png') as im:
                self.brand=ImageTk.PhotoImage(im.convert('RGBA').resize((65,65)))
            tk.Label(header,image=self.brand,bg=FIELD).pack(side='left',padx=(23,13),pady=12)
        except Exception:
            tk.Label(header,text='◈',fg=PURPLE,bg=FIELD,font=('Consolas',34)).pack(side='left',padx=26)
        hd=tk.Frame(header,bg=FIELD);hd.pack(side='left',pady=15)
        tk.Label(hd,text='C R Y P T O   //   N O C T U R N E',fg=GREEN,bg=FIELD,
                 font=('Consolas',15,'bold')).pack(anchor='w')
        tk.Label(hd,text='WINDOWS EXECUTABLE & INNO SETUP BUILD CENTER   •   v4.5.1',
                 fg=PURPLE,bg=FIELD,font=('Consolas',9,'bold')).pack(anchor='w',pady=(6,0))
        self.status=tk.StringVar(value='READY / build tools are idle')
        tk.Label(header,textvariable=self.status,fg=GREEN,bg=FIELD,font=('Consolas',9),
                 padx=18).pack(side='right')
        main=tk.Frame(self.root,bg=BG,padx=19,pady=15);main.pack(fill='both',expand=True)
        tk.Label(main,text='RELEASE OPERATIONS',bg=BG,fg=PURPLE,font=('Consolas',10,'bold')).pack(anchor='w',pady=(0,7))
        controls=tk.Frame(main,bg=BG);controls.pack(fill='x')
        items=[('01  PREFLIGHT','check'),('02  RUN TESTS','test'),('03  BUILD EXE','exe'),
               ('04  BUILD INSTALLER','installer'),('BUILD BOTH','full'),('PORTABLE EXE','portable'),('RELEASE CHECKS','release-check')]
        self.buttons=[]
        for idx,(name,action) in enumerate(items):
            b=ttk.Button(controls,text=name,style='Accent.TButton' if action=='full' else 'TButton',
                         command=lambda what=action:self.start(what))
            b.grid(row=idx//3,column=idx%3,padx=5,pady=6,sticky='ew')
            self.buttons.append(b)
        for i in range(3):controls.grid_columnconfigure(i,weight=1)
        self.launch_installer = tk.BooleanVar(value=False)
        self.launch_option = tk.Checkbutton(
            main, text='Launch Inno Setup installer after a successful build',
            variable=self.launch_installer, onvalue=True, offvalue=False,
            bg=BG, fg=GREEN, activeforeground=GREEN, activebackground=BG,
            selectcolor=FIELD, highlightthickness=0, font=('Consolas',10),
        )
        self.launch_option.pack(anchor='w',pady=(6,0))
        self.last_action=None
        self.launch_requested=False
        row=tk.Frame(main,bg=BG);row.pack(fill='x',pady=(8,8))
        tk.Label(row,text='ENVIRONMENT:',bg=BG,fg=PURPLE,font=('Consolas',9,'bold')).pack(side='left')
        self.detect=tk.StringVar(value='Detecting...')
        tk.Label(row,textvariable=self.detect,bg=BG,fg=SUB,font=('Consolas',9)).pack(side='left',padx=(8,0))
        ttk.Button(row,text='Open outputs',command=self.open_outputs).pack(side='right')
        ttk.Button(row,text='Save log',command=self.save_log).pack(side='right',padx=7)
        tk.Label(main,text='BUILD LOG / COMPILER OUTPUT',bg=BG,fg=PURPLE,font=('Consolas',10,'bold')).pack(anchor='w',pady=(6,7))
        logframe=tk.Frame(main,bg=BORDER,padx=1,pady=1);logframe.pack(fill='both',expand=True)
        self.log=tk.Text(logframe,bg=FIELD,fg=TEXT,insertbackground=GREEN,wrap='word',
                         font=('Consolas',9),borderwidth=0,relief='flat',state='disabled',
                         padx=13,pady=11)
        scroll=tk.Scrollbar(logframe,command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.log.pack(fill='both',expand=True)
        self.log.tag_configure('success',foreground=GREEN)
        self.log.tag_configure('error',foreground=RED)
        self.log.tag_configure('highlight',foreground=PURPLE)
        tk.Label(main,text='BUILDING AN EXE DOES NOT AUTHORIZE REAL-MONEY OPERATIONS OR PROVIDE A SECURITY AUDIT.',
                 fg=RED,bg=BG,font=('Consolas',9,'bold'),anchor='w').pack(fill='x',pady=(11,1))
        self.logline('Source: '+str(ROOT))
        self.logline('The full build runs tests, packages static resources, then invokes ISCC.exe.')
        self.logline('No .vault/.fiat private files should be present in the app source tree.')
        self.refresh_environment()
        self.root.after(100,self.poll)
        self.root.protocol('WM_DELETE_WINDOW',self.close)

    def refresh_environment(self):
        inno=build.find_inno_setup()
        self.detect.set(('Windows' if os.name=='nt' else 'NON-WINDOWS')+
                        '  |  Python '+sys.version.split()[0]+
                        '  |  Inno '+('found' if inno else 'not detected'))

    def logline(self,line):
        line=str(line).rstrip('\r\n')
        self.loglines.append(line)
        tag=('error' if '[FAILED]' in line or 'ERROR:' in line else
             'success' if '[PASS]' in line or '[SUCCESS]' in line else
             'highlight' if line.startswith('[BUILD]') or line.startswith('[TEST]') else None)
        self.log.configure(state='normal')
        self.log.insert('end',line+'\n',tag)
        self.log.configure(state='disabled');self.log.see('end')

    def start(self,action):
        if self.active:return
        if action not in ('check','test','release-check') and os.name!='nt':
            messagebox.showwarning('Windows required','To build a Windows EXE/installer, run this builder on Windows.')
            return
        self.active=True;self.last_action=action
        self.launch_requested=bool(self.launch_installer.get()) and action in ('full','installer')
        self.launch_option.configure(state='disabled')
        self.status.set('RUNNING / '+action.upper())
        for b in self.buttons:b.configure(state='disabled')
        self.logline('\n'+'='*68)
        self.logline('TASK '+action.upper()+'  '+datetime.now().isoformat(timespec='seconds'))
        threading.Thread(target=self.worker,args=(action,),daemon=True).start()

    def worker(self,action):
        args=[sys.executable,'-u',str(ROOT/'build_release.py'),action]
        try:
            self.proc=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                       encoding='utf-8',errors='replace',bufsize=1)
            assert self.proc.stdout is not None
            for line in self.proc.stdout:self.q.put(('line',line))
            code=self.proc.wait()
            self.q.put(('done',code))
        except Exception as exc:self.q.put(('error',str(exc)))
        finally:self.proc=None

    def poll(self):
        try:
            while True:
                type_,payload=self.q.get_nowait()
                if type_=='line':self.logline(payload)
                elif type_=='done':
                    self.logline('[PASS] Build task finished.' if payload==0 else f'[FAILED] Build task exited with code {payload}.')
                    self.finish(payload==0)
                elif type_=='error':self.logline('[FAILED] '+payload);self.finish(False)
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def finish(self,ok):
        self.active=False
        self.status.set('SUCCESS / OUTPUT READY' if ok else 'FAILED / REVIEW LOG')
        for b in self.buttons:b.configure(state='normal')
        self.launch_option.configure(state='normal')
        self.refresh_environment()
        # Launch only after the build process returned success. This code runs
        # on Tk's main thread; no shell command or user-entered path is used.
        should_open = ok and self.launch_requested and self.last_action in ('full','installer')
        self.launch_requested=False
        if should_open:
            installer=build.INSTALLER
            if os.name == 'nt' and installer.is_file():
                try:
                    os.startfile(str(installer))
                    self.logline('[PASS] Opened Inno Setup installer.')
                except OSError:
                    self.logline('[FAILED] Installer built but could not be opened.')
                    messagebox.showerror('Installer launch failed',
                                         'The installer was built but Windows could not open it. Use Open outputs.')
            else:
                self.logline('[FAILED] Installer was not found at the expected release path.')

    def open_outputs(self):
        folder=ROOT.parent/'release' if (ROOT.parent/'release').is_dir() else ROOT.parent/'dist' if (ROOT.parent/'dist').is_dir() else ROOT.parent
        if os.name=='nt':os.startfile(str(folder))
        else:messagebox.showinfo('Build folder',str(folder))

    def save_log(self):
        path=filedialog.asksaveasfilename(title='Save compiler log',defaultextension='.txt',
                   filetypes=[('Text files','*.txt')],initialfile='NOCTURNE_build_log.txt')
        if path:
            Path(path).write_text('\n'.join(self.loglines)+'\n',encoding='utf-8')
            messagebox.showinfo('Saved','Build log saved successfully.')

    def close(self):
        if self.active:
            messagebox.showwarning('Build in progress','Allow the build to finish before closing the compiler.')
            return
        self.root.destroy()

if __name__=='__main__':BuilderGUI().root.mainloop()
