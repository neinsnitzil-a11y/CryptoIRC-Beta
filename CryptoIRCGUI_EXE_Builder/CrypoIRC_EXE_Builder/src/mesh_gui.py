"""Desktop interface for the VaultForge v2.7 network, in an isolated chat process.

Compatible with existing CLI/AWS mesh protocol. No wallet or transaction methods.
"""
from __future__ import annotations
import json
import os
import zipfile
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

DARK='#15101e'; BG='#07060b'; TEXT='#f2edf9'; GRAY='#a39ab6'; GREEN='#47fca3'; RED='#ff707a'; BORDER='#3b2654'
AWS='18.227.91.173:6667'


def remote_user_rows(users):
    # The signed-in identity is shown separately in the account header.
    # The "Online Users" list must not confuse this local account with remote peers.
    return [u for u in users if u.get('rooms') != 'you']


def should_auto_connect(active, enabled, mode, endpoint):
    return bool(active and enabled and mode in ('WAN / AWS', 'Tor required') and endpoint.strip())


def worker_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--mesh-bridge']
    return [sys.executable, '-u', '-I', str(Path(__file__).resolve().parent / 'mesh_bridge.py')]


def node_command(args):
    if getattr(sys,'frozen',False):
        return [sys.executable, '--mesh-node', *args]
    return [sys.executable, '-I', str(Path(__file__).resolve().parent / 'vaultmesh' / 'node_manager.py'), *args]


