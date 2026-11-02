"""Phase 15 — wallet-first financial experience, read-only until signer pages."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from financial_experience import capabilities, observation_display, matching_history, selected_funding_target
from portfolio_engine import distinct_accounts, query_account, Observation, wallet_identity
from unified_wallet import UnifiedAccountRegistry, from_vault_rows, from_watch_rows
from universal_transactions import UniversalTxJournal, display_units
from performance_runtime import QueueSaturated

BG='#07060b'; CARD='#15101e'; GREEN='#47fca3'; MUTED='#a39ab6'; WARN='#ff707a'; PURPLE='#b363ff'

class FinancialExperienceUI:
    def page_money_hub(self):
        self.head('Money Hub / Phase 15',
            'One selected public wallet for Receive, live RPC balance, transaction activity, Send and Add Money. '
            'This view cannot sign transactions, submit payments, or create fiat balances.')
        self._mh_epoch=getattr(self,'_mh_epoch',0)+1
        epoch=self._mh_epoch
        self._mh_page_epoch=epoch
        self._mh_busy=False
        self._mh_selected=None
        self._mh_observation=None
        self._mh_last_config=None
        self._mh_accounts={}
        self.mh_auto=tk.BooleanVar(value=False)
        self.mh_status=tk.StringVar(value='Choose a wallet. No blockchain balance loaded.')
        self.mh_balance=tk.StringVar(value='Total: —    RPC-reported available: —    Unavailable/pending: —')
        self.mh_detail=tk.StringVar(value='No selected account.')
        self.mh_address=tk.StringVar(value='')
        self.mh_activity=tk.StringVar(value='No account selected; local transaction history is not proof of settlement.')
        self.mh_warning=tk.StringVar(value='No connected signer or independently verified recovery.')

        header=tk.Frame(self.content,bg=CARD,padx=14,pady=13);header.pack(fill='x',pady=6)
        tk.Label(header,text='01 / SELECT AN EXISTING WALLET',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.mh_tree=ttk.Treeview(header,columns=('wallet','asset','network','type'),show='headings',height=7,selectmode='browse')
        for col,width in (('wallet',255),('asset',95),('network',155),('type',180)):
            self.mh_tree.heading(col,text=col.upper());self.mh_tree.column(col,width=width,stretch=col=='wallet')
        self.mh_tree.pack(fill='x',pady=8)
        self.mh_tree.bind('<<TreeviewSelect>>',lambda _:self._mh_choose())
        row=tk.Frame(header,bg=CARD);row.pack(fill='x',pady=5)
        ttk.Button(row,text='RELOAD WALLETS',command=self._mh_load).pack(side='left',padx=(0,8))
        ttk.Button(row,text='LINK SIGNER / UNLOCK VAULT',command=lambda:self.show('Unified Wallets')).pack(side='left',padx=(0,8))
        ttk.Button(row,text='CREATE WALLET',command=lambda:self.show('Create Wallet')).pack(side='left')
        tk.Label(header,text='Wallets are public references. Even a connected RPC does not prove an encrypted seed can restore or sign.',
            bg=CARD,fg=WARN,wraplength=950,justify='left').pack(anchor='w',pady=3)

        account=tk.Frame(self.content,bg=CARD,padx=14,pady=13);account.pack(fill='x',pady=6)
        tk.Label(account,text='02 / PUBLIC RECEIVING ADDRESS',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(account,textvariable=self.mh_detail,bg=CARD,fg=PURPLE,justify='left',wraplength=950).pack(anchor='w',pady=6)
        ttk.Entry(account,textvariable=self.mh_address,state='readonly',font=('Consolas',10)).pack(fill='x',pady=5)
        tk.Label(account,textvariable=self.mh_warning,bg=CARD,fg=WARN,wraplength=950,justify='left').pack(anchor='w',pady=5)
        row=tk.Frame(account,bg=CARD);row.pack(fill='x',pady=4)
        ttk.Button(row,text='COPY ADDRESS',command=self._mh_copy).pack(side='left',padx=(0,8))
        ttk.Button(row,text='SHOW QR',command=self._mh_qr).pack(side='left',padx=(0,8))
        ttk.Button(row,text='OPEN RECEIVE',command=lambda:self.show('Receive')).pack(side='left')

        balance=tk.Frame(self.content,bg=CARD,padx=14,pady=13);balance.pack(fill='x',pady=6)
        tk.Label(balance,text='03 / LIVE BLOCKCHAIN BALANCE',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(balance,textvariable=self.mh_balance,bg=CARD,fg=PURPLE,font=('Consolas',11,'bold'),justify='left',wraplength=950).pack(anchor='w',pady=7)
        tk.Label(balance,textvariable=self.mh_status,bg=CARD,fg=MUTED,justify='left',wraplength=950).pack(anchor='w',pady=5)
        row=tk.Frame(balance,bg=CARD);row.pack(fill='x')
        ttk.Button(row,text='REFRESH SELECTED BALANCE',command=self._mh_refresh,style='Accent.TButton').pack(side='left',padx=(0,10))
        ttk.Checkbutton(row,text='AUTO EVERY 30s',variable=self.mh_auto).pack(side='left')
        tk.Label(balance,text='Values are node-reported and can change after reorgs. Pending is total minus reported available, not proof of an incoming payment.',
            bg=CARD,fg=WARN,wraplength=950,justify='left').pack(anchor='w',pady=7)

        history=tk.Frame(self.content,bg=CARD,padx=14,pady=13);history.pack(fill='x',pady=6)
        tk.Label(history,text='04 / SELECTED WALLET ACTIVITY',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(history,textvariable=self.mh_activity,bg=CARD,fg=MUTED,justify='left',wraplength=980).pack(anchor='w',pady=8)
        row=tk.Frame(history,bg=CARD);row.pack(fill='x')
        ttk.Button(row,text='REFRESH LOCAL HISTORY',command=self._mh_history).pack(side='left',padx=(0,9))
        ttk.Button(row,text='OPEN TRANSACTION CENTER',command=lambda:self.show('Universal Transactions')).pack(side='left')

        actions=tk.Frame(self.content,bg=CARD,padx=14,pady=13);actions.pack(fill='x',pady=6)
        tk.Label(actions,text='05 / MONEY ACTIONS — REVIEW REQUIRED',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        row=tk.Frame(actions,bg=CARD);row.pack(fill='x',pady=7)
        ttk.Button(row,text='SEND / SIGNER REVIEW',command=self._mh_send,style='Accent.TButton').pack(side='left',padx=(0,9))
        ttk.Button(row,text='ADD MONEY / BUY CRYPTO',command=self._mh_buy).pack(side='left',padx=(0,9))
        ttk.Button(row,text='CASH OUT / PROVIDER REVIEW',command=self._mh_cashout).pack(side='left')
        tk.Label(actions,text='Send opens an existing chain-specific signing workflow; nothing is transmitted here. '
            'Buy/sell use an external provider that must independently confirm eligibility, fees and settlement. '
            'A provider handoff is NOT a received or completed payment.',
            bg=CARD,fg=WARN,justify='left',wraplength=950).pack(anchor='w',pady=5)
        orders=tk.Frame(self.content,bg=CARD,padx=14,pady=13);orders.pack(fill='x',pady=6)
        tk.Label(orders,text='06 / FUNDING REQUESTS AND FIAT SANDBOX',bg=CARD,fg=GREEN,font=('Consolas',12,'bold')).pack(anchor='w')
        self.mh_orders=tk.StringVar(value='Not loaded. Desktop payment records are not settlement evidence.')
        tk.Label(orders,textvariable=self.mh_orders,bg=CARD,fg=MUTED,justify='left',wraplength=960).pack(anchor='w',pady=7)
        ttk.Button(orders,text='REFRESH REQUESTS',command=self._mh_orders_refresh).pack(anchor='w',pady=4)
        tk.Label(orders,text='The desktop cannot credit bank or crypto balances. Sandbox events, submitted checkout requests, '
            'and local records never mean settled or deposited funds.',bg=CARD,fg=WARN,wraplength=950,justify='left').pack(anchor='w',pady=5)
        self._mh_load()
        self._mh_orders_refresh()
        self.root.after(30_000,lambda:self._mh_tick(epoch))

    def _mh_load(self):
        if self._mh_busy:return
        previous=self._mh_selected.id if self._mh_selected else None
        try:
            accounts=list(UnifiedAccountRegistry().list())
            for path,rows in self.public_unlocked.items():accounts.extend(from_vault_rows(path,rows))
            accounts.extend(from_watch_rows(self.watch))
            accounts=distinct_accounts(accounts)[:250]
        except (ValueError,OSError,KeyError,TypeError):
            accounts=[]
            self.mh_status.set('Public account registry unavailable. No balance or wallet will be guessed.')
        self._mh_accounts={a.id:a for a in accounts}
        self.mh_tree.delete(*self.mh_tree.get_children())
        for a in accounts:self.mh_tree.insert('','end',iid=a.id,values=(a.label,a.asset,a.network,a.kind))
        if previous in self._mh_accounts:
            self.mh_tree.selection_set(previous);self._mh_choose()
        else:self._mh_choose()

    def _mh_choose(self):
        chosen=self.mh_tree.selection()
        new=self._mh_accounts.get(chosen[0]) if chosen else None
        if self._mh_selected != new:
            self._mh_epoch+=1
            self._mh_observation=None
            self._mh_last_config=None
        self._mh_selected=new
        self.mh_address.set(new.address if new else '')
        self.mh_detail.set(f'{new.label} / {new.asset} / {new.network} / {new.kind}' if new else 'Select a public account from the list above.')
        self.mh_warning.set(capabilities(new).warning if new else 'No wallet selected; wallet control is not established.')
        self._mh_render_balance()
        self.mh_activity.set('Local outgoing history not loaded; not an independent blockchain transaction scan.')

    def _mh_config(self):
        return dict(btc_url=self.btc_url.get().strip(),btc_cookie=self.btc_cookie.get().strip(),
            xmr_url=self.xmr_url.get().strip(),xmr_user=self.xmr_user.get().strip(),
            xmr_password=self.xmr_password.get(),evm_code=self.evm_code.get(),evm_url=self.evm_url.get().strip())

    def _mh_render_balance(self):
        acc=self._mh_selected
        if acc is None:
            self.mh_balance.set('Total: —    RPC-reported available: —    Pending/locked: —')
            self.mh_status.set('UNAVAILABLE — no account selected.')
            return
        try:shown=observation_display(acc,self._mh_observation)
        except ValueError:shown=observation_display(acc,None)
        self.mh_balance.set(f"Total: {shown['total']} {acc.asset}     RPC-reported available: {shown['available']}     Pending/locked: {shown['pending']}")
        self.mh_status.set(f"{shown['status']} · Height {shown['height']} · {shown['provider']}. No fiat valuation assumed.")

    def _mh_refresh(self):
        acc=self._mh_selected
        if acc is None:
            self.mh_status.set('Choose a wallet before checking a balance.');return
        if self._mh_busy:return
        if not capabilities(acc).balance_query:
            self.mh_status.set('No supported balance reader. See Chain Expansion or Token Center.');return
        configuration=self._mh_config()
        epoch=self._mh_epoch
        self._mh_observation=None;self._mh_last_config=None;self._mh_render_balance()
        self._mh_busy=True
        self.mh_status.set('RPC request in progress — no cached balance is being shown.')
        def work():
            snap=query_account(acc,configuration)
            return Observation.from_snapshot(acc,snap)
        def done(result):
            self._mh_busy=False
            if self.current_page!='Money Hub' or epoch!=self._mh_epoch:return
            if self._mh_selected!=acc or self._mh_config()!=configuration:
                self._mh_observation=None
                self.mh_status.set('Account or connection changed; stale RPC reply discarded.')
                return
            self._mh_observation=result
            self._mh_last_config=configuration
            self._mh_render_balance()
        def failed(_kind):
            self._mh_busy=False
            if self.current_page=='Money Hub' and epoch==self._mh_epoch:
                self._mh_observation=None;self._mh_render_balance()
                self.mh_status.set('Balance unavailable — RPC identity, synchronization or connection could not be verified.')
        try:self.executor.submit(work,done,failed,lane='financial',key='moneyhub-balance')
        except (QueueSaturated,RuntimeError):
            self._mh_busy=False;self.mh_status.set('Balance unavailable — worker queue full.')

    def _mh_tick(self,epoch):
        if self.current_page!='Money Hub' or epoch!=getattr(self,'_mh_page_epoch',-1):return
        if self.mh_auto.get() and not self._mh_busy:
            self._mh_refresh()
        self.root.after(30_000,lambda:self._mh_tick(epoch))

    def _mh_copy(self):
        if not self._mh_selected:return
        self.copy_public(self._mh_selected.address)

    def _mh_qr(self):
        acc=self._mh_selected
        if acc is None:return
        # Reuse the already-implemented public-address-only QR view.
        from wallet_funding import FundingTarget
        self._hub_target=FundingTarget(acc.asset,acc.address,acc.network,acc.kind,acc.label)
        self._hub_show_qr()

    def _mh_send(self):
        acc=self._mh_selected
        if acc is None:return
        action=capabilities(acc)
        if not action.send_page:
            messagebox.showwarning('No in-app signer','Address-only or watch-only wallet. No verified in-app signing route. Use compatible trusted wallet software.',parent=self.root)
            return
        if not messagebox.askyesno('SIGNER REVIEW — NO TRANSFER YET',
            f'{acc.asset} / {acc.network}\nSource: {acc.address}\n\n'
            'Opening the chain-specific signing screen. Confirm signer ownership, recovery, full recipient, network, fees and amount there. '
            'Nothing is signed or broadcast by this shortcut.',parent=self.root):return
        self.show(action.send_page)
        if action.send_page=='BTC Phase 1':
            self.p1_network.set(acc.network);self.p1_wallet.set(acc.source)
            self.p1_status.set('Wallet selected from Money Hub. Recheck Core node ownership and recovery before sending.')
        elif action.send_page=='EVM Phase 2':
            self.p2_chain.set(acc.network);self.p2_keystore.set(acc.source)
            self._p23_set(self.p2_output,'Public wallet selected: '+acc.address+'\nRecheck RPC, signer password and network before any transaction.')
        else:
            self.p3_network.set(acc.network)
            self._p23_set(self.p3_output,'Public wallet selected: '+acc.address+'\nVerify wallet-RPC ownership and spendability before sending.')

    def _mh_buy(self):
        acc=self._mh_selected
        if acc is None:return
        observed=(self._mh_observation is not None and self._mh_last_config==self._mh_config())
        eligible=capabilities(acc,fresh=bool(observed and self._mh_observation.fresh()),observed=observed)
        if not eligible.buy_route:
            messagebox.showwarning('Funding verification required',
                'Fiat funding shortcut requires a freshly checked mainnet BTC Core or Monero RPC account. '
                'Other addresses require independent recovery and provider-network verification before funding.',parent=self.root)
            return
        self._hub_target=selected_funding_target(acc)
        self.show('Phase 4 Funding')

    def _mh_cashout(self):
        acc=self._mh_selected
        if acc is None:return
        observed=(self._mh_observation is not None and self._mh_last_config==self._mh_config())
        eligible=capabilities(acc,fresh=bool(observed and self._mh_observation.fresh()),observed=observed)
        if not eligible.buy_route:
            messagebox.showwarning('Unverified or unsupported sell destination',
                'The Cash Out shortcut is limited to freshly checked mainnet BTC Core and Monero RPC wallets. '
                'Unverified vaults, watch-only accounts and testnets are not treated as spendable.',parent=self.root)
            return
        if not messagebox.askyesno('EXTERNAL CASH OUT — NO TRANSFER',
            f'Account: {acc.asset} / {acc.network}\nAddress: {acc.address}\n\n'
            'Cash Out is an external provider workflow, NOT an in-app bank withdrawal. '
            'The provider must create an order and supply a VERIFIED UNIQUE deposit address. '
            'NO cryptocurrency is transferred by opening the provider page. Continue?',parent=self.root):return
        self._hub_target=selected_funding_target(acc)
        self.show('Phase 4 Funding')

    def _mh_history(self):
        acc=self._mh_selected
        if not acc:return
        # Read only existing local projection. No transaction broadcast or journal writes.
        try:
            data=UniversalTxJournal().list(limit=120)
            rows=matching_history(data,acc,limit=8)
            if not rows:
                self.mh_activity.set('No matching local outgoing records. This is NOT a complete on-chain incoming history.')
            else:
                lines=[]
                for row in rows:
                    try:amount=display_units(row['amount_units'],row['decimals'])
                    except (ValueError,KeyError):continue
                    lines.append(f"{row['asset']} {amount} → {row['destination'][:15]}… / {row['status']} / {row['confirmations']} confirmations")
                self.mh_activity.set('\n'.join(lines) if lines else 'No valid local outgoing records.')
        except (OSError,ValueError,KeyError):
            self.mh_activity.set('Local transaction journal unavailable. No completion status inferred.')

    def _mh_orders_refresh(self):
        # This is LOCAL status only. NO network payments or provider credentials.
        try:
            from funding_orders import FundingOrders
            from phase4_ui import _orders_path
            from banking_rails import RailRequests,printable_amount
            from banking_rails_ui import _store_path
            funding=FundingOrders(_orders_path()).list(5)
            rails=RailRequests(_store_path()).list(5)
            lines=['CRYPTO PURCHASE HANDOFFS (unverified):']
            lines += [f"{r['asset']} / {r['chain']} · {r['amount']} {r['fiat']} · {r['status']}" for r in funding]
            if not funding:lines.append('None recorded')
            lines.append('FIAT REQUESTS (sandbox only):')
            lines += [f"{r['flow']} {printable_amount(r['minor'],r['currency'])} {r['currency']} · {r['status']}" for r in rails]
            if not rails:lines.append('None recorded')
            self.mh_orders.set('\n'.join(lines))
        except (OSError,ValueError,KeyError,TypeError):
            self.mh_orders.set('Local request history unavailable — never assume a payment was settled.')
