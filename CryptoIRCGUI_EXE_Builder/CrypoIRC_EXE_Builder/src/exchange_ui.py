"""Interactive Tkinter fiat FX and crypto on-ramp guidance.

This is NOT a money transmitter, bank, exchange, card processor, or custody service.
It deliberately never collects card PAN/CVV, bank credentials, or seed phrases;
never initiates unapproved transactions and never credits local ledgers.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from core.exchange_engine import (
 CURRENCY_CATALOG, FIAT_CODES, CRYPTO_IDS, STABLECOIN_NETWORKS,
 FIAT_PROVIDERS, CRYPTO_ONRAMPS, ExchangeError, fiat_estimate,
 crypto_estimate, quote_summary, positive_amount,
)
from core import fiat_registry

BG='#07060b'; CARD='#15101e'; FG='#f2edf9'; ACCENT='#47fca3'; MUTED='#a39ab6'; WARN='#ff707a'

FIAT_CHOICES=[f'{c} — {CURRENCY_CATALOG[c]["name"]}' for c in FIAT_CODES]
COIN_CHOICES=[f'{c} — {CRYPTO_IDS[c]}' for c in CRYPTO_IDS]

def code(selected:str) -> str:return selected.split(' — ',1)[0]

def disclaimer_text() -> str:
    return ('Reference quotes are NOT payment offers. Live card charging, currency exchange, KYC, '
            'custody, delivery, refunds, fees and payout depend on an authorized provider. '
            'This application never stores card numbers, CVVs, or banking passwords and '
            'does NOT automatically credit local fiat ledgers or send crypto.')


class ExchangeUI:
    def page_currency_exchange(self):
        self.head('Currency Exchange & Add Money',
                  '164 ISO fiat selections • indicative cross-currency rates • crypto market previews • safe provider handoffs')
        tabs=ttk.Notebook(self.content);tabs.pack(fill='both',expand=True,pady=4)
        for title,func in (
            ('Convert & Quote',self._exchange_quote_tab),
            ('Add Money / Card',self._exchange_fund_tab),
            ('Receive & Auto-Convert',self._exchange_receive_tab),
            ('Supported Routes',self._exchange_help_tab),
        ):
            frame=tk.Frame(tabs,bg=BG,padx=11,pady=12)
            tabs.add(frame,text='  '+title+'  ')
            func(frame)

    def _fx_panel(self,frame,title):
        c=tk.Frame(frame,bg=CARD,padx=17,pady=14)
        c.pack(fill='x',pady=5)
        self._lab(c,title,True).pack(anchor='w')
        return c

    def _note_wrap(self,c,text,color=MUTED):
        tk.Label(c,bg=CARD,fg=color,text=text,justify='left',wraplength=750,font=('Segoe UI',9)).pack(anchor='w',pady=6)

    def _fx_code(self,val):return code(val.get())

    def _currency_selector(self,c,label,var):
        return self._select(c,label,var,FIAT_CHOICES,width=56)

    def _exchange_quote_tab(self,f):
        c=self._fx_panel(f,'STEP 1 — SOURCE MONEY → DESTINATION CURRENCY OR CRYPTO')
        self.xq_from=tk.StringVar(value=next(x for x in FIAT_CHOICES if x.startswith('INR —')))
        self.xq_kind=tk.StringVar(value='Fiat currency')
        self.xq_fiat_to=tk.StringVar(value=next(x for x in FIAT_CHOICES if x.startswith('USD —')))
        self.xq_coin=tk.StringVar(value=COIN_CHOICES[0]);self.xq_amount=tk.StringVar(value='1000')
        self._currency_selector(c,'I currently have (source fiat currency)',self.xq_from)
        self._select(c,'Convert into',self.xq_kind,['Fiat currency','Cryptocurrency / stablecoin'],self._refresh_fx_destination)
        self.xq_dest_holder=tk.Frame(c,bg=CARD);self.xq_dest_holder.pack(fill='x')
        self._entry(c,'Amount in source currency',self.xq_amount)
        self.xq_route=tk.StringVar(value='Wise')
        self._select(c,'Execution provider / external handoff',self.xq_route,list(FIAT_PROVIDERS))
        self._refresh_fx_destination()
        self._btn(c,'GET REFERENCE RATE (NO TRANSACTION)',self._run_exchange_quote,True).pack(anchor='w',pady=10)
        self.xq_result=tk.StringVar(value='Select source and destination then request an indicative rate. No fee or payout guarantee.')
        tk.Label(c,textvariable=self.xq_result,bg=CARD,fg=FG,justify='left',wraplength=740,font=('Consolas',10)).pack(anchor='w',pady=8)
        self._btn(c,'OPEN PROVIDER FOR ACTUAL QUOTE',self._open_fx_provider).pack(anchor='w',pady=7)
        self._note_wrap(c,'Rates by ExchangeRate-API • https://www.exchangerate-api.com — daily indicative rates. Crypto estimates: CoinGecko. No hidden card/FX fee assumptions.',WARN)

    def _refresh_fx_destination(self):
        for x in self.xq_dest_holder.winfo_children():x.destroy()
        if self.xq_kind.get()=='Fiat currency':
            self._currency_selector(self.xq_dest_holder,'Target currency',self.xq_fiat_to)
        else:
            self._select(self.xq_dest_holder,'Target cryptocurrency',self.xq_coin,COIN_CHOICES)
            self._note_wrap(self.xq_dest_holder,'Crypto prices indicate market value; only provider-generated on-ramp orders can purchase tokens.')

    def _run_exchange_quote(self):
        src=self._fx_code(self.xq_from); amount=self.xq_amount.get();kind=self.xq_kind.get()
        dest=self._fx_code(self.xq_fiat_to) if kind=='Fiat currency' else self._fx_code(self.xq_coin)
        def work():return (fiat_estimate(amount,src,dest) if kind=='Fiat currency' else crypto_estimate(amount,src,dest))
        self.run_job(work,lambda quote:self.xq_result.set(quote_summary(quote)),
                     'Getting indicative market reference — no transactions initiated...')

    def _open_fx_provider(self):
        provider=self.xq_route.get()
        if self.xq_kind.get()!='Fiat currency':
            return messagebox.showwarning('Different provider required',
              'Crypto purchases use a regulated on-ramp selected under Add Money / Card, not a general fiat FX site.')
        src=self._fx_code(self.xq_from); dst=self._fx_code(self.xq_fiat_to)
        try:positive_amount(self.xq_amount.get(),src)
        except ExchangeError as e:return messagebox.showerror('Invalid amount',str(e))
        if not messagebox.askyesno('External FX provider',
            f'You will leave CRYPTO for {provider}.\n\nSOURCE: {self.xq_amount.get()} {src}\nTARGET: {dst}\n\nThe provider must check currency-pair eligibility, fees, recipient details and actual payout. No transaction has occurred here.\n\nOpen official website?'):return
        webbrowser.open(FIAT_PROVIDERS[provider])
        self.status.set('EXTERNAL PROVIDER OPENED • No money moved / no local balance credited')

    def _exchange_fund_tab(self,f):
        c=self._fx_panel(f,'STEP 2 — ADD MONEY USING A LICENSED PAYMENT PROVIDER')
        self.af_destination=tk.StringVar(value='Crypto wallet / blockchain address')
        self._select(c,'Deposit destination',self.af_destination,
                     ['Crypto wallet / blockchain address','Fiat provider account (real funds)'],self._update_fund_fields)
        self.af_source=tk.StringVar(value=next(x for x in FIAT_CHOICES if x.startswith('USD —')))
        self._currency_selector(c,'Currency your card or bank pays in',self.af_source)
        self.af_amount=tk.StringVar(value='50.00');self._entry(c,'Payment amount (reference only)',self.af_amount)
        self.af_method=tk.StringVar(value='Debit / credit card (provider checkout)')
        self._select(c,'Funding method',self.af_method,
                     ['Debit / credit card (provider checkout)', 'Apple Pay / Google Pay (if offered)',
                      'Bank transfer / ACH (if offered)', 'Existing approved provider balance'])
        self.af_dynamic=tk.Frame(c,bg=CARD);self.af_dynamic.pack(fill='x')
        self.af_note=tk.StringVar(value='')
        self._update_fund_fields()
        self._btn(c,'REVIEW FUNDING ROUTE — NO CHARGE',self._fund_review,True).pack(anchor='w',pady=10)
        self._note_wrap(c,disclaimer_text(),WARN)
        self._note_wrap(c,'Never enter a payment card number, CVV, BIP39 phrase or banking password in this app. Complete identity verification and card checkout only on the official provider page.')

    def _update_fund_fields(self):
        for child in self.af_dynamic.winfo_children():child.destroy()
        self.af_is_crypto=self.af_destination.get().startswith('Crypto')
        if self.af_is_crypto:
            self.af_coin=tk.StringVar(value='BTC');self.af_network=tk.StringVar(value='Bitcoin mainnet')
            self.af_provider=tk.StringVar(value='Stripe Crypto Onramp')
            self._select(self.af_dynamic,'Crypto asset to receive',self.af_coin,list(CRYPTO_IDS),self._refresh_onramp_network)
            self._select(self.af_dynamic,'Blockchain network — must match address',self.af_network,['Bitcoin mainnet'])
            self.af_net_widgets=self.af_dynamic.winfo_children()[-1]
            self._refresh_onramp_network()
            self._select(self.af_dynamic,'External on-ramp provider',self.af_provider,list(CRYPTO_ONRAMPS))
            self.af_address=tk.StringVar(value='')
            self._entry(self.af_dynamic,'Your public RECEIVING address (never a seed or private key)',self.af_address)
            self.af_wallet_rows=self._public_rows()
            self.af_wallet_options=['Manual — enter public address']+[
                f"{r['coin']} | {r['kind']} | {r['label']} | …{r['address'][-10:]}" for r in self.af_wallet_rows]
            self.af_wallet_choice=tk.StringVar(value=self.af_wallet_options[0])
            self._select(self.af_dynamic,'Choose wallet from THIS PC / USB vault or watch-only list',
                         self.af_wallet_choice,self.af_wallet_options,self._use_selected_funding_wallet)
            self._note_wrap(self.af_dynamic,'If a wallet is missing, unlock its PUBLIC addresses in Wallets first. Only a public address is used. The application never exports seeds to an on-ramp.',WARN)
            self._note_wrap(self.af_dynamic,'Find your address in Receive. Verify the exact chain and token contract/associated account in trusted wallet software before purchase.',WARN)
        else:
            self.af_provider=tk.StringVar(value='Wise')
            self._select(self.af_dynamic,'Existing licensed bank / payment provider',self.af_provider,list(FIAT_PROVIDERS))
            ledgers=fiat_registry.load()
            self.af_ledger=tk.StringVar(value='(no ledger linked)')
            self._select(self.af_dynamic,'Local fiat ledger label (bookkeeping only)',self.af_ledger,['(no ledger linked)']+ledgers)
            self._note_wrap(self.af_dynamic,'CRYPTO does not issue stored-value balances or bank accounts. This route opens the provider to add money to YOUR existing account; ledger labels are never actual fund destinations.',WARN)

    def _use_selected_funding_wallet(self):
        idx=self.af_wallet_options.index(self.af_wallet_choice.get())
        if idx==0:return
        row=self.af_wallet_rows[idx-1]
        coin=self.af_coin.get();network=self.af_network.get()
        # Do not silently use a USDT-on-Tron vault as USDT-on-Ethereum, for example.
        exact=(row['coin']==coin) if coin not in STABLECOIN_NETWORKS else (
            row['coin'].startswith(coin+'-') and row.get('network')==network)
        if not exact:
            self.af_wallet_choice.set(self.af_wallet_options[0]);self.af_address.set('')
            return messagebox.showerror('Wrong crypto or network',
                f'The selected public wallet is {row["coin"]} / {row.get("network", "unknown")}.\n'
                f'You selected {coin} / {network}. Do not assume the addresses are interchangeable.')
        self.af_address.set(row['address'])

    def _refresh_onramp_network(self):
        if not self.af_is_crypto:return
        coin=self.af_coin.get()
        networks=(STABLECOIN_NETWORKS.get(coin) or
                  {'BTC':('Bitcoin mainnet',),'ETH':('Ethereum mainnet',),'XMR':('Monero mainnet',),
                   'SOL':('Solana mainnet',),'TRX':('Tron mainnet',),'BNB':('BNB Smart Chain',),
                   'LTC':('Litecoin mainnet',)}.get(coin,(coin+' native network',)))
        self.af_network.set(networks[0])
        if hasattr(self,'af_wallet_choice'):self.af_wallet_choice.set('Manual — enter public address')
        if hasattr(self,'af_address'):self.af_address.set('')
        for child in self.af_net_widgets.winfo_children():
            if isinstance(child,ttk.Combobox):child.configure(values=list(networks))

    def _fund_review(self):
        src=self._fx_code(self.af_source)
        try: positive_amount(self.af_amount.get(),src)
        except ExchangeError as e:return messagebox.showerror('Invalid amount',str(e))
        provider=self.af_provider.get()
        if self.af_is_crypto:
            address=self.af_address.get().strip()
            if not address or len(address)>160 or any(c.isspace() for c in address):
                return messagebox.showerror('Receiving address required',
                    'Enter a public receiving address and verify its network outside this app. Do not enter a private key or seed.')
            if any(c in address.lower() for c in (' ','abandon ','seed ','private')):
                return messagebox.showerror('Unsafe input','Never supply a secret recovery phrase as an address')
            target=self.af_coin.get(); net=self.af_network.get();url=CRYPTO_ONRAMPS[provider]
            msg=(f'You want to pay {self.af_amount.get()} {src} using {self.af_method.get()}.\n'
                 f'Requested crypto: {target} on {net}.\n'
                 f'Your public wallet address ends in: …{address[-8:]}\n\n'
                 'The provider must independently verify address, network, token, fiat currency, country and payment-method availability.\n'
                 'A reference quote is not a purchase. The provider alone will show an executable quote, fees and confirmation.\n'
                 'CRYPTO will NOT transmit the address or any sensitive data automatically. You must re-enter and verify it inside the provider flow.')
        else:
            target='existing '+provider+' provider account';url=FIAT_PROVIDERS[provider]
            msg=(f'Add {self.af_amount.get()} {src} to your {target}.\n'
                 'Only the approved provider may charge your card, verify account ownership and credit its real balance.\n'
                 'Your local CRYPTO fiat ledger is tracking-only and WILL NOT receive or reflect funds automatically.')
        if messagebox.askyesno('REVIEW — PROVIDER HANDOFF ONLY',msg+'\n\nOpen official provider website?'):
            webbrowser.open(url)
            self.status.set('FUNDING HANDOFF OPENED • NO CARD CHARGE OR WALLET CREDIT IN CRYPTO')

    def _exchange_receive_tab(self,f):
        c=self._fx_panel(f,'RECEIVE IN YOUR PREFERRED CURRENCY — CONVERSION REQUEST PREVIEW')
        self._note_wrap(c,
            'Example: sender pays INR; you want USD. Or sender pays GBP; you want ETH. This configures a preference and estimates conversion. Automatic settlement requires a provider that explicitly supports the corridor, payout and currency pair.',WARN)
        self.rv_in=tk.StringVar(value=next(x for x in FIAT_CHOICES if x.startswith('INR —')))
        self.rv_dest_kind=tk.StringVar(value='Fiat provider account')
        self.rv_dest_currency=tk.StringVar(value=next(x for x in FIAT_CHOICES if x.startswith('USD —')))
        self.rv_dest_coin=tk.StringVar(value='ETH')
        self._currency_selector(c,'Currency sender intends to pay',self.rv_in)
        self._select(c,'I want to receive as',self.rv_dest_kind,
                     ['Fiat provider account','Crypto wallet'],self._refresh_receive_target)
        self.rv_target_holder=tk.Frame(c,bg=CARD);self.rv_target_holder.pack(fill='x')
        self.rv_amount=tk.StringVar(value='1000');self._entry(c,'Sender amount (indicative)',self.rv_amount)
        self._refresh_receive_target()
        self._btn(c,'PREVIEW EXPECTED RECEIPT (NO INCOMING PAYMENT)',self._receive_quote,True).pack(anchor='w',pady=10)
        self.rv_result=tk.StringVar(value='No receive request or funds received. Use a verified payment provider to collect and convert money.')
        tk.Label(c,bg=CARD,fg=FG,justify='left',textvariable=self.rv_result,wraplength=740,font=('Consolas',10)).pack(anchor='w',pady=5)
        self._note_wrap(c,'Receiving money does not auto-convert by itself: it requires a provider to collect the payment, execute FX or purchase crypto, and settle to your verified account/address. No deposit is credited here.')

    def _refresh_receive_target(self):
        for child in self.rv_target_holder.winfo_children():child.destroy()
        if self.rv_dest_kind.get()=='Fiat provider account':
            self._currency_selector(self.rv_target_holder,'Preferred received fiat currency',self.rv_dest_currency)
            self.rv_receive_provider=tk.StringVar(value='Wise')
            self._select(self.rv_target_holder,'Provider must handle conversion/settlement',self.rv_receive_provider,list(FIAT_PROVIDERS))
        else:
            self._select(self.rv_target_holder,'Desired cryptocurrency',self.rv_dest_coin,list(CRYPTO_IDS))
            self.rv_receive_provider=tk.StringVar(value='Stripe Crypto Onramp')
            self._select(self.rv_target_holder,'Crypto on-ramp provider',self.rv_receive_provider,list(CRYPTO_ONRAMPS))
            self._note_wrap(self.rv_target_holder,'Verify destination address and chain with the receiving wallet and provider. This preview does not create a payable on-ramp link.')

    def _receive_quote(self):
        src=self._fx_code(self.rv_in);amount=self.rv_amount.get()
        if self.rv_dest_kind.get()=='Fiat provider account':
            dst=self._fx_code(self.rv_dest_currency)
            work=lambda:fiat_estimate(amount,src,dst)
        else:
            dst=self.rv_dest_coin.get()
            work=lambda:crypto_estimate(amount,src,dst)
        self.run_job(work,lambda quote:self.rv_result.set(quote_summary(quote)),
                     'Fetching reference rate, not receiving any money...')

    def _exchange_help_tab(self,f):
        c=self._fx_panel(f,'HOW THE PAYMENT ROUTES WORK')
        for title,detail in (
          ('INR → USD (bank / fiat)','View indicative conversion here, then log into an eligible licensed FX provider and obtain a final quote. Provider sends USD to a verified recipient. No wallet credit inside CRYPTO.'),
          ('GBP → EUR (fiat)','Same process. Pair availability, beneficiary details, FX spread and settlement times depend on the provider and destination country.'),
          ('USD → BTC / ETH / USDT','Use an authorized fiat-to-crypto on-ramp. The provider collects funds and sends crypto to a compatible, confirmed public wallet address on the exact selected network.'),
          ('Card → USD / GBP account','Fund an EXISTING provider-issued account, if that provider permits card deposits for your account type. General-purpose stored-value wallets cannot be created solely by this Tkinter application.'),
          ('Someone pays INR; I receive USD','A provider can support a request/recipient payout using currency conversion, if available. A generic wallet cannot automatically swap incoming unrelated fiat and crypto.'),
          ('Provider-verified completion','Only provider webhooks / authenticated API reconciliation or blockchain confirmation can establish receipt. Local notes, reference quotes and payment links are not proof of money.'),
          ('Currency universe','164 ISO-4217 fiat selections for reference quoting. There is NO guarantee all 164 are tradable or funded by card. Unsupported rate pairs fail explicitly.'),
          ('Privacy / security','We never collect PAN/CVV, bank login, 2FA OTP, wallet seeds, or secret keys for payment quotes. Provider redirects use fixed official HTTPS hosts.'),
        ):
            self._lab(c,title,True).pack(anchor='w',pady=(11,2)); self._note_wrap(c,detail)
        self._note_wrap(c,'Reference FX data attribution: Rates By ExchangeRate-API — https://www.exchangerate-api.com. Cryptocurrency reference prices: https://www.coingecko.com.',WARN)
