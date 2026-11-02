"""Tkinter interface for registered, provider-backed payment requests and bank handoffs."""
from __future__ import annotations
import os, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from core import fiat_payments as fp, fiat_registry
from core.assets import FIAT

BG='#07060b'; CARD='#15101e'; FG='#f2edf9'; MUTED='#a39ab6'; ACCENT='#47fca3'; WARN='#ff707a'

class FiatPaymentsUI:
    def page_fiat_payments(self):
        self.head('Fiat payments & transfers','11 payment method choices • real merchant checkout where supported • bank and P2P handoffs elsewhere')
        tabs=ttk.Notebook(self.content);tabs.pack(fill='both',expand=True)
        for title,build in (
            ('Receive / Request',self._fiat_receive_tab),
            ('Send / Exchange',self._fiat_send_tab),
            ('Verify a Payment',self._fiat_verify_tab),
            ('Provider Connections',self._fiat_connections_tab)):
            frame=tk.Frame(tabs,bg=BG,padx=10,pady=12)
            tabs.add(frame,text='  '+title+'  ')
            build(frame)

    def _fiat_receive_tab(self,frame):
        c=tk.Frame(frame,bg=CARD,padx=18,pady=14);c.pack(fill='x',pady=3)
        self._lab(c,'REQUEST MONEY FROM A REAL PROVIDER',True).pack(anchor='w')
        self.fiat_pay_method=tk.StringVar(value='Stripe Checkout')
        self._select(c,'Provider / payment method',self.fiat_pay_method,list(fp.METHODS),self._fiat_method_changed)
        self.fiat_pay_mode=tk.StringVar(value='sandbox')
        self._select(c,'Mode (use sandbox first)',self.fiat_pay_mode,['sandbox','live'])
        ledgers=fiat_registry.load()
        self.fiat_pay_ledger=tk.StringVar(value=ledgers[0] if ledgers else '(not linked)')
        self._select(c,'Related fiat ledger (organizational label only; no automatic credit)',self.fiat_pay_ledger,['(not linked)']+ledgers)
        self.fiat_pay_currency=tk.StringVar(value='USD')
        self._select(c,'Request currency',self.fiat_pay_currency,sorted(fp.CURRENCIES))
        self.fiat_pay_amount=tk.StringVar(value='10.00')
        self._entry(c,'Exact amount to request',self.fiat_pay_amount)
        self.fiat_pay_memo=tk.StringVar(value='Payment request')
        self._entry(c,'Memo / description (never bank details)',self.fiat_pay_memo)
        self.fiat_public_link=tk.StringVar(value='')
        self._entry(c,'Optional official public payment link (Cash App/Wise/Venmo; no banking URLs)',self.fiat_public_link)
        self.fiat_pay_password=tk.StringVar()
        self._entry(c,'Encryption password for payment receipt file (14+ characters)',self.fiat_pay_password,True)
        self.fiat_pay_folder=tk.StringVar(value=str(Path.home()/'CryptoWallets'/'FiatPayments'))
        self._entry(c,'Encrypted receipt folder (PC or selected USB path)',self.fiat_pay_folder)
        rr=tk.Frame(c,bg=CARD);rr.pack(fill='x',pady=8)
        self._btn(rr,'Select USB / folder',self._fiat_pick_folder).pack(side='left',padx=(0,8))
        self._btn(rr,'GENERATE PROVIDER PAYMENT REQUEST',self._fiat_create_link,True).pack(side='left',padx=(0,8))
        self._btn(rr,'Open provider dashboard',self._fiat_open_receive_provider).pack(side='left')
        self.fiat_pay_hint=tk.StringVar()
        tk.Label(c,textvariable=self.fiat_pay_hint,justify='left',wraplength=730,fg=WARN,bg=CARD).pack(anchor='w',pady=5)
        self._fiat_method_changed()
        d=tk.Frame(frame,bg=CARD,padx=18,pady=14);d.pack(fill='x',pady=12)
        self._lab(d,'REQUEST STATUS',True).pack(anchor='w')
        self.info(d,'Payment links do not prove payment. A receipt stays pending until a matching provider API status is checked. Provider funds can still be refunded, disputed, or withheld; no balance is automatically credited.',WARN)
        self.fiat_pay_result=tk.StringVar(value='No request generated this session.')
        tk.Label(d,textvariable=self.fiat_pay_result,fg=FG,bg=CARD,wraplength=740,justify='left').pack(anchor='w')
        self.fiat_pay_url=''
        self._btn(d,'Copy last checkout link',self._fiat_copy_link).pack(anchor='w',pady=7)

    def _fiat_method_changed(self):
        m=self.fiat_pay_method.get()
        self.fiat_pay_hint.set(fp.METHODS[m][1]+'\n'+fp.HINTS[m]+'\n'+fp.config_status(m))

    def _fiat_pick_folder(self):
        path=filedialog.askdirectory(title='Choose directory on PC or USB for encrypted payment request files')
        if path:self.fiat_pay_folder.set(path)

    def _fiat_create_link(self):
        method=self.fiat_pay_method.get()
        is_external=method in fp.EXTERNAL_LINK_HOSTS
        mode=self.fiat_pay_mode.get(); amount=self.fiat_pay_amount.get().strip();currency=self.fiat_pay_currency.get()
        memo=self.fiat_pay_memo.get().strip();folder=self.fiat_pay_folder.get().strip(); pw=self.fiat_pay_password.get()
        try:
            fp.amount_minor(amount,currency)
            if len(pw)<14:raise fp.PaymentError('Use an encryption password of at least 14 characters')
            if not Path(folder).expanduser().is_absolute():raise fp.PaymentError('Choose an absolute PC / USB path')
            if not os.path.isdir(folder):
                if not messagebox.askyesno('Create receipt directory',f'Create encrypted payment record folder?\n{folder}'):
                    return
            if not messagebox.askyesno('Review provider payment request',
                f'Method: {method}\nMode: {"EXTERNAL / UNVERIFIED" if is_external else mode.upper()}\nAmount: {amount} {currency}\nMemo: {memo}\nRecord folder: {folder}\n\n'+
                ('EXTERNAL REFERENCE ONLY. This will NOT send or receive funds. Continue?' if is_external else 'LIVE checkout may charge real people. Continue?' if mode=='live' else 'Sandbox test only. Continue?')):return
        except Exception as e:messagebox.showerror('Invalid request',str(e));return
        self.fiat_pay_password.set('')
        public_link=self.fiat_public_link.get().strip()
        def work():
            rec=(fp.make_external_request(method,amount,currency,memo,public_link)
                 if is_external else fp.create_request(method,amount,currency,memo,mode))
            rec['related_fiat_ledger']=self.fiat_pay_ledger.get()
            try:path=fp.new_payment_file(folder,pw,rec)
            except Exception:
                # Request may exist remotely; never silently retry a POST.
                raise fp.PaymentError('Provider request may have been created, but its encrypted local record was NOT saved. Check provider dashboard before trying again.')
            return (rec,path)
        def complete(result):
            rec,path=result
            self.fiat_pay_url=rec['checkout_url']
            self.fiat_pay_result.set(('EXTERNAL REFERENCE — UNVERIFIED' if is_external else 'CREATED — NOT PAID')+'\nSaved: '+path+'\nOfficial link: '+(rec['checkout_url'] or '(none; use provider app)'))
            self.status.set('REQUEST CREATED • UNPAID • '+method)
            messagebox.showinfo('Payment request created','Saved encrypted request to:\n'+path+'\n\nThis is NOT a confirmation of received money. External records cannot be API-verified.')
        self.run_job(work,complete,'Creating hosted checkout using provider API...')

    def _fiat_copy_link(self):
        if not getattr(self,'fiat_pay_url',''):return messagebox.showwarning('No link','Create a checkout link first')
        self.root.clipboard_clear();self.root.clipboard_append(self.fiat_pay_url)
        self.status.set('Checkout URL copied. A link is NOT proof of payment.')

    def _fiat_open_receive_provider(self):
        method=self.fiat_pay_method.get()
        urls={
            'Stripe Checkout':'https://dashboard.stripe.com/',
            'PayPal Checkout':'https://www.paypal.com/',
            'Square Checkout':'https://squareup.com/dashboard/',
            'Cash App Pay (Square)':'https://squareup.com/dashboard/',
            'Cash App Personal (external)':'https://cash.app/',
            'Venmo (PayPal)':'https://www.paypal.com/',
            'Wise':'https://wise.com/',
            'Revolut Merchant':'https://business.revolut.com/',
            'Zelle (your bank)':'https://www.zellepay.com/',
            'ACH bank transfer':'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
            'Bank wire / SWIFT':'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
        }
        if messagebox.askyesno('Open official provider','Open provider or information site in your browser? This does not initiate a transfer.'):
            webbrowser.open(urls[method])

    def _fiat_send_tab(self,frame):
        c=tk.Frame(frame,bg=CARD,padx=18,pady=18);c.pack(fill='x')
        self._lab(c,'SEND FIAT / CURRENCY EXCHANGE',True).pack(anchor='w')
        self.info(c,'This suite cannot move money between PayPal, Cash App, banks or currencies without provider-issued authorization. Use the official destination application for the final recipient check, FX quote, authentication and transfer. No transfer is completed inside this screen.',WARN)
        self.fx_method=tk.StringVar(value='Wise')
        options=['Wise','Revolut Merchant','PayPal Checkout','Venmo (PayPal)','Cash App Pay (Square)','Cash App Personal (external)','Zelle (your bank)','ACH bank transfer','Bank wire / SWIFT']
        self._select(c,'Transfer method / rail',self.fx_method,options)
        ledgers=fiat_registry.load()
        self.fx_ledger=tk.StringVar(value=ledgers[0] if ledgers else '(no local ledger)')
        self._select(c,'Source currency account label (not a funding instruction)',self.fx_ledger,['(no local ledger)']+ledgers)
        self.fx_from=tk.StringVar(value='USD');self.fx_to=tk.StringVar(value='EUR')
        codes=sorted(fp.CURRENCIES)
        self._select(c,'From fiat currency',self.fx_from,codes)
        self._select(c,'To fiat currency',self.fx_to,codes)
        self.fx_amount=tk.StringVar(value='25.00')
        self._entry(c,'Send amount',self.fx_amount)
        self.fx_beneficiary=tk.StringVar(value='')
        self._entry(c,'Recipient nickname (not account credentials)',self.fx_beneficiary)
        self._btn(c,'REVIEW EXTERNAL TRANSFER / OPEN PROVIDER',self._fiat_open_send,True).pack(anchor='w',pady=12)
        self.info(c,'No proprietary USD/EUR "wallet address" exists. Your actual balance, receiving details, fees, settlement and exchange rates come from your licensed bank/payment provider. Card numbers, passwords and bank login details are never requested here.')

    def _fiat_open_send(self):
        m=self.fx_method.get();src=self.fx_from.get();dst=self.fx_to.get();amount=self.fx_amount.get()
        try:fp.amount_minor(amount,src)
        except Exception as e:messagebox.showerror('Invalid amount',str(e));return
        if src!=dst and m in ('Zelle (your bank)','ACH bank transfer','Cash App Pay (Square)','Cash App Personal (external)','Venmo (PayPal)'):
            messagebox.showwarning('Conversion unavailable','This method does not offer a general international FX conversion flow here. Choose Wise, Revolut or bank wire and verify eligibility.')
            return
        if not messagebox.askyesno('External transfer review',f'Source: {amount} {src}\nDestination currency: {dst}\nMethod: {m}\nRecipient label: {self.fx_beneficiary.get()[:60]}\n\nNO QUOTE OR FUNDS TRANSFER HAS OCCURRED. Continue to the official provider?'):
            return
        urls={
            'Wise':'https://wise.com/', 'Revolut Merchant':'https://www.revolut.com/',
            'PayPal Checkout':'https://www.paypal.com/', 'Venmo (PayPal)':'https://venmo.com/',
            'Cash App Pay (Square)':'https://cash.app/', 'Cash App Personal (external)':'https://cash.app/', 'Zelle (your bank)':'https://www.zellepay.com/',
            'ACH bank transfer':'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
            'Bank wire / SWIFT':'https://www.consumerfinance.gov/consumer-tools/bank-accounts/',
        }
        webbrowser.open(urls[m]);self.status.set('EXTERNAL HANDOFF ONLY • No transfer initiated')

    def _fiat_verify_tab(self,frame):
        c=tk.Frame(frame,bg=CARD,padx=18,pady=16);c.pack(fill='x')
        self._lab(c,'OPEN AN ENCRYPTED PAYMENT REQUEST',True).pack(anchor='w')
        self.fv_path=tk.StringVar(value='');self._entry(c,'Encrypted .fiatpay record path',self.fv_path)
        self._btn(c,'Browse .fiatpay',self._fiat_select_payment).pack(anchor='w',pady=4)
        self.fv_password=tk.StringVar(value='')
        self._entry(c,'Encryption password',self.fv_password,True)
        row=tk.Frame(c,bg=CARD);row.pack(anchor='w',pady=8)
        self._btn(row,'OPEN LOCAL REQUEST',self._fiat_open_record).pack(side='left',padx=5)
        self._btn(row,'VERIFY WITH PROVIDER',self._fiat_verify_remote,True).pack(side='left',padx=5)
        self._btn(row,'CAPTURE APPROVED PAYPAL ORDER',self._fiat_capture_paypal).pack(side='left',padx=5)
        self.fv_summary=tk.StringVar(value='No encrypted payment request opened.')
        tk.Label(c,textvariable=self.fv_summary,bg=CARD,fg=FG,justify='left',wraplength=730).pack(anchor='w',pady=8)
        self.info(c,'Local records alone cannot confirm receipt. API confirmation is required for a paid state. Provider refunds, payout timing, payment disputes and bank settlement must be checked separately. No fiat ledger balance is silently credited.',WARN)

    def _fiat_select_payment(self):
        p=filedialog.askopenfilename(title='Choose encrypted payment record',filetypes=[('Fiat payments','*.fiatpay')])
        if p:self.fv_path.set(p)

    def _fiat_open_record(self):
        path=self.fv_path.get();pw=self.fv_password.get()
        try:rec=fp.read_payment_file(path,pw)
        except Exception as e:messagebox.showerror('Cannot open payment file',str(e));return
        self.fv_password.set('')
        self._fiat_display_record(rec)

    def _fiat_display_record(self,rec):
        self.fv_summary.set('Method: '+rec['method']+'\nAmount: '+str(rec['minor']/(1 if rec['currency'] in fp.ZERO_DECIMAL else 100))+' '+rec['currency']+'\nMode: '+rec['environment']+'\nState (last verified): '+rec['state'].upper()+'\nOrder: '+rec['provider_id']+'\nProvider link: '+rec['checkout_url']+'\nLast confirmed: '+str(rec.get('verified_utc') or 'Not verified'))

    def _fiat_verify_remote(self):
        path=self.fv_path.get();pw=self.fv_password.get()
        if not path or not pw:return messagebox.showwarning('Missing data','Choose the .fiatpay file and enter its password')
        self.fv_password.set('')
        def done(rec):
            self._fiat_display_record(rec)
            messagebox.showinfo('Provider status',f'Provider returned: {rec["state"].upper()}\n\nThis is not the same as withdrawn/settled funds. Check your provider for disputes and final settlement.')
        self.run_job(lambda:fp.verify_and_save(path,pw),done,'Checking order identity, amount, currency and provider status...')

    def _fiat_capture_paypal(self):
        path=self.fv_path.get();pw=self.fv_password.get()
        try:rec=fp.read_payment_file(path,pw)
        except Exception as e:messagebox.showerror('Cannot open payment file',str(e));return
        if rec['provider']!='PayPal':return messagebox.showwarning('Not PayPal','Only PayPal orders can be captured here')
        if not messagebox.askyesno('Capture PayPal payment',f'CAPTURE approved payer funds?\nAmount: {rec["minor"]/(1 if rec["currency"] in fp.ZERO_DECIMAL else 100)} {rec["currency"]}\nOrder ID: {rec["provider_id"]}\n\nOnly do this for an approved authorized payment.'):
            return
        self.fv_password.set('')
        def work():
            fp.capture_paypal(rec)
            return fp.verify_and_save(path,pw)
        self.run_job(work,self._fiat_display_record,'Capturing explicitly approved PayPal order...')

    def _fiat_connections_tab(self,frame):
        c=tk.Frame(frame,bg=CARD,padx=18,pady=15);c.pack(fill='x')
        self._lab(c,'SUPPORTED PROVIDERS — DIFFERENT LEVELS OF INTEGRATION',True).pack(anchor='w')
        self.info(c,'API secrets are read from environment variables ONLY at request time; they are not written to account files. Never enter any banking username/password or paste card numbers into this app.')
        for name in fp.METHODS:
            line=tk.Frame(c,bg=CARD);line.pack(fill='x',pady=2)
            tk.Label(line,text=name,bg=CARD,fg=FG,width=25,anchor='w').pack(side='left')
            tk.Label(line,text=fp.config_status(name),bg=CARD,fg=ACCENT if 'Configured' in fp.config_status(name) else MUTED,anchor='w').pack(side='left')
        self.info(c,'A "Configured" label only means credentials exist in the environment; it is not a verified account connection. Merchant API access is subject to provider approval, local regulations and eligibility.',WARN)
        self._btn(c,'Create local fiat ledger',lambda:self._jump_fiat_create()).pack(anchor='w',pady=7)
