"""Local LAN IRC-style room chat for the experimental CRYPTO wallet desktop UI.

No wallet file reads, no recovery phrases, no fiat or signing secrets.
Presence from a relay hub is *reported*, not independently authenticated.
"""
from __future__ import annotations
import queue
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from core.lan_chat import LANDiscovery, ContactBook, check_nick, check_room
from core.peer_network import _safe_chat


class LANChatUI:
    def init_lan_chat(self):
        self.chat_nickname=tk.StringVar(value='CryptoUser')
        self.chat_room=tk.StringVar(value='#general')
        self.chat_text=tk.StringVar()
        self.chat_dm=tk.StringVar()
        self.chat_discovery_enabled=tk.BooleanVar(value=False)
        self.chat_presence=tk.StringVar(value='Chat offline • identity locked')
        self.chat_discovery=None
        self.chat_discovered={}
        self.chat_log=[]
        self.chat_rosters={}
        self.chat_last_refresh=0.0
        self.chat_contacts=ContactBook(self._peer_folder())

    def _chat_log(self,line):
        now=datetime.now().strftime('%H:%M:%S')
        self.chat_log.append('['+now+'] '+str(line)[:1250])
        self.chat_log=self.chat_log[-250:]

    def _chat_peer_event(self,e):
        what=e.get('event')
        if what=='discovered':
            peer=e['record']
            self.chat_discovered[peer['fingerprint']]={**peer,'last_seen':time.monotonic()}
        elif what=='online':
            self._chat_log('ONLINE (authenticated direct session) • '+e['fingerprint'][:16])
        elif what=='offline':
            self._chat_log('OFFLINE • '+e['fingerprint'][:16])
            self.chat_rosters.pop(e['fingerprint'],None)
        elif what=='roster':
            self.chat_rosters[e['fingerprint']]=e['users']
        elif what=='chat':
            obj=e['data'];author=e['fingerprint'];via=e['via']
            tag=self.chat_contacts.entries.get(author,author[:12])
            relay=' [via hub / not independently verified]' if author!=via else ''
            self._chat_log(obj['channel']+' <'+tag+'> '+obj['text']+relay)
        elif what=='local_chat':
            obj=e['data']
            self._chat_log(obj['channel']+' <you> '+obj['text'])
        elif what=='message' and e['data'].get('type')=='message':
            author=e['fingerprint']; name=self.chat_contacts.entries.get(author,author[:12])
            self._chat_log('PRIVATE <'+name+'> '+e['data']['text'])
        elif what=='local_message':
            msg=str(e['text'])
            if msg.startswith('YOU →'):self._chat_log('PRIVATE '+msg[:1100])
        elif what=='listening':
            self._chat_log('TCP listener active at '+e['host']+':'+str(e['port']))
        elif what=='error' or what=='ui_error':
            self._chat_log('Network warning: '+e.get('detail','unknown')[:120])

    def _chat_refresh_view(self):
        if self.current_page!='IRC LAN Chat':return
        if self.chat_presence is None:return
        hub=self.peer_hub
        now=time.monotonic()
        self.chat_discovered={fp:p for fp,p in self.chat_discovered.items()
                              if now-p['last_seen']<35}
        online=set(hub.peers()) if hub else set()
        relay_claims={}
        for parent,users in list(self.chat_rosters.items()):
            if parent not in online:continue
            for user in users:
                fp=user['fingerprint']
                if fp not in online and fp!=getattr(self.peer_identity,'fingerprint',None):
                    relay_claims[fp]=user
        observed=set(online)|set(self.chat_discovered)|set(self.chat_contacts.entries)|set(relay_claims)
        self.chat_presence.set(f'{len(online)} connected directly • '
                               f'{len(relay_claims)} hub-reported • '
                               f'{len(self.chat_discovered)} advertised on LAN • '
                               f'{len(self.chat_contacts.entries)} saved contacts')
        tree=getattr(self,'chat_user_tree',None)
        if tree and tree.winfo_exists():
            selected=tree.selection()
            selected_fp=selected[0] if selected else None
            existing=set(tree.get_children())
            for fp in existing-observed:tree.delete(fp)
            for fp in sorted(observed):
                trusted=fp in self.chat_contacts.entries
                if fp in online: status='ONLINE • direct session'
                elif fp in relay_claims:status='ONLINE? • hub reports'
                elif fp in self.chat_discovered:status='DISCOVERED • unverified'
                else:status='OFFLINE • saved contact'
                nick=(self.chat_contacts.entries.get(fp) or
                      self.chat_discovered.get(fp,{}).get('nickname') or
                      relay_claims.get(fp,{}).get('nick') or 'Peer')
                data=(nick,status,'YES' if trusted else 'NO',fp[:18]+'…')
                if fp in existing:tree.item(fp,values=data)
                else:tree.insert('',tk.END,iid=fp,values=data)
            if selected_fp in observed:tree.selection_set(selected_fp)
        logs=getattr(self,'chat_log_widget',None)
        if logs and logs.winfo_exists():
            display='\n'.join(self.chat_log[-100:])
            if logs.get('1.0','end-1c') != display:
                logs.configure(state='normal');logs.delete('1.0','end')
                logs.insert('1.0',display);logs.configure(state='disabled')
                logs.see('end')

    def chat_start_discovery(self,advertise=True):
        if getattr(self,'tor_only',None) is not None and self.tor_only.get():
            return messagebox.showwarning('Tor-only','LAN discovery is disabled while Tor-only P2P is enabled')
        if not self.peer_hub or not self.peer_identity:
            return messagebox.showwarning('Locked','Unlock your peer identity first')
        hub=self.peer_hub
        if advertise and (not hub._listener or getattr(hub,'bind_host','')!='0.0.0.0'):
            return messagebox.showwarning('Listener required',
                'To ADVERTISE you must start your Peer to Peer listener in LAN mode. '
                'You can BROWSE without advertising or starting a listener.')
        if self.chat_discovery:return
        if advertise and not messagebox.askyesno('Enable LAN visibility?',
            'Other devices on this local Wi-Fi/LAN will be able to see your public '
            'chat fingerprint, nickname and listener port. NO wallet contents or '
            'bank details are announced. LAN discovery can be spoofed. Enable?'):
            return
        try:
            discovery=LANDiscovery(self.peer_identity.fingerprint,
                                   check_nick(self.chat_nickname.get()),
                                   getattr(hub,'listen_port',19420),
                                   lambda x:self._peer_event({'event':'discovered','record':x}),
                                   advertise=advertise)
            discovery.start();self.chat_discovery=discovery
            self.chat_discovery_enabled.set(True)
            self._chat_log(('LAN visibility ON' if advertise else 'Browse-only discovery ON')+
                           ' • no wallet metadata advertised')
        except Exception as ex:
            messagebox.showerror('LAN discovery unavailable',str(ex))
            self.chat_discovery_enabled.set(False)

    def chat_stop_discovery(self):
        if self.chat_discovery:
            self.chat_discovery.stop();self.chat_discovery=None
        self.chat_discovery_enabled.set(False)
        self.chat_discovered.clear()
        self._chat_log('LAN visibility OFF')

    def chat_apply_nick(self):
        try:
            name=check_nick(self.chat_nickname.get())
            if self.peer_hub:self.peer_hub.set_nickname(name)
        except Exception as ex:return messagebox.showerror('Nickname',str(ex))
        if self.chat_discovery:
            self.chat_stop_discovery()
            messagebox.showinfo('Discovery disabled','Restart LAN discovery to advertise your new nickname.')
        self._chat_log('Nickname set to '+name)

    def chat_selected_fp(self):
        w=getattr(self,'chat_user_tree',None)
        if not w or not w.winfo_exists() or not w.selection():return ''
        return w.selection()[0]

    def chat_use_discovered(self):
        fp=self.chat_selected_fp()
        item=self.chat_discovered.get(fp)
        if not item:
            return messagebox.showwarning('No LAN entry','Select a discovered LAN device from the list')
        self.peer_target.set(item['ip']);self.peer_target_port.set(str(item['port']))
        self.peer_expected.set(fp)
        self.peer_transport.set('Direct TCP (LAN / configured router)')
        self._chat_log('Prepared '+item['ip']+' for manual authenticated pairing')
        messagebox.showinfo('Fingerprint NOT verified',
            'Address and claimed fingerprint copied to Peer to Peer > Connect.\n\n'
            'A LAN beacon can be forged. Compare the entire fingerprint over a '
            'separate trusted channel before connecting. No automatic trust.')
        self.show('Peer to Peer')

    def chat_save_contact(self):
        fp=self.chat_selected_fp()
        if not fp:return messagebox.showwarning('Select contact','Choose a person in the user list')
        if not messagebox.askyesno('Verify identity OUT OF BAND',
            'Have you compared ALL 64 hexadecimal digits of this peer fingerprint '
            'using an independent trusted channel?\n\n'+fp+'\n\n'
            'Only save as verified if you really checked. Discovery is NOT identity proof.'):
            return
        from tkinter import simpledialog
        name=simpledialog.askstring('Save peer alias','Alias (2–20 letters/numbers/_/-):',
                      initialvalue=self.chat_discovered.get(fp,{}).get('nickname','Peer'),parent=self.root)
        if name is None:return
        try:self.chat_contacts.remember(fp,name)
        except Exception as ex:return messagebox.showerror('Contact not saved',str(ex))
        self._chat_log('Saved independently verified contact '+name+' • '+fp[:16])
        self._chat_refresh_view()

    def chat_remove_contact(self):
        fp=self.chat_selected_fp()
        if fp in self.chat_contacts.entries:
            self.chat_contacts.remove(fp);self._chat_log('Removed saved peer '+fp[:16])

    def chat_join_room(self):
        if not self.peer_hub:return messagebox.showwarning('Locked','Unlock identity first')
        room=self.chat_room.get().strip().lower()
        try:self.peer_hub.join_room(room)
        except Exception as ex:return messagebox.showerror('Join failed',str(ex))
        self._chat_log('Joined '+room+' • messages are visible to connected room peers / relay host')

    def chat_leave_room(self):
        if not self.peer_hub:return
        room=self.chat_room.get().strip().lower()
        try:self.peer_hub.part_room(room)
        except Exception as ex:return messagebox.showerror('Leave failed',str(ex))
        self._chat_log('Left '+room)

    def chat_send_room(self):
        if not self.peer_hub:return messagebox.showwarning('Locked','Unlock identity first')
        room=self.chat_room.get().strip().lower();text=self.chat_text.get().strip()
        try:check_room(room);_safe_chat(text)
        except Exception as ex:return messagebox.showerror('Message blocked',str(ex))
        hub=self.peer_hub
        def worker():
            try:hub.send_channel(room,text)
            except Exception as ex:self._peer_event({'event':'ui_error','detail':str(ex)[:130]})
        threading.Thread(target=worker,daemon=True).start()
        self.chat_text.set('')

    def chat_send_dm(self):
        if not self.peer_hub:return
        fp=self.chat_selected_fp();text=self.chat_dm.get().strip()
        if fp not in self.peer_hub.peers():
            return messagebox.showwarning('Not directly connected',
                'Private messages work only over direct authenticated sessions. '
                'Hub-reported or discovered users must connect directly first.')
        try:_safe_chat(text)
        except Exception as ex:return messagebox.showerror('Message blocked',str(ex))
        hub=self.peer_hub
        def worker():
            try:hub.send(fp,{'type':'message','text':text})
            except Exception as ex:self._peer_event({'event':'ui_error','detail':str(ex)[:130]})
            else:self._peer_event({'event':'local_message','text':'YOU → '+fp[:16]+': '+text})
        threading.Thread(target=worker,daemon=True).start()
        self.chat_dm.set('')

    def page_irc_lan_chat(self):
        from crypto import styled_label,action,CARD,ACCENT,FG,MUTED,WARN
        self.head('IRC LAN Chat • private wallet boundaries',
            'Talk across two or more CRYPTO installations on the same Wi-Fi/LAN. '
            'Secure direct peers, opt-in multicast discovery, IRC-style rooms, saved offline contacts and private DMs.')
        c=self.card()
        styled_label(c,'01   IDENTITY • WLAN DISCOVERY',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'First: Peer to Peer > Unlock identity > Start Listener > LAN. '
                  'Discovery is optional and visible to the local network; it shares nickname/fingerprint/port ONLY. '
                  'Peer verification is still mandatory.\n'
                  'Room chat is encrypted per connected hop; a relay host can read room messages. '
                  'Private DMs only go to directly connected peers.',WARN)
        row=tk.Frame(c,bg=CARD);row.pack(fill='x',pady=5)
        self._peer_input(row,'Nickname (public on LAN)',self.chat_nickname,22)
        action(row,'Apply Nickname',self.chat_apply_nick).pack(side='left',padx=5,pady=(25,5))
        action(row,'Browse (no advert)',lambda:self.chat_start_discovery(False)).pack(side='left',padx=5,pady=(25,5))
        action(row,'Advertise + Browse',lambda:self.chat_start_discovery(True)).pack(side='left',padx=5,pady=(25,5))
        action(row,'Stop',self.chat_stop_discovery).pack(side='left',padx=5,pady=(25,5))
        styled_label(c,'',11,fg=FG,textvariable=self.chat_presence).pack(anchor='w')
        action(c,'Open Peer Connection Setup',lambda:self.show('Peer to Peer')).pack(anchor='w',pady=6)

        c=self.card()
        styled_label(c,'02   ONLINE / OFFLINE USER DIRECTORY',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'ONLINE = active authenticated socket. ONLINE? = a hub reports someone online, '
                  'not independently verified. DISCOVERED = an untrusted LAN advertisement. '
                  'OFFLINE = previously saved contact not connected. No financial details here.')
        cols=('nickname','status','trusted','identity')
        tree=ttk.Treeview(c,columns=cols,show='headings',height=8,selectmode='browse')
        for key,width in [('nickname',130),('status',260),('trusted',76),('identity',180)]:
            tree.heading(key,text=key.upper());tree.column(key,width=width,stretch=key=='status')
        tree.pack(fill='x',pady=7);self.chat_user_tree=tree
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        action(row,'Connect to selected LAN device',self.chat_use_discovered).pack(side='left',padx=4)
        action(row,'Save Verified Contact',self.chat_save_contact).pack(side='left',padx=4)
        action(row,'Forget Contact',self.chat_remove_contact).pack(side='left',padx=4)

        c=self.card()
        styled_label(c,'03   CHANNELS • IRC-STYLE ROOM CHAT',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Use #general, #help, #trading or type any #channel-name. '
                  'All participants in a room see messages relayed by the connected host. '
                  'No payments happen in chat, and messages are not saved to disk.')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        room_combo=self._peer_combo_field(row,'Channel',self.chat_room,('#general','#help','#trading','#support'),25)
        room_combo.configure(state='normal')
        action(row,'Join Channel',self.chat_join_room).pack(side='left',padx=4,pady=(25,5))
        action(row,'Leave Channel',self.chat_leave_room).pack(side='left',padx=4,pady=(25,5))
        row2=tk.Frame(c,bg=CARD);row2.pack(fill='x')
        ent=self._peer_input(row2,'Message to channel (1000 characters max)',self.chat_text,75)
        ent.bind('<Return>',lambda e:self.chat_send_room())
        action(row2,'Send to Room',self.chat_send_room).pack(side='left',padx=5,pady=(25,5))

        c=self.card()
        styled_label(c,'04   PRIVATE MESSAGES • DIRECT PEERS ONLY',14,True,fg=ACCENT).pack(anchor='w')
        self.info(c,'Select an ONLINE direct user above. DMs are session-encrypted; '
                  'no message passes through a relay host. Never share seed phrases or financial credentials.')
        row=tk.Frame(c,bg=CARD);row.pack(fill='x')
        entry=self._peer_input(row,'Message to selected online user',self.chat_dm,75)
        entry.bind('<Return>',lambda e:self.chat_send_dm())
        action(row,'Private Message',self.chat_send_dm).pack(side='left',padx=5,pady=(25,5))
        self.chat_log_widget=tk.Text(c,bg='#0a1419',fg=FG,insertbackground=FG,
                      wrap='word',height=17,relief='flat',state='disabled',font=('Consolas',10))
        self.chat_log_widget.pack(fill='both',expand=True,pady=8)
        self.info(c,'Local UI memory only • no automatic balance/status updates • '
                  'discovery may fail on guest Wi-Fi or networks with client isolation.')
        self._chat_refresh_view()
