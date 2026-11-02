"""Security Center: encrypted-only backup, authenticated inspection and safe rotation."""
from __future__ import annotations
import tkinter as tk
from tkinter import filedialog,messagebox,simpledialog,ttk
from pathlib import Path
from vault_security import inspect_vault, backup_encrypted_vault, rotate_vault_with_backup

class VaultSecurityUI:
    def page_vault_security(self):
        self.head('Vault Security Center',
                  'Local authenticated file checks, encrypted backups and rollback-safe password rotation. '
                  'None of these operations proves independent seed recovery.')
        c=self.card()
        self.vsc_path=tk.StringVar(value=self.vault_paths[0] if self.vault_paths else '')
        self.info(c,'Select an existing encrypted .vault file. Other wallet types (Bitcoin Core, EVM keystore, Monero wallet files) have their own backup requirements.')
        ttk.Combobox(c,textvariable=self.vsc_path,values=self.vault_paths).pack(fill='x',pady=7)
        ttk.Button(c,text='Choose .vault file',command=self._vsc_pick).pack(anchor='w',pady=5)
        ttk.Button(c,text='Verify encryption and file permissions',command=self._vsc_verify).pack(anchor='w',pady=5)
        ttk.Button(c,text='Create independently verified ENCRYPTED backup',command=self._vsc_backup).pack(anchor='w',pady=5)
        ttk.Button(c,text='Rotate password WITH encrypted rollback backup',command=self._vsc_rotate).pack(anchor='w',pady=5)
        self.vsc_status=tk.StringVar(value='No vault inspected. No recovery has been independently verified.')
        tk.Label(c,textvariable=self.vsc_status,bg=c.cget('bg'),fg='#47fca3',font=('Consolas',10),
                 justify='left',wraplength=780).pack(anchor='w',pady=12)
        notice=self.card()
        self.info(notice,'A matching encrypted copy protects against file loss, NOT forgotten passwords or corrupted recovery phrases. Independently restore your seed in a compatible trusted wallet before funding.')
        self.info(notice,'On Windows, verify NTFS access controls yourself. Removable drives and cloud-synced folders may expose encrypted files or backups. Python cannot guarantee in-memory secret erasure.')

    def _vsc_pick(self):
        path=filedialog.askopenfilename(parent=self.root,title='Select encrypted vault',filetypes=[('Encrypted vault','*.vault')])
        if path:self.vsc_path.set(path)

    def _vsc_password(self,label='Vault password'):
        return simpledialog.askstring(label,'Enter the existing encryption password:',parent=self.root,show='●')

    def _vsc_destination(self):
        p=Path(self.vsc_path.get()).expanduser()
        return filedialog.asksaveasfilename(parent=self.root,title='Save encrypted vault backup in another folder',
                                            initialfile=p.stem+'_encrypted_backup.vault',
                                            defaultextension='.vault',filetypes=[('Encrypted vault','*.vault')])

    def _vsc_verify(self):
        pw=self._vsc_password()
        if not pw:return
        source=self.vsc_path.get()
        def done(result):
            self.vsc_status.set(f'Encryption authenticated: YES   |   Size: {result.file_bytes} bytes\n'
                                f'Encrypted SHA-256: {result.encrypted_digest}\n'
                                f'Permissions: {result.permission_status}\n'
                                'Recovery by independent wallet: NOT VERIFIED')
        self.run_job(lambda:inspect_vault(source,pw),done,'Authenticating encrypted vault...')

    def _vsc_backup(self):
        pw=self._vsc_password()
        if not pw:return
        destination=self._vsc_destination()
        if not destination:return
        if not messagebox.askyesno('Backup encrypted file',
            'Save a NEW encrypted copy to the selected location? It must be in a different folder. '
            'The destination must not already exist. This is NOT recovery-phrase verification.',parent=self.root):return
        source=self.vsc_path.get()
        def done(result):
            self.vsc_status.set('Encrypted backup written and authenticated.\n'
                                f'Encrypted SHA-256: {result.encrypted_digest}\n'
                                'Independent recovery: NOT VERIFIED')
            messagebox.showinfo('Encrypted backup verified',
                'The saved encrypted bytes match and unlock with the supplied password. '
                'Store another independently verified seed backup offline.',parent=self.root)
        self.run_job(lambda:backup_encrypted_vault(source,destination,pw),done,'Verifying encrypted backup...')

    def _vsc_rotate(self):
        old=self._vsc_password('Current vault password')
        if not old:return
        new=simpledialog.askstring('New vault password','New password (14+ characters):',parent=self.root,show='●')
        if not new:return
        confirm=simpledialog.askstring('Confirm new password','Repeat new password:',parent=self.root,show='●')
        if new!=confirm or len(new)<14 or new==old:
            messagebox.showerror('Invalid password','Use a different matching password of at least 14 characters.',parent=self.root)
            return
        dest=self._vsc_destination()
        if not dest:return
        if not messagebox.askyesno('Confirm password rotation',
            'Create an authenticated rollback backup with your OLD password, then re-encrypt the live vault? '
            'The backup is still protected by the OLD password, which you must retain until securely retired.',parent=self.root):return
        src=self.vsc_path.get()
        def done(result):
            self.public_unlocked.clear()
            self.vsc_status.set('Vault password changed; new ciphertext authenticated.\n'
                                'Encrypted rollback backup retained under OLD password.\n'
                                'Independent recovery: NOT VERIFIED')
            messagebox.showinfo('Rotation completed',
                'Vault was rotated after making an authenticated encrypted rollback copy. '
                'Test the new password and separately verify recovery before retiring the old backup.',parent=self.root)
        self.run_job(lambda:rotate_vault_with_backup(src,old,new,dest),done,'Safely rotating encrypted vault...')
