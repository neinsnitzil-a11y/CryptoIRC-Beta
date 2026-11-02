"""Private, local-only mnemonic backup display for newly generated encrypted vaults.

Optional explicit TXT export is unencrypted and dangerous; no clipboard, logging, telemetry or network I/O.
This screen does not replace independent recovery verification using trusted wallet software.
"""
from __future__ import annotations

import hmac
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from recovery_export import save_plaintext_backup, suggested_filename

_BG='#07060b'; _PANEL='#15101e'; _TEXT='#f2edf9'
_GREEN='#47fca3'; _PURPLE='#ba74ff'; _WARNING='#ff707a'; _MUTED='#a39ab6'


def pick_challenge_positions(words: list[str], count: int = 4) -> tuple[int,...]:
    """Ask for four unpredictable numbered words from a written backup."""
    if len(words) not in (12, 24, 25):
        raise ValueError('Unsupported recovery phrase length')
    return tuple(sorted(secrets.SystemRandom().sample(range(len(words)), min(count, len(words)))))


def check_challenge(words: list[str], positions: tuple[int,...], answers: list[str]) -> bool:
    """Verify sampled answers, without ever saving them outside process memory."""
    if len(positions) != len(answers) or not positions or len(set(positions)) != len(positions):
        return False
    checks = [0 <= idx < len(words) and hmac.compare_digest(words[idx], value.strip().lower())
              for idx,value in zip(positions,answers)]
    return all(checks)