class MeshGUI:
    def init_mesh_gui(self):
        self.mesh_proc=None
        self.mesh_pipe_events=queue.Queue(maxsize=2000)
        self.mesh_var_status=tk.StringVar(value='DISCONNECTED — start with Register / Log In')
        self.mesh_var_endpoint=tk.StringVar(value=AWS)
        self.mesh_var_listen=tk.StringVar(value='127.0.0.1:0')
        self.mesh_var_nick=tk.StringVar(value='')
        self.mesh_var_room=tk.StringVar(value='#general')
        self.mesh_var_text=tk.StringVar(value='')
        self.mesh_var_recipient=tk.StringVar(value='')
        self.mesh_var_target=tk.StringVar(value='TARGET: #general room (not a DM)')
        self.mesh_connected=False
        self.mesh_var_autoconnect=tk.BooleanVar(value=True)
        self.mesh_var_roster_summary=tk.StringVar(value='REMOTE ONLINE: 0 · connect to AWS to see others')
        self.mesh_last_roster_refresh=0.0
        self.mesh_var_mode=tk.StringVar(value='WAN / AWS')
        self.mesh_var_node_name=tk.StringVar(value='NocturneRelay')
        self.mesh_var_node_endpoint=tk.StringVar(value='')
        self.mesh_var_node_listen=tk.StringVar(value='0.0.0.0:6667')
        self.mesh_log_lines=[]
        self.mesh_users=[]
        self.mesh_nodes=[]
        self.mesh_peers=[]
        self.mesh_relays=[]
        self.mesh_active_relay=AWS
        self.mesh_postlogin_connect=False
        self.mesh_lan=[]
        self.mesh_files=[]
        self.mesh_saved=[]
        self.mesh_rooms=['#general']
        self.mesh_room_counts={}
        self.mesh_expected_node=None
        self.mesh_view=None
        self.mesh_selected_public=None
        self.mesh_selected_lan=None
        self.mesh_active=False
        self.mesh_accounts=[]
        self.mesh_event_polling=False
        self.mesh_var_current_user=tk.StringVar(value='Local chat identity: not signed in')

    def _mesh_start_worker(self):
        if self.mesh_proc and self.mesh_proc.poll() is None:
            return True
        try:
            kw=dict(stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    text=True,encoding='utf-8',bufsize=1)
            if os.name == 'nt':
                kw['creationflags'] = subprocess.CREATE_NO_WINDOW
            self.mesh_proc=subprocess.Popen(worker_command(), **kw)
        except (OSError,ValueError) as exc:
            messagebox.showerror('Mesh runtime failed',str(exc),parent=self.root)
            return False
        p=self.mesh_proc
        def read():
            try:
                for line in p.stdout:
                    try: item=json.loads(line)
                    except (ValueError,TypeError): continue
                    try:self.mesh_pipe_events.put_nowait(item)
                    except queue.Full:pass
            except OSError:pass
            try:self.mesh_pipe_events.put_nowait({'kind':'error','text':'Chat worker disconnected'})
            except queue.Full:pass
        threading.Thread(target=read,daemon=True,name='NocturneMeshReader').start()
        if not self.mesh_event_polling:
            self.mesh_event_polling=True
            self.root.after(75,self._mesh_pump)
        return True

    def _mesh_send(self, action, **fields):
        if not self._mesh_start_worker():return
        try:
            payload=json.dumps({'action':action,**fields},ensure_ascii=True,separators=(',',':'))
            if len(payload)>11500:raise ValueError('Command too long')
            self.mesh_proc.stdin.write(payload+'\n')
            self.mesh_proc.stdin.flush()
        except (BrokenPipeError,OSError,ValueError) as exc:
            self._mesh_log('ERROR: chat worker unavailable — '+type(exc).__name__)

    def _mesh_log(self, line):
        text=str(line).replace('\x00','')[:2000]
        self.mesh_log_lines.append(text)
        self.mesh_log_lines=self.mesh_log_lines[-750:]
        box=getattr(self,'mesh_log_box',None)
        if box and box.winfo_exists():
            box.configure(state='normal')
            box.insert('end',text+'\n')
            count=int(box.index('end-1c').split('.')[0]);
            if count>780:box.delete('1.0',f'{count-750}.0')
            box.see('end')
            box.configure(state='disabled')

    def _mesh_pump(self):
        for _ in range(140):
            try:ev=self.mesh_pipe_events.get_nowait()
            except queue.Empty:break
            kind=ev.get('kind','')
            if kind in ('log','error'):
                self._mesh_log(('[ERROR] ' if kind=='error' else '')+str(ev.get('text','')))
            elif kind=='identity':
                self.mesh_active=True
                self.mesh_var_current_user.set(f"Chat: {ev.get('nick','')}@{ev.get('id','')} (local identity)")
                self.mesh_var_status.set('Signed in — use Connect to AWS / Join Room')
                self._mesh_log('[SIGNED IN] '+str(ev.get('nick',''))+' (fingerprint '+str(ev.get('id',''))+')')
                self.mesh_postlogin_connect=True
            elif kind=='accounts':
                self.mesh_accounts=ev.get('names',[])
                if self.mesh_accounts and not self.mesh_var_nick.get(): self.mesh_var_nick.set(self.mesh_accounts[0])
            elif kind=='trust_status':
                self._mesh_verify_relay_trust(ev)
            elif kind=='peer_identity_changed':
                endpoint = str(ev.get('endpoint',''))
                old = str(ev.get('pinned',''))
                new = str(ev.get('presented',''))
                self._mesh_log('[SECURITY] RELAY IDENTITY CHANGED '+endpoint+': '+old+' -> '+new+' (BLOCKED)')
                self.mesh_var_status.set('SECURITY WARNING — relay identity changed; verification required')
                # A remote handshake may report anything: only a separately verified
                # value and explicit user confirmation can authorize trust rotation.
                self._mesh_verify_relay_trust({'endpoint':endpoint,'pinned':old,'detected':new})
            elif kind=='trust_updated':
                endpoint = str(ev.get('endpoint',''))
                self._mesh_log('[TRUST UPDATED] '+endpoint+' now expects '+str(ev.get('new_id',''))+'. Reconnecting ...')
                # Discard any stale ID remembered from a prior public-node listing.
                if self.mesh_expected_node and self.mesh_expected_node[0] == endpoint:
                    self.mesh_expected_node = None
                if self.mesh_active and self.mesh_var_endpoint.get().strip()==endpoint:
                    self._mesh_connect()
            elif kind=='ready':
                self._mesh_log('[ENGINE] VaultForge protocol '+str(ev.get('protocol',''))+' ready; isolated from wallet keys.')
                self._mesh_send('accounts')
            elif kind=='state':
                self.mesh_users=ev.get('users',self.mesh_users)
                self.mesh_connected=bool(ev.get('connected',False))
                self.mesh_peers=ev.get('peers',self.mesh_peers)
                self.mesh_relays=ev.get('relays',self.mesh_relays)
                self.mesh_active_relay=ev.get('active_relay',self.mesh_active_relay)
                if self.mesh_postlogin_connect:
                    self.mesh_postlogin_connect=False
                    self.mesh_var_endpoint.set(self.mesh_active_relay)
                    if should_auto_connect(self.mesh_active,self.mesh_var_autoconnect.get(),
                                           self.mesh_var_mode.get(), self.mesh_active_relay):
                        self._mesh_log('[AUTO-CONNECT] Active relay '+self.mesh_active_relay)
                        self._mesh_connect()
                self.mesh_rooms=ev.get('rooms',self.mesh_rooms)
                self.mesh_room_counts=ev.get('room_counts',self.mesh_room_counts)
                self.mesh_files=ev.get('files',self.mesh_files)
                self.mesh_saved=ev.get('saved',self.mesh_saved)
                if 'nodes' in ev and ev.get('nodes'): self.mesh_nodes=ev['nodes']
                if ev.get('room'):self.mesh_var_room.set(ev['room'])
                if 'identity' in ev and not ev['identity']:
                    self.mesh_active=False
                    self.mesh_var_current_user.set('Local chat identity: not signed in')
                remote_count=len(remote_user_rows(self.mesh_users))
                self.mesh_var_roster_summary.set(
                    ('REMOTE ONLINE: '+str(remote_count)+' · '+str(len(self.mesh_peers))+' authenticated links · auto-updates every 2s')
                    if self.mesh_connected else 'REMOTE ONLINE: 0 · NOT CONNECTED — connect to AWS or another host')
                if 'connected' in ev:
                    self.mesh_var_status.set(
                        ('CONNECTED — '+str(len(self.mesh_peers))+' encrypted peer links · '
                         +str(remote_count)+' remote online') if ev['connected']
                        else ('LOCAL ONLY — click Connect to join other users' if self.mesh_active else 'DISCONNECTED'))
                self._mesh_target_label()
                self._mesh_update_lists()
            elif kind=='scan_public':
                self.mesh_nodes=ev.get('rows',[])
                self._mesh_update_lists()
                self._mesh_log('[DIRECTORY] '+str(len(self.mesh_nodes))+' signed node listing(s); not guaranteed reachable.')
                for err in ev.get('errors',[]):self._mesh_log('[DISCOVERY] '+str(err))
            elif kind=='scan_lan':
                self.mesh_lan=ev.get('rows',[])
                self._mesh_update_lists()
                self._mesh_log('[LAN] Found '+str(len(self.mesh_lan))+' opted-in discovery peers')
            elif kind=='history':
                self._mesh_log('[HISTORY] '+str(ev.get('room',''))+' — '+str(len(ev.get('lines',[])))+' saved messages')
                for line in ev.get('lines',[]):self._mesh_log('  '+str(line))
            elif kind=='download':
                self._mesh_log('[SAVED] '+str(ev.get('path','')))
                self._mesh_send('refresh_files')
                if (getattr(self,'mesh_tabs',None) and self.mesh_tabs.winfo_exists()
                        and getattr(self,'mesh_tab_saved',None) and self.mesh_tab_saved.winfo_exists()):
                    self.mesh_tabs.select(self.mesh_tab_saved)
        if self.root.winfo_exists(): self.root.after(100,self._mesh_pump)

    def _mesh_update_lists(self):
        room_rows=[{'room':name,'users':count} for name,count in sorted(self.mesh_room_counts.items())]
        specs=(('links',self.mesh_peers,('name','endpoint','id')),
               ('relays',self.mesh_relays,('label','endpoint','state','active')),
               ('rooms',room_rows,('room','users')),
               ('users',remote_user_rows(self.mesh_users),('nick','id','rooms')),
               ('public',self.mesh_nodes,('nick','endpoint','id')),
               ('lan',self.mesh_lan,('nick','endpoint','id')),
               ('files',self.mesh_files,('name','sender','size','status','id')),
               ('saved',self.mesh_saved,('name','size','path')))
        if (getattr(self,'mesh_tabs',None) and self.mesh_tabs.winfo_exists()
                and getattr(self,'mesh_tab_files',None) and self.mesh_tab_files.winfo_exists()):
            ready=sum(bool(o.get('ready')) for o in self.mesh_files)
            self.mesh_tabs.tab(self.mesh_tab_files,text=f'File Inbox ({ready} ready)')
        for suffix,rows,columns in specs:
            tree=getattr(self,'mesh_tree_'+suffix,None)
            if tree is None or not tree.winfo_exists():continue
            selected=tree.selection()
            old=tree.item(selected[0],'values') if selected else None
            for i in tree.get_children():tree.delete(i)
            for i,row in enumerate(rows):
                iid=f'{suffix}-{i}'
                tree.insert('','end',iid=iid,values=[str(row.get(c,''))[:100] for c in columns])
                if old and tuple(map(str,tree.item(iid,'values')))==tuple(old):tree.selection_set(iid)

    def _mesh_select(self,tree,items):
        selection=tree.selection() if tree and tree.winfo_exists() else []
        if not selection:return None
        try: idx=int(selection[0].split('-')[-1]);return items[idx]
        except (IndexError,ValueError):return None

    def _mesh_auth(self, register):
        if self.mesh_active:
            messagebox.showinfo('Already signed in','Disconnect before switching identities.',parent=self.root);return
        nick=self.mesh_var_nick.get().strip()
        if not nick:
            messagebox.showwarning('Account','Enter a chat username.',parent=self.root);return
        password=simpledialog.askstring('VaultForge chat account',f'Chat password for {nick} (not wallet password):',show='●',parent=self.root)
        if password is None:return
        if register:
            confirm=simpledialog.askstring('Confirm chat password','Repeat the same chat password:',show='●',parent=self.root)
            if confirm != password:
                messagebox.showerror('Account','Passwords do not match.',parent=self.root);return
        mode=self.mesh_var_mode.get()
        offline=mode=='Offline LAN';tor=mode=='Tor required'
        listen=self.mesh_var_listen.get().strip() or '127.0.0.1:0'
        if mode=='Offline LAN' and listen=='127.0.0.1:0':
            listen='0.0.0.0:7777'
        self._mesh_send('register' if register else 'login',nick=nick,password=password,
                        offline=offline,tor=tor,lan=offline,listen=listen)
        # No GUI variable holds a copy of the entered secret after this method returns.
        password=None

    def _mesh_change_password(self):
        nick=self.mesh_var_nick.get().strip()
        old=simpledialog.askstring('Chat account','Current chat password:',show='●',parent=self.root)
        if old is None:return
        new=simpledialog.askstring('Chat account','New chat password (14+ characters):',show='●',parent=self.root)
        if new is None:return
        confirm=simpledialog.askstring('Chat account','Repeat new chat password:',show='●',parent=self.root)
        if confirm!=new:messagebox.showerror('Mismatch','Passwords differ',parent=self.root);return
        self._mesh_send('change_password',nick=nick,old=old,new=new)

    def _mesh_choose_public(self):
        row=self._mesh_select(getattr(self,'mesh_tree_public',None),self.mesh_nodes)
        if row:
            self.mesh_expected_node=(row.get('endpoint',''),row.get('id',''))
            self.mesh_var_endpoint.set(row.get('endpoint',''))
            self._mesh_log('[DIRECTORY] Selected signed node '+str(row.get('nick',''))+'; identity must match after handshake.')

    def _mesh_join_selected_room(self):
        rows=[{'room':name,'users':count} for name,count in sorted(self.mesh_room_counts.items())]
        row=self._mesh_select(getattr(self,'mesh_tree_rooms',None),rows)
        if row:
            self.mesh_var_room.set(row['room'])
            self._mesh_join_room()

    def _mesh_public_scan(self):
        if self.mesh_var_mode.get()=='Offline LAN':
            messagebox.showinfo('Offline mode','Public node scanning requires internet. Use Scan LAN for offline peers.',parent=self.root)
            return
        self._mesh_send('scan_public',bootstrap=self.mesh_var_endpoint.get().strip(),tor=self.mesh_var_mode.get()=='Tor required')

    def _mesh_refresh_users(self):
        if not self.mesh_active:
            self._mesh_log('[ROSTER] Sign in first, then connect to AWS or another mesh peer.')
            return
        if not self.mesh_connected:
            if should_auto_connect(True, True, self.mesh_var_mode.get(), self.mesh_var_endpoint.get()):
                self._mesh_log('[ROSTER] Not connected. Retrying '+self.mesh_var_endpoint.get().strip()+' ...')
                self._mesh_connect()
            else:
                self._mesh_log('[ROSTER] No connected peers. A refresh cannot discover everyone worldwide without a reachable relay.')
            return
        now=time.monotonic()
        if now-self.mesh_last_roster_refresh < 4:
            self._mesh_log('[ROSTER] Refresh already requested. Signed presence may take a moment to propagate.')
            return
        self.mesh_last_roster_refresh=now
        self._mesh_log('[ROSTER] Requesting fresh signed presence from connected mesh peers ...')
        self._mesh_send('refresh_roster')

    def _mesh_request_relay_trust(self):
        if not self.mesh_active:
            messagebox.showinfo('Log in first',
                'Log in with your existing chat account before viewing or updating peer trust.', parent=self.root)
            return
        endpoint = self.mesh_var_endpoint.get().strip()
        if not endpoint:
            messagebox.showwarning('Relay address','Enter the relay HOST:PORT first.',parent=self.root)
            return
        self._mesh_send('peer_trust_status',endpoint=endpoint)

    def _mesh_verify_relay_trust(self, response):
        endpoint = str(response.get('endpoint',''))
        old = str(response.get('pinned',''))
        if endpoint != self.mesh_var_endpoint.get().strip():
            self._mesh_log('[TRUST] Endpoint changed; open Verify / Update Relay Trust again.')
            return
        if not old:
            messagebox.showinfo('No existing trust pin',
                endpoint+' has no saved trusted fingerprint for this local chat account. '
                'Use Connect, then independently verify the first-contact fingerprint with the server administrator.',
                parent=self.root)
            return
        import re
        detected = str(response.get('detected','')).strip().lower()
        if detected:
            if not re.fullmatch(r'[0-9a-f]{16}', detected):
                self._mesh_log('[SECURITY] Invalid fingerprint reported by remote peer; rejecting.')
                return
            prompt = ('SECURITY WARNING: the server identity CHANGED.\n\n'
                      'Endpoint: '+endpoint+'\nPreviously trusted: '+old+
                      '\nPresented by remote peer (UNTRUSTED): '+detected+
                      '\n\nVerify this value INDEPENDENTLY using the server console or administrator. '
                      'Do NOT trust this alert alone.\n'
                      'After verifying on your server console, click Yes to approve the displayed replacement.\n'
                      'No fingerprint typing required; Cancel keeps the old pin:')
        else:
            prompt = ('Saved identity for '+endpoint+':\n'+old+'\n\n'
                      'Only change this if you independently verified the server\'s NEW identity '
                      '(for example using its own SSH console).\n'
                      'Enter that full 16-character fingerprint (not the old one):')
        if detected:
            if not messagebox.askyesno('Verify detected server identity', prompt, parent=self.root):
                return
            verified = detected
        else:
            answer = simpledialog.askstring('Verified replacement fingerprint', prompt, parent=self.root)
            if answer is None:return
            verified = answer.strip().lower()
        import re
        if not re.fullmatch(r'[0-9a-f]{16}',verified):
            messagebox.showerror('Invalid fingerprint','Enter exactly 16 hexadecimal characters.',parent=self.root)
            return
        if verified == old:
            messagebox.showinfo('Already trusted','The fingerprint is unchanged.',parent=self.root)
            return
        if detected and verified != detected:
            messagebox.showerror('Fingerprint mismatch',
                'The independently verified value does not match the key presented by the server. '
                'Connection stays blocked and the old pin is unchanged.', parent=self.root)
            return
        if not messagebox.askyesno('Confirm independently verified key rotation',
                'Endpoint: '+endpoint+'\nPreviously trusted: '+old+'\nVerified replacement: '+verified+
                '\n\nThis replaces the saved trust pin for this endpoint only and leaves wallet/chat accounts intact. '
                'A backup of the previous pins will be saved locally.\n\n'
                'Did you verify '+verified+' independently on the actual server?', parent=self.root):
            return
        self._mesh_send('replace_peer_trust',endpoint=endpoint,previous_id=old,verified_id=verified)

    def _mesh_relay_selected(self):
        return self._mesh_select(getattr(self,'mesh_tree_relays',None),self.mesh_relays)

    def _mesh_add_relay(self):
        if not self.mesh_active:
            messagebox.showinfo('Sign in first','Log in to save your relay list.',parent=self.root);return
        endpoint=self.mesh_var_endpoint.get().strip()
        if not endpoint:
            messagebox.showwarning('Host','Enter HOST:PORT.',parent=self.root);return
        label=simpledialog.askstring('Save relay','Display name (optional):',parent=self.root)
        if label is None:return
        self._mesh_send('relay_add',endpoint=endpoint,label=label or endpoint)

    def _mesh_select_relay(self):
        row=self._mesh_relay_selected()
        if not row:return
        self.mesh_var_endpoint.set(row['endpoint'])
        if not self.mesh_active:return
        self._mesh_send('relay_select',endpoint=row['endpoint'])

    def _mesh_connect_relay(self):
        row=self._mesh_relay_selected()
        if not row:return
        self.mesh_var_endpoint.set(row['endpoint'])
        self._mesh_connect()

    def _mesh_remove_relay(self):
        row=self._mesh_relay_selected()
        if not row or not self.mesh_active:return
        if messagebox.askyesno('Remove saved host',
            'Remove '+row['endpoint']+' from the host menu?\nIdentity pins and files will be kept.',parent=self.root):
            self._mesh_send('relay_remove',endpoint=row['endpoint'])

    def _mesh_connect(self):
        if not self.mesh_active:
            messagebox.showinfo('Sign in first','Create or log in to a local chat identity.',parent=self.root);return
        endpoint=self.mesh_var_endpoint.get().strip()
        expected=self.mesh_expected_node[1] if self.mesh_expected_node and self.mesh_expected_node[0]==endpoint else ''
        self._mesh_send('connect',endpoint=endpoint,expected_id=expected)

    def _mesh_target_label(self):
        target=self.mesh_var_recipient.get().strip()
        me=next((u for u in self.mesh_users if u.get('rooms')=='you'),None)
        if target and me and target in (me['id'],me['nick'],f"{me['nick']}@{me['id']}"):
            self.mesh_var_recipient.set('');target=''
        display=(f'DM → {target}' if target else f'ROOM → {self.mesh_var_room.get().strip() or "#general"}')
        self.mesh_var_target.set('TARGET: '+display + (' · CONNECTED MESH' if self.mesh_connected else ' · LOCAL ONLY'))

    def _mesh_room_mode(self):
        self.mesh_var_recipient.set('')
        self._mesh_target_label()
        input_widget=getattr(self,'mesh_input_widget',None)
        if input_widget and input_widget.winfo_exists():input_widget.focus_set()

    def _mesh_choose_user(self):
        row=self._mesh_select(getattr(self,'mesh_tree_users',None),remote_user_rows(self.mesh_users))
        if not row:return
        if row.get('rooms')=='you':
            self._mesh_room_mode()
            self._mesh_log('[TARGET] Cannot DM yourself. Room target restored.')
            return
        self.mesh_var_recipient.set(row['id'])
        self._mesh_target_label()

    def _mesh_join_room(self):
        room=self.mesh_var_room.get().strip().lower()
        self._mesh_room_mode()
        self._mesh_send('join',room=room)

    def _mesh_message(self):
        text=self.mesh_var_text.get().strip()
        if not text:return
        if len(text)>1500:
            messagebox.showwarning('Too long','Maximum message is 1500 characters',parent=self.root);return
        target=self.mesh_var_recipient.get().strip()
        if target and not self.mesh_connected:
            self._mesh_log('[NOT CONNECTED] Connect to AWS or another peer before sending a DM.')
            return
        if target:
            online=[u for u in self.mesh_users if u.get('rooms')!='you']
            if not any(target in (u.get('nick'),u.get('id'),f"{u.get('nick')}@{u.get('id')}") for u in online):
                self._mesh_log('[DM NOT SENT] That person is not in the reachable online roster. Select them in Online Users and click Message Selected.')
                return
        self._mesh_send('dm' if target else 'chat',**({'recipient':target,'text':text} if target else {'text':text}))
        self.mesh_var_text.set('')
        input_widget=getattr(self,'mesh_input_widget',None)
        if input_widget and input_widget.winfo_exists():input_widget.focus_set()

    def _mesh_upload(self, folder=False):
        if not self.mesh_active:
            messagebox.showinfo('Sign in','Create or log into a chat identity first.',parent=self.root);return
        if not self.mesh_connected:
            messagebox.showinfo('Connect first','Connect to AWS or another peer to send files.',parent=self.root);return
        target=self.mesh_var_recipient.get().strip()
        # Explicit target selection: blank recipient means current room, not self.
        if target:
            users={u.get('id') for u in self.mesh_users if u.get('rooms')!='you'}
            if target not in users and not any(target in (u.get('nick'),f"{u.get('nick')}@{u.get('id')}") for u in self.mesh_users if u.get('rooms')!='you'):
                messagebox.showwarning('Not online','Recipient must appear under Online Users; choose Message Selected.',parent=self.root);return
        else:
            room=self.mesh_var_room.get().strip().lower()
            count=sum(1 for u in self.mesh_users if room in u.get('rooms','').split(',') and u.get('rooms')!='you')
            if count==0:
                messagebox.showinfo('Room empty','No other reachable online members of '+room+'.',parent=self.root);return
            if not messagebox.askyesno('Share to room',f'Offer separately encrypted files to {count} online members of {room}? Each recipient must accept.',parent=self.root):return
        path=filedialog.askdirectory(parent=self.root,title='Select folder to send') if folder else filedialog.askopenfilename(parent=self.root,title='Select image or file to send')
        if path:
            if target:self._mesh_send('upload',recipient=target,path=path)
            else:self._mesh_send('upload_room',room=self.mesh_var_room.get().strip().lower(),path=path)

    def _mesh_files(self,accept):
        row=self._mesh_select(getattr(self,'mesh_tree_files',None),self.mesh_files)
        if not row:
            messagebox.showinfo('Incoming transfers','Select a pending file offer.',parent=self.root);return
        if accept and not row.get('ready'):
            messagebox.showwarning('Still receiving','Wait until the file is ready.',parent=self.root);return
        if accept and not messagebox.askyesno('Accept file','Save '+str(row['name'])+' to your VaultForge downloads folder? Only open trusted files.',parent=self.root):return
        self._mesh_send('accept' if accept else 'reject',id=row['id'])

    def _mesh_file_inbox(self):
        """One-click access to incoming offers; does not auto-accept content."""
        tabs=getattr(self,'mesh_tabs',None)
        tab=getattr(self,'mesh_tab_files',None)
        if tabs is not None and tab is not None and tabs.winfo_exists():
            tabs.select(tab)
        self._mesh_send('refresh_files')

    def _mesh_downloads_folder(self):
        # Worker and desktop use the same user-owned VaultForge folder.
        base=Path.home()/'VaultForge'/'mesh_chat'/'downloads'
        if base.is_symlink():
            messagebox.showerror('Unsafe download folder','Downloads folder is a symlink.',parent=self.root)
            return
        if not base.is_dir():
            messagebox.showinfo('No downloads yet','Accept a received file to create the downloads folder.',parent=self.root)
            return
        try:
            if os.name=='nt':
                os.startfile(str(base))
            elif sys.platform=='darwin':
                subprocess.Popen(['open',str(base)])
            else:
                subprocess.Popen(['xdg-open',str(base)])
        except (OSError,ValueError) as exc:
            messagebox.showinfo('Downloads folder',str(base)+'\n\nCould not open folder: '+type(exc).__name__,parent=self.root)

    def _mesh_preview_saved(self):
        """Preview ONLY explicitly accepted local image/ZIP files; never auto-run attachments."""
        row=self._mesh_select(getattr(self,'mesh_tree_saved',None),self.mesh_saved)
        if not row:
            messagebox.showinfo('Saved files','Select a downloaded file in the Downloaded tab.',parent=self.root)
            return
        base=Path.home()/'VaultForge'/'mesh_chat'/'downloads'
        path=Path(str(row.get('path','')))
        if base.is_symlink() or path.is_symlink() or path.parent!=base or not path.is_file():
            messagebox.showerror('Unsafe file','Cannot preview outside your private downloads folder.',parent=self.root)
            return
        if path.stat().st_size>8*1024*1024:
            messagebox.showwarning('Large file','Preview limited to files up to 8 MiB.',parent=self.root)
            return
        ext=path.suffix.lower()
        if ext not in ('.png','.gif','.jpg','.jpeg','.webp','.bmp','.zip','.txt','.md','.csv','.json','.log'):
            messagebox.showinfo('File downloaded',f'Saved to:\n{path}\n\nImages, ZIP listings and text documents can be previewed here. Other files are never executed.',parent=self.root)
            return
        win=tk.Toplevel(self.root)
        win.title('VaultForge preview — '+path.name)
        win.configure(bg=BG)
        win.geometry('900x650')
        ttk.Label(win,text=path.name).pack(pady=8)
        if ext=='.zip' or ext in ('.txt','.md','.csv','.json','.log'):
            box=tk.Text(win,bg=DARK,fg=TEXT,wrap='none')
            box.pack(fill='both',expand=True,padx=12,pady=10)
            if ext=='.zip':
                try:
                    with zipfile.ZipFile(path) as z:
                        entries=z.infolist()
                        box.insert('end',f'{len(entries)} archive entries — inspection only; no extraction\n\n')
                        for entry in entries[:150]:
                            box.insert('end',f'{entry.filename[:180]}   ({entry.file_size} bytes)\n')
                        if len(entries)>150: box.insert('end','... additional entries omitted')
                except (OSError,zipfile.BadZipFile,ValueError):
                    box.insert('end','Invalid or unreadable ZIP archive.')
            else:
                try:
                    with path.open('rb') as stream:
                        raw=stream.read(256*1024+1)
                    box.insert('end',raw[:256*1024].decode('utf-8',errors='replace'))
                    if len(raw)>256*1024:box.insert('end','\n\n... preview capped at 256 KiB')
                except OSError:
                    box.insert('end','Unable to read this text document.')
            box.configure(state='disabled')
        else:
            try:
                from PIL import Image, ImageTk, UnidentifiedImageError
                Image.MAX_IMAGE_PIXELS=12_000_000
                with Image.open(path) as im:
                    im.thumbnail((860,570))
                    pic=ImageTk.PhotoImage(im.copy(),master=win)
            except ImportError:
                try:
                    pic=tk.PhotoImage(file=str(path),master=win)  # Tk supports PNG/GIF
                except tk.TclError:
                    win.destroy()
                    messagebox.showinfo('Image preview','JPEG/WebP previews require Pillow in your GUI Python environment.',parent=self.root)
                    return
            except Exception as exc:
                win.destroy()
                messagebox.showerror('Image preview','Cannot safely preview image: '+type(exc).__name__,parent=self.root)
                return
            label=tk.Label(win,image=pic,bg=BG)
            label.image=pic  # Keep reference while preview window exists.
            label.pack(fill='both',expand=True)
        ttk.Button(win,text='Close Preview',command=win.destroy).pack(pady=8)

    def _mesh_node_action(self,action):
        name=self.mesh_var_node_name.get().strip()
        listen=self.mesh_var_node_listen.get().strip()
        advertised=self.mesh_var_node_endpoint.get().strip()
        mode={'WAN / AWS':'wan','Offline LAN':'lan','Tor required':'tor'}[self.mesh_var_mode.get()]
        args={'setup':['setup','--mode',mode,'--name',name,'--listen',listen],
              'start':['start'],'stop':['stop'],'status':['status'],'autostart':['autostart']}.get(action)
        if args is None:return
        if action=='setup':
            if mode=='wan':
                if not messagebox.askyesno('Internet exposure','Host an experimental, unaudited public relay? Restrict firewall access while testing.',parent=self.root):return
                args.append('--yes')
                if advertised:args.extend(['--advertise',advertised])
                bootstrap=self.mesh_var_endpoint.get().strip()
                if bootstrap and bootstrap!=advertised:
                    args.extend(['--peer',bootstrap])
        def run():
            try:
                cp=subprocess.run(node_command(args),cwd=str(Path(__file__).resolve().parent),
                                  capture_output=True,text=True,timeout=25,stdin=subprocess.DEVNULL)
                reply=(cp.stdout or cp.stderr or 'Node command finished').strip()
                ev={'kind':'log' if cp.returncode==0 else 'error','text':reply[:2500]}
            except (OSError,subprocess.TimeoutExpired) as exc:
                ev={'kind':'error','text':'Node command: '+type(exc).__name__}
            try:self.mesh_pipe_events.put_nowait(ev)
            except queue.Full:pass
        threading.Thread(target=run,daemon=True,name='NocturneNodeAction').start()
        if not self.mesh_event_polling:
            self.mesh_event_polling=True
            self.root.after(100,self._mesh_pump)

    def page_internet_chat(self):
        # The old bespoke WAN protocol cannot interoperate with the deployed AWS mesh relay.
        # Route both Internet Chat and Mesh Network through the same compatible engine.
        self.page_mesh_network()

    def page_mesh_network(self):
        self.head('VaultForge mesh communications','CLI-compatible encrypted mesh · AWS bootstrap · signed public discovery · offline LAN · Tor · file & folder exchange')
        self._mesh_start_worker()
        outer=tk.Frame(self.content,bg=BG);outer.pack(fill='both',expand=True)
        top=tk.Frame(outer,bg=DARK,highlightbackground=BORDER,highlightthickness=1,padx=10,pady=10)
        top.pack(fill='x',pady=4)
        tk.Label(top,textvariable=self.mesh_var_status,fg=GREEN,bg=DARK,font=('Consolas',10,'bold')).pack(anchor='w')
        tk.Label(top,textvariable=self.mesh_var_current_user,fg=GRAY,bg=DARK,font=('Consolas',8)).pack(anchor='w')
        acct=tk.Frame(top,bg=DARK);acct.pack(fill='x',pady=5)
        tk.Label(acct,text='Account',fg=TEXT,bg=DARK).pack(side='left')
        ttk.Entry(acct,textvariable=self.mesh_var_nick,width=19).pack(side='left',padx=5)
        for title,fn in [('Register',lambda:self._mesh_auth(True)),('Log In',lambda:self._mesh_auth(False)),('Password',self._mesh_change_password),('Disconnect',lambda:self._mesh_send('disconnect'))]:
            ttk.Button(acct,text=title,command=fn).pack(side='left',padx=3)
        con=tk.Frame(top,bg=DARK);con.pack(fill='x',pady=4)
        tk.Label(con,text='Network mode',bg=DARK,fg=GRAY).pack(side='left')
        ttk.Combobox(con,textvariable=self.mesh_var_mode,values=['WAN / AWS','Offline LAN','Tor required'],state='readonly',width=15).pack(side='left',padx=5)
        tk.Label(con,text='Local listener',bg=DARK,fg=GRAY).pack(side='left',padx=3)
        ttk.Entry(con,textvariable=self.mesh_var_listen,width=22).pack(side='left',padx=4)
        endpoint=tk.Frame(top,bg=DARK);endpoint.pack(fill='x',pady=4)
        tk.Label(endpoint,text='Peer / bootstrap',bg=DARK,fg=GRAY).pack(side='left')
        ttk.Entry(endpoint,textvariable=self.mesh_var_endpoint,width=30).pack(side='left',padx=6)
        ttk.Button(endpoint,text='Connect',command=self._mesh_connect).pack(side='left',padx=3)
        ttk.Button(endpoint,text='Save Host',command=self._mesh_add_relay).pack(side='left',padx=3)
        # Trust management is separate from chat text: /unpin typed as a message
        # must never silently edit the local pin registry.
        trust_row=tk.Frame(top,bg=DARK);trust_row.pack(fill='x',pady=(1,2))
        ttk.Button(trust_row,text='Verify / Update Relay Trust',
                   command=self._mesh_request_relay_trust).pack(side='left',padx=3)
        tk.Label(trust_row,text='Use after an independently verified server identity change',
                 bg=DARK,fg=GRAY).pack(side='left',padx=4)
        ttk.Checkbutton(endpoint,text='Auto-connect on login',variable=self.mesh_var_autoconnect).pack(side='left',padx=3)
        ttk.Button(endpoint,text='Scan Public Nodes',command=self._mesh_public_scan).pack(side='left',padx=3)
        ttk.Button(endpoint,text='Scan LAN',command=lambda:self._mesh_send('scan_lan')).pack(side='left',padx=3)
        tabs=ttk.Notebook(outer);tabs.pack(fill='x',pady=6)
        self.mesh_tabs=tabs
        def make_table(label,suffix,columns,widths):
            tab=tk.Frame(tabs,bg=DARK,padx=5,pady=5);tabs.add(tab,text=label)
            tree=ttk.Treeview(tab,columns=columns,show='headings',height=5,selectmode='browse')
            for col,w in zip(columns,widths):tree.heading(col,text=col.title());tree.column(col,width=w,anchor='w')
            tree.pack(fill='x',expand=True)
            setattr(self,'mesh_tree_'+suffix,tree)
            return tab,tree
        relay_tab,relay_tree=make_table('Saved Relays / Live Hosts','relays',
                                         ('label','endpoint','state','active'),(180,200,135,65))
        relay_buttons=tk.Frame(relay_tab,bg=DARK);relay_buttons.pack(fill='x')
        for caption,callback in [('Save Typed Host',self._mesh_add_relay),
                                 ('Use as Active',self._mesh_select_relay),
                                 ('Connect Selected',self._mesh_connect_relay),
                                 ('Remove Host',self._mesh_remove_relay)]:
            ttk.Button(relay_buttons,text=caption,command=callback).pack(side='left',padx=3)
        live_tab,live_tree=make_table('Live Connections','links',
                                       ('name','endpoint','id'),(170,210,310))
        tk.Label(live_tab,text='Authenticated encrypted connections; updates automatically every 2 seconds',
                 bg=DARK,fg=GREEN).pack(anchor='w')
        rooms,room_tree=make_table('Live Rooms','rooms',('room','users'),(300,100))
        ttk.Button(rooms,text='Join Selected Room',command=self._mesh_join_selected_room).pack(anchor='e')
        users,us_tree=make_table('Online Users (remote peers)','users',('nick','id','rooms'),(140,360,140))
        user_tools=tk.Frame(users,bg=DARK);user_tools.pack(fill='x',pady=3)
        tk.Label(user_tools,textvariable=self.mesh_var_roster_summary,bg=DARK,fg=GREEN).pack(side='left',padx=4)
        ttk.Button(user_tools,text='Refresh Online',command=self._mesh_refresh_users).pack(side='right',padx=3)
        ttk.Button(user_tools,text='Message Selected',command=self._mesh_choose_user).pack(side='right',padx=3)
        public,pub_tree=make_table('Public Nodes','public',('nick','endpoint','id'),(150,200,360))
        ttk.Button(public,text='Use Selected Node',command=self._mesh_choose_public).pack(anchor='e')
        lan,lan_tree=make_table('Local Network','lan',('nick','endpoint','id'),(150,220,360))
        ttk.Button(lan,text='Use LAN Peer',command=lambda:self.mesh_var_endpoint.set((self._mesh_select(lan_tree,self.mesh_lan) or {}).get('endpoint',''))).pack(anchor='e')
        files,file_tree=make_table('File Inbox','files',('name','sender','size','status','id'),(180,200,80,100,150))
        self.mesh_tab_files=files
        ff=tk.Frame(files,bg=DARK);ff.pack(anchor='e')
        ttk.Button(ff,text='Refresh Inbox',command=lambda:self._mesh_send('refresh_files')).pack(side='left',padx=3)
        ttk.Button(ff,text='Download Selected',command=lambda:self._mesh_files(True)).pack(side='left',padx=3)
        ttk.Button(ff,text='Reject',command=lambda:self._mesh_files(False)).pack(side='left',padx=3)
        saved,saved_tree=make_table('Downloaded Files','saved',('name','size','path'),(230,90,400))
        self.mesh_tab_saved=saved
        sf=tk.Frame(saved,bg=DARK);sf.pack(anchor='e')
        ttk.Button(sf,text='Preview Image / Text / ZIP',command=self._mesh_preview_saved).pack(side='left',padx=3)
        ttk.Button(sf,text='Open Downloads Folder',command=self._mesh_downloads_folder).pack(side='left',padx=3)
        ttk.Button(sf,text='Refresh',command=lambda:self._mesh_send('refresh_files')).pack(side='left',padx=3)
        middle=tk.Frame(outer,bg=DARK,padx=9,pady=8)
        middle.pack(fill='x')
        tk.Label(middle,text='Room',bg=DARK,fg=GRAY).pack(side='left')
        ttk.Entry(middle,textvariable=self.mesh_var_room,width=22).pack(side='left',padx=4)
        ttk.Button(middle,text='Create / Join Room',command=self._mesh_join_room).pack(side='left',padx=3)
        ttk.Button(middle,text='Recent History',command=lambda:self._mesh_send('history',room=self.mesh_var_room.get())).pack(side='left',padx=3)
        ttk.Button(middle,text='Upload File / Image',command=self._mesh_upload).pack(side='left',padx=3)
        ttk.Button(middle,text='Share Folder (ZIP)',command=lambda:self._mesh_upload(True)).pack(side='left',padx=3)
        ttk.Button(middle,text='Receive / Download Files',command=self._mesh_file_inbox).pack(side='left',padx=3)
        chat=tk.Frame(outer,bg=DARK,padx=8,pady=8)
        chat.pack(fill='both',expand=True)
        tk.Label(chat,text='LIVE CHAT / CHANNEL HISTORY',bg=DARK,fg=GREEN,font=('Consolas',10,'bold')).pack(anchor='w')
        self.mesh_log_box=tk.Text(chat,bg='#0c0914',fg=TEXT,insertbackground=GREEN,wrap='word',
                                  height=13,relief='flat',font=('Consolas',10),state='normal')
        self.mesh_log_box.pack(fill='both',expand=True,pady=4)
        for line in self.mesh_log_lines[-350:]:self.mesh_log_box.insert('end',line+'\n')
        self.mesh_log_box.see('end');self.mesh_log_box.configure(state='disabled')
        send=tk.Frame(chat,bg=DARK);send.pack(fill='x',pady=5)
        tk.Label(send,textvariable=self.mesh_var_target,bg=DARK,fg=GREEN).pack(side='left')
        ttk.Button(send,text='Send to Room',command=self._mesh_room_mode).pack(side='left',padx=5)
        tk.Label(send,text='DM ID',bg=DARK,fg=GRAY).pack(side='left')
        recipient_input=ttk.Entry(send,textvariable=self.mesh_var_recipient,width=24)
        recipient_input.pack(side='left',padx=5)
        recipient_input.bind('<FocusOut>',lambda e:self._mesh_target_label())
        send2=tk.Frame(chat,bg=DARK);send2.pack(fill='x')
        self.mesh_input_widget=ttk.Entry(send2,textvariable=self.mesh_var_text)
        self.mesh_input_widget.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.mesh_input_widget.bind('<Return>',lambda e:(self._mesh_message(),'break')[1])
        ttk.Button(send2,text='Send',command=self._mesh_message).pack(side='left')
        nodes=tk.LabelFrame(outer,text='OPTIONAL BACKGROUND NODE — not required for chatting',bg=DARK,fg=GREEN,padx=6,pady=6)
        nodes.pack(fill='x',pady=7)
        row=tk.Frame(nodes,bg=DARK);row.pack(fill='x')
        for label,var,width in [('Node name',self.mesh_var_node_name,15),('Listen',self.mesh_var_node_listen,19),('Public advertise (optional)',self.mesh_var_node_endpoint,22)]:
            tk.Label(row,text=label,bg=DARK,fg=GRAY).pack(side='left',padx=3)
            ttk.Entry(row,textvariable=var,width=width).pack(side='left',padx=3)
        row2=tk.Frame(nodes,bg=DARK);row2.pack(fill='x',pady=4)
        for label,act in [('Configure Node','setup'),('Start in Background','start'),('Stop','stop'),('Status','status'),('Autostart','autostart')]:
            ttk.Button(row2,text=label,command=lambda a=act:self._mesh_node_action(a)).pack(side='left',padx=3)
        tk.Label(outer,text='Experimental unaudited mesh, not standard IRC. Public rooms/history are readable by relays; private DMs and files use recipient encryption. Public nodes are signed listings, not trust proofs.',bg=BG,fg=GRAY,wraplength=1100,justify='left').pack(anchor='w',pady=4)
        self._mesh_target_label()
        self._mesh_update_lists()

    def mesh_stop(self):
        p=getattr(self,'mesh_proc',None)
        if p is None:return
        try:
            if p.poll() is None:
                p.stdin.write('{"action":"shutdown"}\n');p.stdin.flush()
                p.wait(timeout=1.5)
        except (OSError,subprocess.TimeoutExpired):
            try:p.terminate()
            except OSError:pass
        self.mesh_proc=None
