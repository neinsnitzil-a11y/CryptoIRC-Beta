"""Phase 16 local compliance workspace: no identity collection or live payment approvals."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from compliance_runtime import LocalComplianceJournal, ComplianceError, SCOPES, PRIVACY_REQUESTS, assess_provider_eligibility

BG='#07060b'; CARD='#15101e'; GREEN='#47fca3'; MUTED='#a39ab6'; WARN='#ff707a'; PURPLE='#b363ff'
NOTICES = {'PRIVACY_NOTICE':'privacy-v1', 'TERMS_NOTICE':'terms-draft-v1', 'RISK_DISCLOSURE':'wallet-risk-v1'}
NOTICE_TEXT = {
    'PRIVACY_NOTICE':'LOCAL PRIVACY INFORMATION (DEVELOPMENT DRAFT)\nNOCTURNE stores encrypted wallet files and local application metadata. The local Compliance Center journal records only notice versions, actions and timestamps. Connected blockchain nodes and external purchase providers have their own data practices. This notice is not a reviewed privacy policy.',
    'TERMS_NOTICE':'DRAFT — NO PUBLIC SERVICE TERMS ARE PROVIDED. The application is experimental. No acceptance here creates a bank account, authorizes payment processing, establishes a financial-services relationship or replaces legally reviewed terms.',
    'RISK_DISCLOSURE':'CRYPTO ASSET RISK INFORMATION\nCryptocurrency transfers may be irreversible. Wrong-network addresses and lost private keys can permanently lose funds. Blockchain balances and local records can be stale. NOCTURNE has not passed independent wallet-security or live transaction audits. Do not fund wallets without independent recovery/spending tests.'
}

class ComplianceUI:
    def page_compliance_center(self):
        self.head('Compliance Center / Phase 16',
            'Local privacy/consent tracking and operational eligibility preflight. This application is NOT a licensed bank, '
            'does not conduct identity verification or sanctions screening, and cannot authorize live fiat transactions.')
        self._comp_scope=tk.StringVar(value='PRIVACY_NOTICE')
        self._comp_viewed=set()
        self._comp_request=tk.StringVar(value='ACCESS')
        self._comp_result=tk.StringVar(value='No live provider eligibility approval. Financial transfers stay disabled.')
        self._comp_audit=tk.StringVar(value='Local journal status not yet checked.')
        self._comp_consent=tk.StringVar(value='No notice state checked.')
        card=tk.Frame(self.content,bg=CARD,padx=16,pady=13);card.pack(fill='x',pady=6)
        tk.Label(card,text='01 / RELEASE AND PROVIDER GATES',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(card,text='PRODUCTION BANKING: DISABLED  •  LIVE ON-RAMP: UNVERIFIED  •  KYC/AML/SANCTIONS: NOT PROVIDED',
            fg=WARN,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=7)
        tk.Label(card,textvariable=self._comp_result,fg=PURPLE,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=4)
        ttk.Button(card,text='CHECK PROVIDER ELIGIBILITY',command=self._comp_policy).pack(anchor='w',pady=6)
        tk.Label(card,text='A desktop eligibility check is advisory only. A separate backend must verify signed, short-lived provider scopes. '
            'Country selection or notice acceptance never substitutes for KYC, AML, sanctions checks or legal permissions.',
            fg=MUTED,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=4)
        card=tk.Frame(self.content,bg=CARD,padx=16,pady=13);card.pack(fill='x',pady=6)
        tk.Label(card,text='02 / LOCAL NOTICE RECORDS',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(card,text='These records are local metadata only, not an online identity or regulatory consent service. '
            'Review actual applicable notices before accepting.',fg=MUTED,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=5)
        ttk.Combobox(card,textvariable=self._comp_scope,values=sorted(SCOPES),state='readonly',width=26).pack(anchor='w',pady=5)
        row=tk.Frame(card,bg=CARD);row.pack(anchor='w',pady=6)
        ttk.Button(row,text='READ NOTICE',command=self._comp_show_notice).pack(side='left',padx=(0,7))
        ttk.Button(row,text='RECORD NOTICE ACCEPTANCE',command=lambda:self._comp_record('ACCEPT')).pack(side='left',padx=(0,7))
        ttk.Button(row,text='WITHDRAW LOCAL ACCEPTANCE',command=lambda:self._comp_record('REVOKE')).pack(side='left',padx=(0,7))
        ttk.Button(row,text='CHECK NOTICE STATE',command=self._comp_state).pack(side='left')
        tk.Label(card,textvariable=self._comp_consent,fg=PURPLE,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=6)
        card=tk.Frame(self.content,bg=CARD,padx=16,pady=13);card.pack(fill='x',pady=6)
        tk.Label(card,text='03 / PRIVACY REQUEST REGISTER',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(card,text='Record a local request type without supplying a name, identification documents, wallet address, '
            'bank credentials or recovery phrase. Recording a request does not send it to a provider or fulfill it.',
            fg=MUTED,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=5)
        row=tk.Frame(card,bg=CARD);row.pack(anchor='w',pady=7)
        ttk.Combobox(row,textvariable=self._comp_request,values=sorted(PRIVACY_REQUESTS),state='readonly',width=24).pack(side='left',padx=(0,8))
        ttk.Button(row,text='RECORD LOCAL REQUEST',command=self._comp_privacy).pack(side='left')
        card=tk.Frame(self.content,bg=CARD,padx=16,pady=13);card.pack(fill='x',pady=6)
        tk.Label(card,text='04 / LOCAL AUDIT INTEGRITY & EXPORT',fg=GREEN,bg=CARD,font=('Consolas',12,'bold')).pack(anchor='w')
        tk.Label(card,textvariable=self._comp_audit,fg=PURPLE,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=5)
        row=tk.Frame(card,bg=CARD);row.pack(anchor='w',pady=5)
        ttk.Button(row,text='VERIFY LOCAL AUDIT CHAIN',command=self._comp_verify).pack(side='left',padx=(0,8))
        ttk.Button(row,text='EXPORT RECENT 500 AUDIT EVENTS',command=self._comp_export).pack(side='left')
        tk.Label(card,text='SHA-256 chaining detects some accidental or local edits; it is not tamper-proof against an attacker '
            'who can rewrite the journal. Financial audit retention and privacy requests require an external accountable process.',
            fg=WARN,bg=CARD,wraplength=980,justify='left').pack(anchor='w',pady=6)
        self._comp_verify()

    def _comp_policy(self):
        status=assess_provider_eligibility(None,provider='NOT_CONFIGURED',country='US',operation='DEPOSIT',currency='USD',amount_minor=100)
        self._comp_result.set(f'{status.code}: {status.note} Live banking and payment settlement remain blocked.')

    def _comp_show_notice(self):
        scope=self._comp_scope.get()
        messagebox.showinfo('Local development notice / '+scope,NOTICE_TEXT.get(scope,'No notice available.'),parent=self.root)
        if scope in NOTICE_TEXT:self._comp_viewed.add(scope)

    def _comp_record(self,action):
        scope=self._comp_scope.get()
        if action=='ACCEPT' and scope not in self._comp_viewed:
            self._comp_consent.set('Read the selected notice first. No acceptance was recorded.');return
        if action=='ACCEPT' and not messagebox.askyesno('Local notice metadata',
            'Record that you reviewed the selected notice? This is only local metadata and does not authorize financial services.',parent=self.root):return
        if action=='ACCEPT' and scope=='TERMS_NOTICE':
            self._comp_consent.set('Draft terms cannot be accepted as a binding agreement. Await reviewed service terms.');return
        try:
            LocalComplianceJournal().append(action,scope,NOTICES[scope])
            self._comp_state();self._comp_verify()
        except (ComplianceError,OSError,KeyError) as exc:
            self._comp_audit.set('Journal unavailable or damaged; no notice state changed.')

    def _comp_state(self):
        try:
            scope=self._comp_scope.get()
            yes=LocalComplianceJournal().consent_state(scope,NOTICES[scope])
            self._comp_consent.set(f'{scope}: '+('locally recorded as accepted' if yes else 'NOT currently accepted')
                +'. This never represents verified identity or funding permission.')
        except (ComplianceError,OSError,KeyError):
            self._comp_consent.set('Local notice state unavailable; do not infer consent.')

    def _comp_privacy(self):
        try:
            LocalComplianceJournal().append('PRIVACY_REQUEST',self._comp_request.get(),'1')
            self._comp_verify()
        except (ComplianceError,OSError):
            self._comp_audit.set('Could not record privacy request. No request has been sent.')

    def _comp_verify(self):
        try:
            count=LocalComplianceJournal().verify()
            self._comp_audit.set(f'Local sequence check passed · {count} metadata entries · NOT an independently authenticated audit.')
        except (ComplianceError,OSError):
            self._comp_audit.set('WARNING: Local compliance journal could not be verified. Further records must be blocked.')

    def _comp_export(self):
        try: contents=LocalComplianceJournal().export_redacted()
        except (ComplianceError,OSError):
            self._comp_audit.set('Cannot export an unverified local journal.');return
        dest=filedialog.asksaveasfilename(parent=self.root,defaultextension='.json',filetypes=[('JSON','.json')],
                                          initialfile='nocturne-local-compliance-export.json')
        if not dest:return
        try:
            target=Path(dest)
            if target.is_symlink():raise OSError('Not a regular export target')
            with target.open('x',encoding='utf-8') as stream:stream.write(contents+'\n')
            self._comp_audit.set('Minimal local metadata exported (not a regulatory filing).')
        except (OSError,ValueError):
            self._comp_audit.set('Export refused; choose a new filename outside the application installation folder.')
