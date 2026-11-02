"""Tkinter peer-to-peer tab. No key exchange with payment signing keys.
Only approved peer identity and public payment-request data crosses the network.
"""
from __future__ import annotations
import queue
import threading
import os
import socket
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from core.peer_network import Identity, PeerHub, PROVIDERS, validate_request
from core.tor_controller import TorController
from performance_runtime import QueueSaturated


class PeerUI:
    def init_peer(self):
        self.peer_hub = None
        self.peer_identity = None
        self.peer_events = queue.Queue(maxsize=4096)
        self.peer_log = []
        self.mesh_enabled=tk.BooleanVar(value=False)
        self.mesh_target=tk.StringVar(value='')
        self.mesh_text=tk.StringVar(value='')
        self.mesh_status=tk.StringVar(value='Mesh disabled')
        self.tor_only=tk.BooleanVar(value=False)
        self.tor_status=tk.StringVar(value='Tor: OFF • only P2P traffic can use Tor')
        self.tor_binary=tk.StringVar(value='')
        self.tor_onion=tk.StringVar(value='No onion service running')
        self.tor_controller=TorController(self._peer_folder()/'tor',self._peer_event)
        self.peer_fp_var = tk.StringVar(value='Identity locked — no peer networking started')
        self.peer_bind = tk.StringVar(value='Private loopback (Tor/on this computer)')
        self.peer_port = tk.StringVar(value='19420')
        self.peer_target = tk.StringVar(value='127.0.0.1')
        self.peer_target_port = tk.StringVar(value='19420')
        self.peer_expected = tk.StringVar(value='')
        self.peer_transport = tk.StringVar(value='Direct TCP (LAN / configured router)')
        self.peer_proxy_host = tk.StringVar(value='127.0.0.1')
        self.peer_proxy_port = tk.StringVar(value='9050')
        self.peer_choice = tk.StringVar(value='')
        self.peer_method = tk.StringVar(value='Bitcoin')
        self.peer_currency = tk.StringVar(value='BTC')
        self.peer_amount = tk.StringVar(value='0.001')
        self.peer_network = tk.StringVar(value='Bitcoin mainnet')
        self.peer_destination = tk.StringVar(value='')
        self.peer_wallet_choice = tk.StringVar(value='Manual entry')
        self.peer_public_options = {}
        self.peer_memo = tk.StringVar(value='')
        self.peer_note = tk.StringVar(value='')
        self.peer_status = tk.StringVar(value='Offline • no connected peers')
        self.root.after(250,self.peer_poll)

    def _peer_folder(self):
        # Never place the peer identity on user-selected USB wallet volume.
        return Path.home()/'.crypto_creating_wallets'/'p2p'

    def _peer_event(self,evt):
        # Fail under overload instead of growing without bound and exhausting RAM.
        self.peer_events.put(evt,timeout=1)

    def _peer_allow(self, fingerprint):
        reply=threading.Event();result={'yes':False}
        def request():
            try:
                result['yes']=messagebox.askyesno(
                    'Incoming CRYPTO peer • verify identity',
                    'A device requests a private encrypted connection.\n\n'
                    'Fingerprint:\n'+fingerprint+'\n\n'
                    'Compare ALL 64 digits with the other person using an '
                    'independent trusted channel (voice, in person, etc.).\n\n'
                    'Accept ONLY if you confirmed the full fingerprint. '
                    'This does NOT authorize payments.',parent=self.root)
            finally:reply.set()
        try:self.peer_events.put({'event':'approve', 'handler':request},timeout=1)
        except queue.Full:return False
        if not reply.wait(85): return False
        return result['yes']

    def peer_poll(self):
        try:
            for _ in range(30):
                try: e=self.peer_events.get_nowait()
                except queue.Empty:break
                if e['event']=='approve':
                    e['handler']()
                elif e['event']=='discovered':
                    pass
                elif e['event']=='online':
                    self.peer_log.append('ONLINE • '+e['fingerprint'])
                elif e['event']=='offline':
                    self.peer_log.append('OFFLINE • '+e['fingerprint'])
                elif e['event']=='message':
                    fp=e['fingerprint']
                    v=e['data']
                    if v['type']=='payment_request':
                        self.peer_log.append('PAYMENT REQUEST (NOT PAID)\n'
                                             'Peer: '+fp+'\n'+v['method']+' • '+v['amount']+' '+v['currency']+
                                             ' • network '+v['network']+'\nReceiver: '+v['destination']+
                                             '\nReference: '+v['request_id']+'\n'+v['memo'])
                    elif v['type']=='message':
                        self.peer_log.append('MESSAGE '+fp[:16]+': '+v['text'])
                elif e['event']=='listening':
                    self.peer_port.set(str(e['port']))
                    self.peer_log.append('Listening • '+e['host']+':'+str(e['port']))
                elif e['event']=='tor_status':
                    self.tor_status.set('Tor: '+e['status']+' • '+e.get('detail',''))
                    if self.tor_only.get() and e['status'] in ('STOPPED','ERROR','OFF') and self.peer_hub:
                        self.peer_hub.fail_closed()
                        self.tor_onion.set('Tor unavailable: peers disconnected, direct fallback blocked')
                    if e['status']=='READY':
                        self.tor_onion.set(self.tor_controller.onion_address() or 'Tor ready; onion service initializing')
                elif e['event']=='mesh_presence':
                    self.peer_log.append('MESH DISCOVERED • '+e['nick']+' / '+e['fingerprint'][:16]+'…')
                elif e['event']=='mesh_message':
                    self.peer_log.append('MESH MESSAGE (E2E) '+e['fingerprint'][:16]+': '+e['text'])
                elif e['event']=='mesh_delivered':
                    self.peer_log.append('MESH DELIVERED TO ENDPOINT • '+e['packet_id']+' (not read or payment proof)')
                elif e['event']=='listener_stopped':
                    self.peer_log.append('Listener stopped')
                elif e['event']=='error':
                    self.peer_log.append('Connection rejected • '+e.get('detail','error'))
                elif e['event']=='connected_client':
                    self.peer_log.append('Peer verified • '+e['fingerprint'])
                elif e['event']=='local_message':
                    self.peer_log.append(e['text'])
                elif e['event']=='ui_error':
                    self.peer_log.append('ERROR • '+e['detail'])
                self._chat_peer_event(e)
            self.peer_log = self.peer_log[-250:]
            if self.peer_hub:
                peers=self.peer_hub.peers()
                self.peer_status.set(f'{len(peers)} online peer(s) • authenticated + encrypted')
                cb=getattr(self,'peer_combo',None)
                if cb and cb.winfo_exists():
                    old=self.peer_choice.get()
                    cb['values']=peers
                    if old not in peers:self.peer_choice.set(peers[0] if peers else '')
                if self.peer_hub.mesh.enabled:
                    discovered=self.peer_hub.mesh.online()
                    self.mesh_status.set(f'{len(discovered)} signed remote mesh identities • {len(peers)} direct links')
                    combo=getattr(self,'mesh_target_combo',None)
                    if combo and combo.winfo_exists():
                        combo['values']=[fp for fp,_ in discovered]
                else:self.mesh_status.set('Mesh disabled')
            else:self.peer_status.set('Offline • identity locked')
            if self.tor_only.get() and self.tor_controller.bootstrapped:
                onion=self.tor_controller.onion_address()
                if onion:self.tor_onion.set(onion+':'+str(self.peer_port.get()))
            self._chat_refresh_view()
            view=getattr(self,'peer_log_view',None)
            if view and view.winfo_exists():
                latest='\n\n'.join(self.peer_log[-32:])
                if str(view.get('1.0','end-1c')) != latest:
                    view.configure(state='normal'); view.delete('1.0','end')
                    view.insert('1.0',latest);view.configure(state='disabled')
        except (tk.TclError, RuntimeError):return
        try:self.root.after(350,self.peer_poll)
        except (tk.TclError, RuntimeError):pass

    def peer_unlock(self):
        filename=self._peer_folder()/'peer_identity.enc'
        create=not filename.exists()
        if create:
            if not messagebox.askyesno('New P2P identity',
                     'Create a new encrypted peer identity on this computer?\n\n'
                     'This identity is SEPARATE from all crypto wallet seeds. '
                     'It identifies your device to other CRYPTO users.'):
                return
        pw=simpledialog.askstring('P2P identity password',
                'Create identity — set a strong password (12+ characters)' if create else
                'Unlock your existing local peer identity',show='●',parent=self.root)
        if pw is None:return
        if create:
            verify=simpledialog.askstring('Confirm identity password','Repeat password',show='●',parent=self.root)
            if verify != pw:
                messagebox.showerror('Mismatch','Passwords do not match');return
        try:
            identity=Identity.open(self._peer_folder(),pw,create=create)
            self.tor_controller.stop()
            self.tor_only.set(False)
            self.chat_stop_discovery()
            self.wan_stop_connection()
            if self.peer_hub:self.peer_hub.close()
            self.peer_identity=identity
            self.peer_hub=PeerHub(identity,self._peer_event,self._peer_allow,nickname=self.chat_nickname.get())
            self.peer_hub.mesh.enable(self.mesh_enabled.get())
            self.peer_fp_var.set(identity.fingerprint)
            self.peer_log.append('P2P identity '+('created' if create else 'unlocked')+' (no wallet secrets used)')
            self.status.set('P2P unlocked • listening is OFF until you choose Start Listener')
        except Exception as e:
            messagebox.showerror('Cannot unlock P2P identity',type(e).__name__+': '+str(e)[:180])
        finally:
            pw=''
        if self.current_page=='Peer to Peer':self.show('Peer to Peer')

    def _copy_peer_fp(self):
        if not self.peer_identity:return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.peer_identity.fingerprint)
        self.peer_log.append('Copied public fingerprint (never wallet keys)')

    def peer_lock(self):
        self.tor_controller.stop()
        self.tor_only.set(False)
        self.wan_stop_connection()
        self.chat_stop_discovery()
        if self.peer_hub:self.peer_hub.close()
        self.peer_hub=None;self.peer_identity=None
        self.peer_fp_var.set('Identity locked — no peer networking started')
        self.peer_log.append('P2P locked; connections closed')
        self.peer_status.set('Offline')

    def peer_start_listener(self):
        if not self.peer_hub:
            messagebox.showwarning('Locked','Unlock a P2P identity first');return
        if self.tor_only.get():
            return messagebox.showinfo('Tor-only','An onion listener is managed by the Tor switch. Disable Tor-only before starting direct LAN listening.')
        bind='0.0.0.0' if self.peer_bind.get().startswith('LAN') else '127.0.0.1'
        if bind=='0.0.0.0' and not messagebox.askyesno('Expose on LAN',
                'This will listen on ALL local network interfaces. '
                'Only enable it on a network you trust. Continue?'):
            return
        try:self.peer_hub.listen(bind,int(self.peer_port.get()))
        except OSError as e:
            tip='Windows blocked this port. Try 0 for an automatic available port, or check firewall/port exclusions.' if getattr(e,'winerror',None)==10013 or getattr(e,'errno',None)==13 else str(e)
            messagebox.showerror('Listener failed',tip)
        except (ValueError,RuntimeError) as e:messagebox.showerror('Listener failed',str(e))

    def peer_stop_listener(self):
        if self.tor_only.get():
            self.tor_controller.stop()
            self.tor_only.set(False)
            self.tor_onion.set('No onion service running')
        self.chat_stop_discovery()
        if self.peer_hub:self.peer_hub.stop_listener()

    def peer_connect(self):
        if not self.peer_hub:
            messagebox.showwarning('Locked','Unlock your identity first');return
        via_tor=self.tor_only.get() or self.peer_transport.get().startswith('Tor')
        if self.tor_only.get() and not self.tor_controller.bootstrapped:
            return messagebox.showwarning('Tor starting','Tor must reach 100% bootstrap before connecting. Direct fallback is disabled.')
        target=self.peer_target.get().strip()
        expected=self.peer_expected.get().strip().lower()
        try:port=int(self.peer_target_port.get());proxyport=(self.tor_controller.socks_port if self.tor_only.get() else int(self.peer_proxy_port.get()))
        except ValueError:
            messagebox.showerror('Port','Port must be a number');return
        hub=self.peer_hub
        proxy_host=self.peer_proxy_host.get()  # Tk state read only on UI thread
        def background():
            return hub.connect(target,port,expected,via_tor,proxy_host,proxyport)
        try:self.executor.submit(background,
            lambda fp:self._peer_event({'event':'connected_client','fingerprint':fp}),
            lambda kind:self._peer_event({'event':'ui_error','detail':'Connection failed: '+kind}),
            key='peer-connect:'+target+':'+str(port))
        except (QueueSaturated,RuntimeError) as exc:
            messagebox.showwarning('Connection busy',str(exc))

    def _p2p_public_wallets(self):
        options={'Manual entry':None}
        for item in self.watch:
            code=str(item.get('coin','')).upper().strip()
            addr=str(item.get('address','')).strip()
            label=str(item.get('label','Watch-only')).strip()[:32]
            if code and addr:
                key=f'{label} • {code} • {addr[:21]}…'
                options[key]={'code':code,'address':addr,'network':str(item.get('network',code))}
        for path,entries in self.public_unlocked.items():
            for item in entries:
                code=str(item.get('coin','')).upper().strip()
                addr=str(item.get('address','')).strip()
                if code and addr:
                    key=f'{Path(path).stem[:24]} • {code} • {addr[:21]}…'
                    options[key]={'code':code,'address':addr,'network':str(item.get('network',code))}
        return options

    def _peer_choose_wallet(self, event=None):
        item=self.peer_public_options.get(self.peer_wallet_choice.get())
        if not item:return
        self.peer_destination.set(item['address'])
        self.peer_currency.set(item['code'])
        self.peer_network.set(item['network'])
        if item['code'] in ('BTC','XMR','ETH','USDT','USDC','SOL'):
            self.peer_method.set({'BTC':'Bitcoin','XMR':'Monero','ETH':'Ethereum',
                'SOL':'Solana','USDT':'USDT','USDC':'USDC'}[item['code']])

    def peer_send_request(self):
        if not self.peer_hub:return messagebox.showwarning('Locked','Unlock peer networking')
        fp=self.peer_choice.get()
        if fp not in self.peer_hub.peers():
            return messagebox.showwarning('Not connected','Select an ONLINE verified peer')
        try:
            obj=validate_request(self.peer_method.get(),self.peer_amount.get(),
                   self.peer_currency.get(),self.peer_destination.get(),
                   self.peer_network.get(),self.peer_memo.get())
        except Exception as e:return messagebox.showerror('Invalid request',str(e))
        if self.tor_only.get() and not self._tor_peer_ready(fp):
            return messagebox.showerror('Tor-only','Recipient must be connected through Tor; request blocked')
        if not messagebox.askyesno('Confirm REQUEST (not payment)',
            'Send an encrypted payment request to:\n'+fp+'\n\n'+
            obj['method']+' • '+obj['amount']+' '+obj['currency']+'\n'+
            obj['network']+'\nDestination: '+obj['destination']+'\n\n'
            'No funds will move. Do NOT send a seed, private key, card number or bank password.'):
            return
        try:
            self._peer_send_async(fp,obj,'REQUEST SENT • '+obj['request_id']+'\n'+
                 obj['amount']+' '+obj['currency']+' via '+obj['method']+' • NOT PAID')
        except Exception as e:messagebox.showerror('Send failed',str(e))

    def peer_send_note(self):
        if not self.peer_hub:return
        fp=self.peer_choice.get()
        note=self.peer_note.get().strip()
        if not 1<=len(note)<=500:return messagebox.showwarning('Message','Enter 1–500 characters')
        if fp not in self.peer_hub.peers():return messagebox.showwarning('Offline','Choose connected peer')
        try:
            if self.tor_only.get() and not self._tor_peer_ready(fp):
                return messagebox.showerror('Tor-only','Peer must be connected through Tor while Tor-only mode is enabled')
            self._peer_send_async(fp,{'type':'message','text':note},'YOU → '+fp[:16]+': '+note)
            self.peer_note.set('')
        except Exception as e:messagebox.showerror('Send failed',str(e))

    def _peer_send_async(self,fp,obj,success_msg):
        hub=self.peer_hub
        def background():return hub.send(fp,obj)
        try:self.executor.submit(background,
            lambda _result:self._peer_event({'event':'local_message','text':success_msg}),
            lambda kind:self._peer_event({'event':'ui_error','detail':'Network send failed: '+kind}))
        except (QueueSaturated,RuntimeError) as exc:
            messagebox.showwarning('Network busy',str(exc))

    def _tor_peer_ready(self,fp):
        # A strict switch changes connection mode by disconnecting all existing
        # direct sessions; every new connection while enabled uses Tor SOCKS.
        return bool(self.tor_only.get() and self.tor_controller.status()=='READY' and
                    self.peer_hub and self.peer_hub.is_tor_peer(fp))

    def peer_mesh_toggle(self):
        if not self.peer_hub:
            self.mesh_enabled.set(False)
            return messagebox.showwarning('Identity locked','Unlock P2P identity first')
        self.peer_hub.mesh.enable(self.mesh_enabled.get())
        self.peer_log.append('MESH '+('ENABLED' if self.mesh_enabled.get() else 'DISABLED')+
                             ' • only signed presence and encrypted chat will be routed')

    def peer_mesh_send(self):
        if not self.peer_hub or not self.peer_hub.mesh.enabled:
            return messagebox.showwarning('Mesh off','Enable mesh and connect to one or more authenticated peers')
        fp=self.mesh_target.get().strip().lower()
        text=self.mesh_text.get().strip()
        if fp not in dict(self.peer_hub.mesh.online()):
            return messagebox.showwarning('Unknown recipient','Wait for a signed presence announcement. Verify the full fingerprint separately.')
        if self.tor_only.get() and (self.tor_controller.status()!='READY' or
                not self.peer_hub.peers() or
                not all(self.peer_hub.is_tor_peer(x) for x in self.peer_hub.peers())):
            return messagebox.showerror('Tor-only','All active mesh links must be Tor-routed')
        if not messagebox.askyesno('Send encrypted mesh message',
              'Send this message to the signed mesh identity?\n\n'+fp+
              '\n\nYou must independently verify the recipient fingerprint. '+
              'Intermediate peers will see fingerprints and hop information but not message plaintext.'):
            return
        try:
            msg_id=self.peer_hub.mesh.send_message(fp,text)
            self.mesh_text.set('')
            self.peer_log.append('MESH QUEUED • '+msg_id+' (not a delivery receipt)')
        except Exception as e:messagebox.showerror('Mesh message failed',type(e).__name__+': '+str(e)[:120])

    def peer_find_port(self):
        bind='0.0.0.0' if self.peer_bind.get().startswith('LAN') else '127.0.0.1'
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
                sock.bind((bind,0))
                self.peer_port.set(str(sock.getsockname()[1]))
        except OSError as e:
            messagebox.showerror('Port selection failed',type(e).__name__)

    def peer_select_tor_binary(self):
        from tkinter import filedialog
        filename=filedialog.askopenfilename(title='Choose Tor daemon from independently verified Tor Expert Bundle',
            filetypes=[('Tor daemon','tor.exe'),('All files','*')],parent=self.root)
        if not filename:return
        try:
            self.tor_controller.set_binary(filename)
            self.tor_binary.set(filename)
        except (OSError,ValueError) as e:messagebox.showerror('Tor daemon',str(e))

    def peer_toggle_tor(self):
        if not self.tor_only.get():
            self.tor_controller.stop()
            if self.peer_hub:
                self.peer_hub.close()
                self.peer_hub=PeerHub(self.peer_identity,self._peer_event,self._peer_allow,
                                      nickname=self.chat_nickname.get()) if self.peer_identity else None
                if self.peer_hub:self.peer_hub.mesh.enable(self.mesh_enabled.get())
            self.tor_onion.set('No onion service running')
            return
        if not self.peer_hub or not self.peer_identity:
            self.tor_only.set(False)
            return messagebox.showwarning('Identity locked','Unlock the P2P identity first')
        if self.peer_hub.peers() and not messagebox.askyesno('Disconnect direct sessions',
             'Enabling Tor-only disconnects existing direct P2P sessions. Continue?'):
            self.tor_only.set(False);return
        # Disable LAN discovery and WAN relay connections in Tor-only mode.
        self.chat_stop_discovery()
        self.wan_stop_connection()
        self.peer_hub.close()
        self.peer_hub=PeerHub(self.peer_identity,self._peer_event,self._peer_allow,
                              nickname=self.chat_nickname.get())
        self.peer_hub.require_tor(True,lambda:self.tor_controller.status()=='READY')
        self.peer_hub.mesh.enable(self.mesh_enabled.get())
        try:
            self.peer_hub.listen('127.0.0.1',int(self.peer_port.get()))
            self.tor_controller.start(peer_port=self.peer_hub.listen_port,
                                      executable=self.tor_binary.get() or None,
                                      socks_port=0)
            self.peer_proxy_host.set('127.0.0.1')
            self.peer_proxy_port.set(str(self.tor_controller.socks_port))
            self.peer_transport.set('Tor (.onion ONLY • fail closed)')
        except (OSError,ValueError,RuntimeError) as e:
            self.tor_only.set(False)
            self.peer_hub.require_tor(False)
            self.peer_hub.stop_listener()
            self.tor_controller.stop()
            messagebox.showerror('Tor was not enabled',str(e)[:260])

    def peer_open_official_tor(self):
        import webbrowser
        webbrowser.open('https://www.torproject.org/download/tor/')

    def page_peer_to_peer(self):
        from crypto import styled_label, action, CARD, MUTED, ACCENT, FG
        self.head('Peer to Peer','Encrypted direct connections, opt-in multi-hop mesh and Tor onion-service hosting. No central peer directory. '
                  'Exchange encrypted payment requests and public receiving addresses; payment settlement remains external.')
        c=self.card()
        styled_label(c,'01   LOCAL DEVICE IDENTITY',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Independent Ed25519 identity encrypted locally with Argon2id + AES-GCM. '
                    'Never use crypto wallet seed words for P2P identity.')
        styled_label(c,'YOUR FINGERPRINT (share only this public identifier):',9,fg=MUTED).pack(anchor='w')
        entry=ttk.Entry(c,textvariable=self.peer_fp_var,state='readonly');entry.pack(fill='x',pady=5)
        row=tk.Frame(c,bg=CARD);row.pack(fill='x',pady=5)
        action(row,'Create / Unlock P2P Identity',self.peer_unlock).pack(side='left',padx=(0,8))
        action(row,'Copy Public Fingerprint',self._copy_peer_fp).pack(side='left',padx=(0,8))
        action(row,'Lock / Disconnect All',self.peer_lock).pack(side='left')
        styled_label(c,'ONLINE STATUS',10,True,fg=ACCENT).pack(anchor='w',pady=(7,0))
        styled_label(c,'',11,fg=FG,textvariable=self.peer_status).pack(anchor='w')

        c=self.card()
        styled_label(c,'02   HOST A DIRECT CONNECTION',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'QUICK SETUP: (1) Both create identities and exchange public fingerprints securely. '
                    '(2) One starts listening and shares its IP/.onion and port. '
                    '(3) The other connects and the host checks the incoming fingerprint.\n\n'
                    'Tor / same computer: listen on 127.0.0.1. LAN: listen on 0.0.0.0, explicit permission required. '
                    'For internet direct TCP, configure your firewall/router manually. No automatic NAT traversal.')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        self._peer_combo_field(row,'Listen mode',self.peer_bind,
                      ('Private loopback (Tor/on this computer)','LAN (all local interfaces)'),30)
        self._peer_input(row,'Listen port',self.peer_port,10)
        action(row,'Start Listener',self.peer_start_listener).pack(side='left',padx=6,pady=(25,5))
        action(row,'Stop Listener',self.peer_stop_listener).pack(side='left',padx=6,pady=(25,5))
        action(row,'Find Free Port',self.peer_find_port).pack(side='left',padx=6,pady=(25,5))
        self.info(c,'Windows WinError 10013: this usually means port access is blocked or reserved. Use Find Free Port and retry; do not disable firewall protections.')

        c=self.card()
        styled_label(c,'03   CONNECT TO AN ONLINE PEER',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Require a full fingerprint obtained independently from the other user. '
                    'Never accept a fingerprint received only from the same untrusted connection.')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        self._peer_combo_field(row,'Transport',self.peer_transport,
                         ('Direct TCP (LAN / configured router)','Tor (.onion ONLY • fail closed)'),30)
        self._peer_input(row,'Host / .onion',self.peer_target,30)
        self._peer_input(row,'Port',self.peer_target_port,8)
        row2=tk.Frame(c,bg=CARD);row2.pack(fill='x')
        self._peer_input(row2,'EXPECTED REMOTE fingerprint (64 hex)',self.peer_expected,68)
        row3=tk.Frame(c,bg=CARD);row3.pack(fill='x')
        self._peer_input(row3,'Tor SOCKS host',self.peer_proxy_host,17)
        self._peer_input(row3,'Tor SOCKS port',self.peer_proxy_port,9)
        action(row3,'Connect Securely',self.peer_connect).pack(side='left',padx=8,pady=(25,5))
        self.info(c,'External Tor connections use local SOCKS and v3 .onion addresses only. '
                    'The built-in Tor controller below can start and host Tor when an official Tor daemon is supplied; no direct fallback.')

        c=self.card()
        styled_label(c,'03B   ENCRYPTED P2P MESH NETWORK',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Opt-in multihop routing over verified active peers (up to three hops). '
                    'Messages are signed and encrypted end-to-end for the destination. Relays see identity fingerprints, '
                    'routing metadata and timing. Signed delivery acknowledgments mean received by endpoint, not read. '
                    'NO wallet keys, balances, or automatic money movement are sent.')
        tk.Checkbutton(c,text='ENABLE MESH RELAY (private messages only)',variable=self.mesh_enabled,
                       command=self.peer_mesh_toggle,bg=CARD,fg=ACCENT,selectcolor='#302047',
                       activebackground=CARD,activeforeground=ACCENT).pack(anchor='w',pady=5)
        styled_label(c,'',11,fg=FG,textvariable=self.mesh_status).pack(anchor='w')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        self.mesh_target_combo=self._peer_combo_field(row,'SIGNED REMOTE FINGERPRINT',
                                 self.mesh_target,(),68)
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        self._peer_input(row,'End-to-end encrypted message (max 500 characters)',self.mesh_text,70)
        action(row,'Send via Mesh',self.peer_mesh_send).pack(side='left',padx=8,pady=(25,5))
        action(c,'Re-announce my public presence',lambda: self.peer_hub.mesh.announce() if self.peer_hub else None).pack(anchor='w',pady=6)

        c=self.card()
        styled_label(c,'03C   BUILT-IN TOR CONTROLLER',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'The switch starts/stops a local Tor daemon and publishes your LOCAL P2P listener as a v3 onion service. '
                    'Only peer traffic is routed. Wallet RPC, payments, and the rest of the computer are NOT anonymized. '
                    'An independently verified Tor Expert Bundle executable is required.')
        tk.Checkbutton(c,text='TOR-ONLY P2P (NO DIRECT FALLBACK)',variable=self.tor_only,
                       command=self.peer_toggle_tor,bg=CARD,fg=ACCENT,selectcolor='#302047',
                       activebackground=CARD,activeforeground=ACCENT).pack(anchor='w',pady=5)
        styled_label(c,'',11,fg=FG,textvariable=self.tor_status).pack(anchor='w')
        styled_label(c,'',10,fg=MUTED,textvariable=self.tor_onion).pack(anchor='w',pady=5)
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        action(row,'Locate Verified Tor Daemon',self.peer_select_tor_binary).pack(side='left',padx=(0,8),pady=5)
        action(row,'Official Tor Project',self.peer_open_official_tor).pack(side='left',pady=5)
        styled_label(c,'',9,fg=MUTED,textvariable=self.tor_binary).pack(anchor='w')

        c=self.card()
        styled_label(c,'04   ENCRYPTED PAYMENT REQUEST' ,14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Select a connected peer, request an amount, and share ONLY public receiving information. '
                    'This does not send money or confirm settlement.')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        self.peer_combo=self._peer_combo_field(row,'ONLINE / VERIFIED PEER',self.peer_choice,
                                                self.peer_hub.peers() if self.peer_hub else (),65)
        row2=tk.Frame(c,bg=CARD);row2.pack(fill='x')
        self._peer_combo_field(row2,'Method / provider',self.peer_method,PROVIDERS,28)
        self._peer_input(row2,'Amount',self.peer_amount,12)
        self._peer_input(row2,'Currency (USD, BTC...)',self.peer_currency,12)
        row3=tk.Frame(c,bg=CARD);row3.pack(fill='x')
        self._peer_input(row3,'Chain / network (if crypto)',self.peer_network,30)
        self._peer_input(row3,'Memo',self.peer_memo,28)
        self.peer_public_options=self._p2p_public_wallets()
        row4=tk.Frame(c,bg=CARD);row4.pack(fill='x')
        mywallet=self._peer_combo_field(row4,'Choose one of MY public wallets (optional)',
                      self.peer_wallet_choice,tuple(self.peer_public_options),70)
        mywallet.bind('<<ComboboxSelected>>',self._peer_choose_wallet)
        self._peer_input(c,'PUBLIC receiving address / provider handle (no secret)',self.peer_destination,78)
        action(c,'Review & Send REQUEST (no transfer)',self.peer_send_request).pack(anchor='w',pady=10)

        c=self.card()
        styled_label(c,'05   PRIVATE MESSAGES & INCOMING REQUESTS',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Requests remain unverified until the legitimate processor or blockchain confirms them. '
                    'No balance is credited and no transactions are signed automatically.')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        self._peer_input(row,'Send short message to selected peer',self.peer_note,70)
        action(row,'Send Message',self.peer_send_note).pack(side='left',pady=(25,5))
        self.peer_log_view=tk.Text(c,height=13,bg='#0a1419',fg=FG,insertbackground=FG,
                                   wrap='word',font=('Consolas',10),state='disabled',relief='flat')
        self.peer_log_view.pack(fill='both',expand=True,pady=10)
        self.info(c,'No server, no address book upload, no seed sharing. Logs exist only in app memory. '
                    'Use your existing Fiat Payments / Send screen to independently initiate and verify any transfer.')

    def _peer_input(self,parent,label,var,width=24):
        from crypto import styled_label, CARD, MUTED
        f=tk.Frame(parent,bg=CARD);f.pack(side='top' if parent.master is self.content else 'left', fill='x',padx=5,pady=3)
        styled_label(f,label,9,fg=MUTED).pack(anchor='w')
        w=ttk.Entry(f,textvariable=var,width=width)
        w.pack(anchor='w',fill='x')
        return w

    def _peer_combo_field(self,parent,label,var,options,width=28):
        from crypto import styled_label, CARD, MUTED
        f=tk.Frame(parent,bg=CARD);f.pack(side='left',padx=5,pady=3)
        styled_label(f,label,9,fg=MUTED).pack(anchor='w')
        w=ttk.Combobox(f,textvariable=var,values=list(options),state='readonly',width=width)
        w.pack(anchor='w')
        return w