class RecoveryBackupDialog:
    """Modal one-time backup workflow. Operates on decrypted groups in memory only.

    The existing Security screen can reveal saved groups later after password entry.
    Completion is *sample verification only*, not a verified cross-wallet restore.
    """
    def __init__(self, root: tk.Misc, groups: list[dict], on_done, number: int = 1, total: int = 1):
        if not isinstance(groups, list) or not groups:
            raise ValueError('No encrypted recovery material was returned')
        checked=[]
        for group in groups:
            words=group.get('mnemonic','').split()
            if len(words) not in (12,24,25) or not all(isinstance(w,str) and w for w in words):
                raise ValueError('Invalid stored recovery material')
            checked.append({'words':words, 'scheme':group.get('scheme','bip39'),
                            'asset':group.get('asset','wallet'),
                            'extra':group.get('passphrase','')})
        self.groups=checked
        self.on_done=on_done
        self.number=number; self.total=total
        self.index=0
        self.positions=()
        self.answers=[]
        self.extra_entry=None
        self.finished=False
        self.win=tk.Toplevel(root)
        self.win.title('NOCTURNE // PRIVATE RECOVERY BACKUP')
        self.win.configure(bg=_BG)
        self.win.geometry('960x730')
        self.win.minsize(760,570)
        self.win.transient(root)
        self.win.grab_set()
        self.win.protocol('WM_DELETE_WINDOW',self._close_without_verification)
        self._make_intro()
        # The screen should not leave sensitive words visible indefinitely.
        self.win.after(300000,self._expire)

    def _clear(self):
        for child in self.win.winfo_children():child.destroy()

    def _heading(self,title,desc):
        tk.Label(self.win,text='// '+title,bg=_BG,fg=_GREEN,
                 font=('Consolas',18,'bold')).pack(anchor='w',padx=24,pady=(20,8))
        tk.Label(self.win,text=desc,bg=_BG,fg=_MUTED,font=('Segoe UI',10),
                 justify='left',wraplength=860).pack(anchor='w',padx=24,pady=(0,15))

    def _button(self,text,callback,primary=True):
        return tk.Button(self.win,text=text,command=callback,bg='#166448' if primary else '#38234f',
                         fg=_TEXT,activebackground='#22815f',activeforeground='white',
                         font=('Consolas',10,'bold'),relief='flat',padx=14,pady=10)

    def _make_intro(self):
        self._clear()
        self._heading('RECOVERY BACKUP REQUIRED',
            f'Encrypted wallet {self.number} of {self.total} was created. Record its recovery words OFFLINE. '
            'The words are never sent to a server or clipboard. Optional TXT export requires explicit consent.')
        panel=tk.Frame(self.win,bg=_PANEL,padx=22,pady=24)
        panel.pack(fill='x',padx=24,pady=12)
        for msg in ('Write the words IN ORDER on paper or a dedicated offline backup.',
                    'Never photograph, screenshot, email, cloud-sync, or share these words.',
                    'If you save a TXT, it is UNENCRYPTED. Store only on secure offline media.',
                    'The vault password is NOT the same thing as the recovery phrase.',
                    'BIP39 extra passphrases, if used, must be backed up SEPARATELY.',
                    'This application is experimental. Independently restore in a trusted compatible wallet before deposits.'):
            tk.Label(panel,text='•  '+msg,bg=_PANEL,fg=_TEXT,font=('Segoe UI',10),
                     wraplength=800,justify='left').pack(anchor='w',pady=5)
        row=tk.Frame(self.win,bg=_BG);row.pack(anchor='w',padx=24,pady=20)
        self._button('SHOW MY RECOVERY WORDS',self._show_words).pack(in_=row,side='left',padx=(0,12))
        self._button('SKIP (NOT BACKED UP)',self._close_without_verification,False).pack(in_=row,side='left')

    def _show_words(self):
        self._clear()
        group=self.groups[self.index]; words=group['words']
        self._heading(f'RECOVERY GROUP {self.index+1} / {len(self.groups)}',
            f"{group['asset']} • {group['scheme']} • {len(words)} words   |   Wallet {self.number} of {self.total}")
        frame=tk.Frame(self.win,bg=_PANEL,padx=15,pady=15)
        frame.pack(fill='both',expand=True,padx=24,pady=10)
        for col in range(4):frame.columnconfigure(col,weight=1)
        for i,word in enumerate(words):
            cell=tk.Frame(frame,bg='#0e0a16',padx=8,pady=9,highlightbackground='#3b2654',highlightthickness=1)
            cell.grid(row=i//4,column=i%4,padx=5,pady=5,sticky='ew')
            tk.Label(cell,text=f'{i+1:02d}',bg='#0e0a16',fg=_PURPLE,
                     font=('Consolas',10,'bold')).pack(side='left',padx=(0,9))
            tk.Label(cell,text=word,bg='#0e0a16',fg=_TEXT,
                     font=('Consolas',12,'bold')).pack(side='left')
        if group['extra']:
            tk.Label(self.win,text='IMPORTANT: This wallet also uses an advanced BIP39 passphrase. Back it up separately.',
                     bg=_BG,fg=_WARNING,font=('Segoe UI',10,'bold'),wraplength=850).pack(padx=24,pady=6)
        tk.Label(self.win,text='Auto-hides after five minutes. Write these words on OFFLINE paper now.',
                 bg=_BG,fg=_WARNING,font=('Segoe UI',10,'bold')).pack(pady=9)
        row=tk.Frame(self.win,bg=_BG);row.pack(anchor='w',padx=24,pady=(0,18))
        self._button('I WROTE THEM DOWN — VERIFY',self._make_challenge).pack(in_=row,side='left',padx=(0,12))
        self._button('SAVE AS .TXT (UNENCRYPTED)',self._save_txt,False).pack(in_=row,side='left',padx=(0,12))
        self._button('CLOSE UNVERIFIED',self._close_without_verification,False).pack(in_=row,side='left')

    def _save_txt(self):
        """Optional explicit TXT export. Never auto-create a plaintext seed file."""
        group=self.groups[self.index]
        approved=messagebox.askyesno(
            'UNENCRYPTED recovery TXT — security warning',
            'A plain .txt file contains your FULL recovery phrase and is NOT encrypted.\n\n'
            'Anyone who reads or copies it may be able to control your funds.\n'
            'Saving to Downloads, Desktop, cloud storage or an infected USB is unsafe.\n\n'
            'Paper or encrypted offline storage is safer.\n\n'
            'Do you explicitly want to save this UNENCRYPTED text file?',
            icon='warning', parent=self.win)
        if not approved: return
        filename=suggested_filename(str(group['asset']),self.number,self.index+1)
        destination=filedialog.asksaveasfilename(
            parent=self.win,title='Choose OFFLINE location for UNENCRYPTED recovery TXT',
            initialfile=filename,defaultextension='.txt',
            filetypes=[('Plain text (unencrypted)','*.txt')])
        if not destination: return
        try:
            save_plaintext_backup(destination,asset=str(group['asset']),
                                  scheme=str(group['scheme']),words=group['words'],
                                  extra_passphrase_used=bool(group['extra']))
        except FileExistsError:
            messagebox.showerror('TXT not saved','Destination already exists. Pick a DIFFERENT filename; existing files are never overwritten.',parent=self.win)
            return
        except (OSError, ValueError):
            messagebox.showerror('TXT not saved','Unable to save a .txt file to the selected location. No recovery words were logged.',parent=self.win)
            return
        messagebox.showwarning('Unencrypted backup saved',
            'Your plaintext recovery phrase was saved at the location you selected.\n\n'
            'Move it to protected OFFLINE storage. Do not leave copies on a shared PC, cloud drive or Downloads folder.\n\n'
            'Export does NOT count as verified recovery. Continue the backup challenge and independently test restoration.',
            parent=self.win)

    def _make_challenge(self):
        words=self.groups[self.index]['words']
        self.positions=pick_challenge_positions(words)
        self._clear()  # Remove EVERY word label before accepting responses.
        self.answers=[]
        self._heading('VERIFY YOUR PAPER BACKUP',
                      'The recovery phrase is now hidden. Enter the requested word numbers from your PAPER backup, not memory.')
        form=tk.Frame(self.win,bg=_PANEL,padx=24,pady=22)
        form.pack(fill='x',padx=24,pady=16)
        for idx in self.positions:
            row=tk.Frame(form,bg=_PANEL);row.pack(fill='x',pady=9)
            tk.Label(row,text=f'WORD #{idx+1:02d}',fg=_PURPLE,bg=_PANEL,
                     font=('Consolas',11,'bold'),width=12,anchor='w').pack(side='left')
            entry=ttk.Entry(row,show='●',width=35)
            entry.pack(side='left',fill='x',expand=True,padx=9)
            self.answers.append(entry)
        self.extra_entry=None
        if self.groups[self.index]['extra']:
            row=tk.Frame(form,bg=_PANEL);row.pack(fill='x',pady=9)
            tk.Label(row,text='EXTRA PASSPHRASE',fg=_PURPLE,bg=_PANEL,
                     font=('Consolas',11,'bold'),width=18,anchor='w').pack(side='left')
            self.extra_entry=ttk.Entry(row,show='●',width=35)
            self.extra_entry.pack(side='left',fill='x',expand=True,padx=9)
        self._button('CHECK MY BACKUP',self._check).pack(anchor='w',padx=24,pady=10)
        self._button('CLOSE UNVERIFIED',self._close_without_verification,False).pack(anchor='w',padx=24,pady=4)

    def _check(self):
        checked=check_challenge(self.groups[self.index]['words'],self.positions,
                                [w.get() for w in self.answers])
        if checked and self.groups[self.index]['extra']:
            extra=self.groups[self.index]['extra'].encode('utf-8')
            supplied=self.extra_entry.get().encode('utf-8') if self.extra_entry is not None else b''
            checked=hmac.compare_digest(extra,supplied)
        if not checked:
            for entry in self.answers:entry.delete(0,'end')
            if self.extra_entry is not None:self.extra_entry.delete(0,'end')
            messagebox.showerror('Backup check failed',
                'One or more words did not match. Do not fund this wallet. You can retry or use Security → Reveal.',
                parent=self.win)
            return
        self.index+=1
        self.answers=[];self.positions=();self.extra_entry=None
        if self.index<len(self.groups):
            self._make_intro()
        else:
            messagebox.showinfo('Paper backup sample checked',
               'Sampled recovery words matched. You must still independently restore the FULL phrase and verify the address before deposits.',
               parent=self.win)
            self._finish(True)

    def _close_without_verification(self):
        self._finish(False)

    def _expire(self):
        if not self.finished and self.win.winfo_exists():
            self._finish(False)

    def _finish(self,verified: bool):
        if self.finished:return
        self.finished=True
        self._clear()
        for group in self.groups:
            group.clear()
        self.groups.clear()
        self.answers.clear()
        self.positions=()
        try:self.win.grab_release()
        except tk.TclError:pass
        self.win.destroy()
        self.on_done(verified)
