"""WAN room/private chat for Tkinter. Only verified public contact cards sent on network.

The chat protocol never accesses wallet or payment secrets. Relay configuration
requires a user-operated/public HTTPS service; no cloud service is bundled.
"""
from __future__ import annotations
import json, queue, threading, time
from datetime import datetime
import tkinter as tk
from tkinter import ttk,messagebox
from core.wan_chat import WANClient, WANContacts, validate_card, contact_card, seal, open_envelope, validate_server_url
from core.lan_chat import check_room,check_nick
from core.peer_network import _safe_chat

BG='#07060b';CARD='#15101e';FG='#f2edf9';MUTED='#a39ab6';ACCENT='#47fca3';FIELD='#0c0914';WARN='#ff707a'

class WANChatUI:
    def init_wan(self):
        self.wan_url=tk.StringVar(value='http://127.0.0.1:8765')
        self.wan_nick=tk.StringVar(value='CryptoUser')
        self.wan_room=tk.StringVar(value='#general')
        self.wan_to=tk.StringVar(value='ROOM — verified contacts')
        self.wan_text=tk.StringVar(value='')
        self.wan_tor=tk.BooleanVar(value=False)
        self.wan_state=tk.StringVar(value='DISCONNECTED • Start your local or HTTPS relay')
        self.wan_contacts=WANContacts(self._peer_folder())
        self.wan_directory={}
        self.wan_members={}
        self.wan_log=[]
        self._wan_dirty=True
        self.wan_current=None
        self.wan_events=queue.Queue(maxsize=2048)
        self.wan_ops=queue.Queue(maxsize=128)
        self.wan_stop=threading.Event()
        self.wan_thread=None
        self.root.after(250,self.wan_ui_poll)

    def _wan_enqueue(self,operation):
        try:
            self.wan_ops.put_nowait(operation)
            return True
        except queue.Full:
            messagebox.showwarning('Network busy','Outgoing chat queue full. Retry after the relay catches up.')
            return False

    def wan_line(self,s):
        self._wan_dirty=True
        self.wan_log.append('['+datetime.now().strftime('%H:%M:%S')+'] '+str(s)[:1100])
        self.wan_log=self.wan_log[-400:]

    def wan_stop_connection(self):
        self.wan_stop.set()
        self.wan_current=None
        self.wan_state.set('DISCONNECTED')
        self.wan_ops=queue.Queue(maxsize=128)

    def wan_connect(self):
        if getattr(self,'tor_only',None) is not None and self.tor_only.get():
            return messagebox.showwarning('Tor-only','WAN relay chat is disabled while Tor-only P2P is enabled; use the .onion mesh connection instead')
        if not self.peer_identity:
            return messagebox.showwarning('Identity locked','Open Peer to Peer and unlock your chat identity first.')
        if self.wan_thread and self.wan_thread.is_alive() and not self.wan_stop.is_set():
            return messagebox.showinfo('Connected','Stop the current internet-chat connection before connecting again.')
        try:
            url=validate_server_url(self.wan_url.get(),via_tor=self.wan_tor.get())
            nick=check_nick(self.wan_nick.get())
            room=check_room(self.wan_room.get())
        except Exception as e:return messagebox.showerror('Invalid settings',str(e))
        if url.startswith('https://') and not messagebox.askyesno('WAN privacy notice',
                'This relay will see your public chat identity, IP address, room names and activity times. '
                'It cannot decrypt protected chat messages. Only encrypted messages to manually verified contacts are sent. '\
                '\n\nUse this server?'):
            return
        self.wan_stop=threading.Event()
        self.wan_ops=queue.Queue(maxsize=128)
        self.wan_thread=threading.Thread(target=self._wan_work,
            args=(self.peer_identity,nick,url,room,self.wan_stop,self.wan_ops,self.wan_tor.get()),daemon=True)
        self.wan_thread.start();self.wan_state.set('CONNECTING • '+url)

    def _wan_work(self,identity,nick,url,room,stopped,ops,via_tor):
        try:client=WANClient(identity,nick,url,via_tor=via_tor)
        except Exception as e:
            self.wan_events.put({'event':'error','detail':type(e).__name__},timeout=1)
            self.wan_events.put({'event':'stopped'},timeout=1)
            return
        def emit(event,**data):self.wan_events.put({'event':event,**data},timeout=1)
        directory={}
        members={}
        room_current=room
        try:
            client.register();client.join(room_current)
            emit('ready',url=url,room=room_current)
            last_poll=0
            while not stopped.is_set():
                try:
                    op,arg=ops.get(timeout=0.4)
                except queue.Empty:op,arg=None,None
                if op:
                    try:
                        if op=='room':
                            check_room(arg)
                            client.join(arg)
                            if arg!=room_current:client.leave(room_current)
                            room_current=arg;emit('joined',room=arg)
                        elif op=='send':
                            dest, content=arg
                            _safe_chat(content)
                            if dest=='ROOM — verified contacts':
                                remote=client.members(room_current)['users']
                                trusted=[]
                                for entry in remote:
                                    fp=entry['fingerprint']
                                    card=self.wan_contacts.cards.get(fp)
                                    if card and fp!=identity.fingerprint:trusted.append(card)
                                if not trusted:raise ValueError('No verified contacts in this room. Verify contacts first.')
                                sent=0
                                for card in trusted:
                                    client.send(seal(identity,card,content,room_current,'room'))
                                    sent+=1
                                emit('sent',text=f'{room_current} <you> {content} [{sent} verified recipient(s)]')
                            else:
                                card=self.wan_contacts.cards.get(dest)
                                if not card:raise ValueError('You must verify and trust this peer first')
                                client.send(seal(identity,card,content))
                                emit('sent',text='PRIVATE <you → '+card['nickname']+'> '+content+' [encrypted]')
                        elif op=='refresh':last_poll=0
                    except Exception as e:emit('error',detail=f'{type(e).__name__}: {str(e)[:150]}')
                if time.monotonic()-last_poll>=4:
                    last_poll=time.monotonic()
                    directory=client.directory()['users']
                    members=client.members(room_current)['users']
                    emit('directory',users=directory,members=members,room=room_current)
                    envelopes=client.inbox()['envelopes']
                    ack=[]
                    for envelope in envelopes:
                        fp=envelope['from'];card=self.wan_contacts.cards.get(fp)
                        if card is None:
                            # Discard unsolicited unreadable encrypted content. The
                            # relay is not permitted to auto-approve contacts.
                            ack.append(envelope['id'])
                            emit('ignored',fingerprint=fp)
                            continue
                        try:
                            value=open_envelope(identity,card,envelope)
                            ack.append(envelope['id'])
                            if value['type']=='room':
                                emit('incoming',message=value['room']+' <'+card['nickname']+'> '+value['text'])
                            else:emit('incoming',message='PRIVATE <'+card['nickname']+'> '+value['text'])
                        except Exception:
                            # Tampered/incorrectly encrypted packets are discarded rather
                            # than repeatedly poisoning the inbox.
                            ack.append(envelope['id'])
                            emit('error',detail='Invalid encrypted message discarded ('+fp[:12]+')')
                    if ack:client.ack(ack)
        except Exception as e:emit('error',detail=f'Internet relay error: {type(e).__name__}: {str(e)[:155]}')
        finally:
            try:client.session.close()
            except Exception:pass
            emit('stopped')

    def wan_ui_poll(self):
        try:
            for _ in range(100):
                try: event=self.wan_events.get_nowait()
                except queue.Empty:break
                typ=event['event']
                self._wan_dirty=True
                if typ=='ready':
                    self.wan_state.set('CONNECTED • encrypted relay '+event['url'])
                    self.wan_line('Connected to WAN relay; joined '+event['room'])
                elif typ=='directory':
                    self.wan_directory={x['fingerprint']:x for x in event['users']
                                        if x['fingerprint']!=getattr(self.peer_identity,'fingerprint','')}
                    self.wan_members={x['fingerprint']:x for x in event['members']}
                    online=sum(x['online'] for x in self.wan_directory.values())
                    self.wan_state.set(f'{online} online worldwide • {len(self.wan_directory)} registered • '
                                       f'{len(self.wan_members)} in {event["room"]} • verified contacts: {len(self.wan_contacts.cards)}')
                elif typ=='incoming':self.wan_line(event['message'])
                elif typ=='sent':self.wan_line(event['text'])
                elif typ=='ignored':self.wan_line('Blocked unsolicited message from unverified identity '+event['fingerprint'][:14])
                elif typ=='joined':self.wan_line('Joined '+event['room'])
                elif typ=='error':self.wan_line('WARNING • '+event['detail'])
                elif typ=='stopped':
                    if self.wan_stop.is_set() or not (self.wan_thread and self.wan_thread.is_alive()):
                        self.wan_state.set('DISCONNECTED • WAN relay unavailable')
            if self.current_page=='Internet Chat' and self._wan_dirty:
                self._wan_redraw()
                self._wan_dirty=False
        except (tk.TclError,RuntimeError):return
        try:self.root.after(450,self.wan_ui_poll)
        except (tk.TclError,RuntimeError):pass

    def _wan_redraw(self):
        tree=getattr(self,'wan_user_tree',None)
        if tree and tree.winfo_exists():
            selected=tree.selection()
            curr=selected[0] if selected else None
            allfps=set(self.wan_directory)|set(self.wan_contacts.cards)
            for iid in tree.get_children():
                if iid not in allfps:tree.delete(iid)
            for fp in sorted(allfps):
                info=self.wan_directory.get(fp,{})
                card=info.get('card') or self.wan_contacts.cards[fp]
                trusted=fp in self.wan_contacts.cards
                vals=(card['nickname'], 'ONLINE' if info.get('online') else 'OFFLINE / UNKNOWN',
                      'VERIFIED' if trusted else 'UNVERIFIED',
                      'IN ROOM' if fp in self.wan_members else '—',fp[:16]+'…')
                if tree.exists(fp):tree.item(fp,values=vals)
                else:tree.insert('','end',iid=fp,values=vals)
            if curr in allfps:tree.selection_set(curr)
        choices=['ROOM — verified contacts'] + [fp for fp in self.wan_contacts.cards]
        combo=getattr(self,'wan_recipient_widget',None)
        if combo and combo.winfo_exists():
            combo['values']=choices
            if self.wan_to.get() not in choices:self.wan_to.set(choices[0])
        log=getattr(self,'wan_text_view',None)
        if log and log.winfo_exists():
            wanted='\n'.join(self.wan_log[-180:])
            if log.get('1.0','end-1c')!=wanted:
                log.config(state='normal');log.delete('1.0','end');log.insert('end',wanted)
                log.config(state='disabled');log.see('end')

    def wan_selected(self):
        tree=getattr(self,'wan_user_tree',None)
        return tree.selection()[0] if tree and tree.winfo_exists() and tree.selection() else ''

    def wan_trust_selected(self):
        fp=self.wan_selected()
        if not fp:return messagebox.showwarning('Select user','Choose a user from the directory')
        record=self.wan_directory.get(fp)
        if not record:
            return messagebox.showwarning('Not available','To trust someone new, first retrieve their public signed profile from the relay')
        try:
            card=record['card'];validated=validate_card(card)
            if validated!=fp:raise ValueError('Mismatch between public identity and directory')
        except Exception as e:return messagebox.showerror('Invalid peer key',str(e))
        if not messagebox.askyesno('Verify identity OFFLINE',
                'Have you compared this exact entire identity fingerprint with the person through '
                'another trusted channel (voice call, in person, known verified account)?\n\n'
                +fp+'\n\nThe relay directory is UNTRUSTED. Clicking YES saves this key as verified. '
                'Do not approve based only on the nickname.'):
            return
        try:self.wan_contacts.trust(card)
        except Exception as e:return messagebox.showerror('Cannot save contact',str(e))
        self.wan_line('Verified peer identity '+card['nickname']+' '+fp[:12])

    def wan_copy_card(self):
        if not self.peer_identity:return messagebox.showwarning('Locked','Unlock P2P identity first')
        data=json.dumps(contact_card(self.peer_identity,check_nick(self.wan_nick.get())),sort_keys=True)
        self.root.clipboard_clear();self.root.clipboard_append(data)
        messagebox.showinfo('Public card copied','Signed PUBLIC chat contact card copied. Contains no wallet secrets.')

    def wan_send_message(self):
        if not self.wan_thread or not self.wan_thread.is_alive() or self.wan_stop.is_set():
            return messagebox.showwarning('Not connected','Connect to the internet relay first')
        try:content=_safe_chat(self.wan_text.get())
        except Exception as e:return messagebox.showerror('Blocked message',str(e))
        if self._wan_enqueue(('send',(self.wan_to.get(),content))):
            self.wan_text.set('')

    def wan_change_room(self):
        try:room=check_room(self.wan_room.get())
        except Exception as e:return messagebox.showerror('Invalid room',str(e))
        if self.wan_thread and self.wan_thread.is_alive() and not self.wan_stop.is_set():
            self._wan_enqueue(('room',room))

    def page_internet_chat(self):
        self._wan_dirty=True
        self.head('Internet / Worldwide Chat','WAN chat across countries and states • encrypted direct messages • verified room peers • offline queued messages')
        p=tk.Frame(self.content,bg=CARD,padx=14,pady=12);p.pack(fill='x',pady=5)
        tk.Label(p,text='Relay HTTPS endpoint (self-hosted or trusted provider)',bg=CARD,fg=FG).pack(anchor='w')
        ttk.Entry(p,textvariable=self.wan_url,width=64).pack(fill='x',pady=(2,8))
        ttk.Checkbutton(p,text='Tor ONLY via local SOCKS5 127.0.0.1:9050 (no direct fallback; supports .onion relays)',
                        variable=self.wan_tor).pack(anchor='w',pady=3)
        r=tk.Frame(p,bg=CARD);r.pack(fill='x',pady=4)
        tk.Label(r,text='Nickname',bg=CARD,fg=FG).pack(side='left')
        ttk.Entry(r,textvariable=self.wan_nick,width=16).pack(side='left',padx=6)
        tk.Label(r,text='Room',bg=CARD,fg=FG).pack(side='left',padx=(12,0))
        ttk.Combobox(r,textvariable=self.wan_room,values=['#general','#trading','#help','#global','#support'],width=19).pack(side='left',padx=5)
        ttk.Button(r,text='Join Room',command=self.wan_change_room).pack(side='left',padx=5)
        r2=tk.Frame(p,bg=CARD);r2.pack(fill='x',pady=6)
        ttk.Button(r2,text='Connect Worldwide',command=self.wan_connect).pack(side='left',padx=4)
        ttk.Button(r2,text='Disconnect WAN',command=self.wan_stop_connection).pack(side='left',padx=4)
        ttk.Button(r2,text='Copy My Public Contact Card',command=self.wan_copy_card).pack(side='left',padx=4)
        tk.Label(p,textvariable=self.wan_state,bg=CARD,fg=ACCENT,wraplength=850,justify='left').pack(anchor='w',pady=7)
        split=tk.Frame(self.content,bg=BG);split.pack(fill='both',expand=True)
        side=tk.Frame(split,bg=CARD,padx=9,pady=10);side.pack(side='right',fill='y',padx=(8,0))
        tk.Label(side,text='Worldwide Users / Contacts',bg=CARD,fg=ACCENT,font=('Segoe UI',11,'bold')).pack(anchor='w')
        tree=ttk.Treeview(side,columns=('nick','presence','trust','room','id'),show='headings',height=11)
        for name,width in (('nick',125),('presence',110),('trust',88),('room',78),('id',114)):
            tree.heading(name,text=name.upper());tree.column(name,width=width,stretch=False)
        tree.pack(fill='both',expand=True,pady=5);self.wan_user_tree=tree
        ttk.Button(side,text='Verify Selected Peer',command=self.wan_trust_selected).pack(fill='x',pady=4)
        tk.Label(side,text='Trust requires comparing the FULL\nfingerprint outside this application.\nRelay listings alone are not proof.',
                 bg=CARD,fg=WARN,justify='left',font=('Segoe UI',9)).pack(anchor='w')
        chat=tk.Frame(split,bg=CARD,padx=11,pady=10);chat.pack(side='left',fill='both',expand=True)
        tk.Label(chat,text='Encrypted Internet Chat',bg=CARD,fg=ACCENT,font=('Segoe UI',11,'bold')).pack(anchor='w')
        view=tk.Text(chat,state='disabled',bg=FIELD,fg=FG,wrap='word',font=('Consolas',10),height=16)
        view.pack(fill='both',expand=True,pady=8);self.wan_text_view=view
        tk.Label(chat,text='Send to (room broadcasts only to verified contacts who joined the room)',bg=CARD,fg=FG).pack(anchor='w')
        self.wan_recipient_widget=ttk.Combobox(chat,textvariable=self.wan_to,state='readonly',width=60,
                                              values=['ROOM — verified contacts'])
        self.wan_recipient_widget.pack(fill='x',pady=5)
        entry=ttk.Entry(chat,textvariable=self.wan_text,width=70);entry.pack(fill='x',pady=5)
        entry.bind('<Return>',lambda e:self.wan_send_message())
        ttk.Button(chat,text='Send Encrypted Chat Message',command=self.wan_send_message).pack(anchor='w',pady=5)
        tk.Label(self.content,text='NO wallet or bank information is published. No fiat/crypto funds move through chat. '
                          'Online means recent relay activity, not guaranteed human availability. Offline messages persist on '
                          'relay up to 7 days. A relay server must be running for global chat.',
                 bg=BG,fg=WARN,wraplength=890,justify='left').pack(anchor='w',pady=9)
        self._wan_redraw()
