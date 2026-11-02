"""Threaded Tk live balance UI. No network I/O on the Tk event thread."""
from __future__ import annotations
import threading
import time
import tkinter as tk
from tkinter import ttk
from live_balances import snapshot_btc, snapshot_xmr, snapshot_evm, transaction_state
from performance_runtime import QueueSaturated

BG='#07060b'; CARD='#15101e'; GREEN='#47fca3'; PURPLE='#9a4bea'; MUTED='#a39ab6'; WARN='#ff707a'
SOURCES=('Bitcoin Core BTC','Monero wallet RPC XMR','EVM native coin','EVM ERC-20 token')
INTERVAL_MS=30000

class LiveBalanceUI:
    def init_live_balance(self):
        self.lb_source=tk.StringVar(value=SOURCES[0])
        self.lb_address=tk.StringVar(value='')
        self.lb_contract=tk.StringVar(value='')
        self.lb_balance=tk.StringVar(value='BALANCE UNAVAILABLE · Connect a node and start refresh')
        self.lb_secondary=tk.StringVar(value='—')
        self.lb_tracking=tk.StringVar(value='No broadcast transaction being tracked.')
        self.lb_enabled=False
        self.lb_inflight=False
        self.lb_queued_refresh=False
        self.lb_last_tx=''
        self.lb_last_source=''
        self.lb_epoch=0
        self.lb_closed=False
        self.lb_last_good_monotonic=None
        self.lb_last_good_settings=None
        self.lb_interval_ms=INTERVAL_MS
        self.root.after(self.lb_interval_ms,self._lb_tick)

    def live_balance_panel(self, parent=None):
        parent=parent or self.content
        panel=tk.Frame(parent,bg=CARD,padx=16,pady=14,highlightthickness=1,highlightbackground='#493065')
        panel.pack(fill='x',pady=9)
        tk.Label(panel,text='// LIVE BLOCKCHAIN BALANCE  •  REFRESH EVERY 30s',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(panel,textvariable=self.lb_balance,bg=CARD,fg=GREEN,font=('Consolas',13,'bold'),anchor='w',wraplength=850,justify='left').pack(fill='x',pady=(9,3))
        tk.Label(panel,textvariable=self.lb_secondary,bg=CARD,fg=MUTED,font=('Consolas',9),wraplength=850,justify='left').pack(anchor='w')
        bar=tk.Frame(panel,bg=CARD);bar.pack(fill='x',pady=(10,4))
        ttk.Combobox(bar,textvariable=self.lb_source,values=SOURCES,state='readonly',width=25).pack(side='left',padx=(0,8))
        ttk.Button(bar,text='REFRESH NOW',command=self.lb_refresh).pack(side='left',padx=(0,8))
        self._lb_toggle_button=ttk.Button(bar,text='STOP AUTO' if self.lb_enabled else 'START AUTO',command=self.lb_toggle)
        self._lb_toggle_button.pack(side='left')
        # EVM address must be selected explicitly. BTC vault public addresses are not Core accounts.
        settings=tk.Frame(panel,bg=CARD);settings.pack(fill='x',pady=(5,2))
        tk.Label(settings,text='EVM public address:',bg=CARD,fg=MUTED).pack(side='left')
        ttk.Entry(settings,textvariable=self.lb_address,width=46).pack(side='left',padx=7)
        tk.Label(settings,text='Token contract (optional, verified by you):',bg=CARD,fg=MUTED).pack(side='left',padx=(5,0))
        ttk.Entry(settings,textvariable=self.lb_contract,width=27).pack(side='left',padx=7)
        tk.Label(panel,text='BTC uses the loaded Bitcoin Core wallet; XMR uses wallet RPC; EVM requires a selected chain and public address. '
                 'A standalone BTC .vault address is NOT a Bitcoin Core balance. No RPC response = unavailable, never zero.',
                 bg=CARD,fg=WARN,wraplength=900,justify='left').pack(anchor='w',pady=4)
        tk.Label(panel,textvariable=self.lb_tracking,bg=CARD,fg=PURPLE,wraplength=850,justify='left').pack(anchor='w',pady=(5,0))
        return panel

    def lb_use_public_row(self,row):
        """Only auto-populate EVM public addresses; never claim BTC vault belongs to Core."""
        coin=str(row.get('coin',''))
        addr=str(row.get('address',''))
        if addr.startswith('0x') and len(addr)==42:
            self.lb_address.set(addr)
            self.lb_source.set('EVM native coin')
            self.lb_balance.set('EVM public address selected. Select matching chain under Connections; refresh to verify on-chain balance.')
        elif coin=='BTC':
            self.lb_balance.set('Standalone BTC vault is NOT connected to a Bitcoin Core wallet. No verified live balance.')
        elif coin=='XMR':
            self.lb_balance.set('Monero address selected. Live XMR balance requires the matching local Monero wallet RPC.')

    def _lb_settings(self):
        source=self.lb_source.get()
        return dict(source=source,btc_url=self.btc_url.get().strip(),btc_cookie=self.btc_cookie.get().strip(),
            btc_wallet=self.btc_name.get().strip(),xmr_url=self.xmr_url.get().strip(),xmr_user=self.xmr_user.get().strip(),
            xmr_password=self.xmr_password.get(),evm_code=self.evm_code.get(),evm_url=self.evm_url.get().strip(),
            evm_address=self.lb_address.get().strip(),evm_contract=self.lb_contract.get().strip())

    @staticmethod
    def _lb_query(settings):
        source=settings['source']
        if source==SOURCES[0]:return snapshot_btc(settings['btc_url'],settings['btc_cookie'],settings['btc_wallet'])
        if source==SOURCES[1]:return snapshot_xmr(settings['xmr_url'],settings['xmr_user'],settings['xmr_password'])
        if source in SOURCES[2:]:
            return snapshot_evm(settings['evm_code'],settings['evm_url'],settings['evm_address'],
                settings['evm_contract'] if source==SOURCES[3] else '')
        raise ValueError('Unknown source')

    def lb_refresh(self):
        if self.lb_closed:return
        if self.lb_inflight:
            self.lb_queued_refresh=True
            return
        settings=self._lb_settings() # snapshot Tk variables on UI thread ONLY
        self.lb_inflight=True
        epoch=self.lb_epoch
        self.lb_balance.set('QUERYING BLOCKCHAIN NODE… (not a predicted balance)')
        def completed(result):self._lb_deliver(epoch,result,False,settings)
        def failed(_kind):self._lb_deliver(epoch,None,True,settings)
        try:
            self.executor.submit(lambda:self._lb_query(settings),completed,failed,
                                 key='balance:'+settings['source'])
        except (QueueSaturated,RuntimeError):
            self.lb_inflight=False
            self.lb_balance.set('BALANCE UNAVAILABLE · Background queue busy; retry shortly')

    def _lb_deliver(self,epoch,result,error,settings):
        self.lb_inflight=False
        # A response from an OLD endpoint/account can never overwrite a newer
        # selection, even when the page epoch has not changed.
        if self.lb_closed or epoch != self.lb_epoch:return
        if self._lb_settings()!=settings:
            self.lb_queued_refresh=True
            self.lb_balance.set('BALANCE UNAVAILABLE · Node or wallet changed; refreshing the current selection')
            self.lb_secondary.set('Old-node response discarded. Do not use a cached amount.')
            self.lb_last_good_monotonic=None
            self.lb_last_good_settings=None
        queued=self.lb_queued_refresh
        self.lb_queued_refresh=False
        if queued:
            self.root.after(0,self.lb_refresh)
            return
        if error:
            self.lb_last_good_monotonic=None
            self.lb_last_good_settings=None
            self.lb_balance.set('BALANCE UNAVAILABLE · Node offline, wrong account/network or RPC failed')
            self.lb_secondary.set('No verified amount. Previous values are not current. Check Connections and retry.')
            self.lb_tracking.set('Transaction status unavailable; check the original wallet before retrying.') if self.lb_last_tx else None
            return
        self.lb_last_good_monotonic=time.monotonic()
        self.lb_last_good_settings=settings.copy()
        self.lb_balance.set(f"{result.currency}  •  AVAILABLE: {result.available}  •  WALLET TOTAL: {result.total}")
        self.lb_secondary.set(f"{result.secondary_label}: {result.secondary}  |  Height: {result.height}  |  UTC: {result.timestamp_utc}\n{result.pending_note}")
        if self.lb_last_tx and self.lb_last_source==settings['source']:
            txid=self.lb_last_tx
            def task():
                return transaction_state(settings['source'],txid,**{k:settings[k] for k in (
                    'btc_url','btc_cookie','btc_wallet','xmr_url','xmr_user','xmr_password','evm_code','evm_url')})
            try:
                self.executor.submit(task,lambda state:self._lb_tx_deliver(epoch,txid,state),
                    lambda _kind:self._lb_tx_deliver(epoch,txid,'STATUS UNAVAILABLE — verify independently'),
                    key='tx:'+settings['source']+':'+txid)
            except (QueueSaturated,RuntimeError):
                self._lb_tx_deliver(epoch,txid,'STATUS UNAVAILABLE — background work busy')

    def _lb_tx_deliver(self,epoch,txid,state):
        if not self.lb_closed and epoch==self.lb_epoch and txid==self.lb_last_tx:
            self.lb_tracking.set('Last broadcast …'+txid[-12:]+': '+state)

    def _lb_tick(self):
        if self.lb_closed:return
        # When auto is disabled or the network stalls, never leave an old
        # balance displayed as an implicitly current/usable live amount.
        if self.lb_last_good_monotonic is not None and (
                time.monotonic()-self.lb_last_good_monotonic>90 or
                self.lb_last_good_settings!=self._lb_settings()):
            self.lb_last_good_monotonic=None
            self.lb_last_good_settings=None
            self.lb_balance.set('STALE BALANCE · Last observation expired or node/account changed')
            self.lb_secondary.set('Do not use the previously displayed amount. Refresh and verify the network.')
        if self.lb_enabled and not self.lb_inflight and not getattr(self,'pending',False):
            self.lb_refresh()
        self.root.after(self.lb_interval_ms,self._lb_tick)

    def lb_toggle(self):
        self.lb_enabled=not self.lb_enabled
        self._lb_toggle_button.configure(text='STOP AUTO' if self.lb_enabled else 'START AUTO')
        if self.lb_enabled:self.lb_refresh()

    def lb_after_send(self,plan,txid):
        """Broadcast submission is not balance credit, and not confirmation."""
        if plan.kind=='btc':self.lb_source.set(SOURCES[0])
        elif plan.kind=='xmr':self.lb_source.set(SOURCES[1])
        else:
            self.lb_source.set(SOURCES[3] if plan.context.get('token_addr') else SOURCES[2])
            self.evm_code.set(plan.context['code'])
            self.lb_address.set(plan.source)
            if plan.context.get('token_addr'):self.lb_contract.set(plan.context['token_addr'])
        self.lb_last_source=self.lb_source.get()
        self.lb_epoch+=1  # invalidate any pre-broadcast response
        self.lb_last_good_monotonic=None
        self.lb_last_good_settings=None
        self.lb_last_tx=str(txid)
        self.lb_enabled=True
        self.lb_tracking.set('SUBMITTED • Not yet confirmed • …'+str(txid)[-12:]+' • Checking network balance, including fees once recorded.')
        self.lb_balance.set('SUBMITTED • Waiting for node balance. Do not assume a deduction/credit is final.')
        self.lb_refresh()
