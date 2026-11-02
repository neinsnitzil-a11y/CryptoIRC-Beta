import hashlib
import hmac
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from compliance_runtime import (LocalComplianceJournal, ComplianceError,
    sign_policy_for_server, assess_provider_eligibility, ZERO)

KEY = b'server-side-test-key-do-not-ship-' + b'x'*40


def policy():
    return dict(version=1,environment='sandbox',provider='Provider_Sandbox',countries=['US','GB'],
        operations=['BUY','DEPOSIT'],currencies=['USD','GBP'],issued_at=1000,expires_at=2000,max_minor=200000)


class CompliancePhase16Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'events.sqlite3'

    def test_empty_audit_is_clean_and_no_implicit_consent(self):
        j=LocalComplianceJournal(self.path)
        self.assertEqual(j.verify(),0)
        self.assertFalse(j.consent_state('TERMS_NOTICE','terms-v1'))

    def test_consent_then_revocation_persists(self):
        j=LocalComplianceJournal(self.path)
        j.append('ACCEPT','PRIVACY_NOTICE','privacy-v1',now=1200)
        self.assertTrue(LocalComplianceJournal(self.path).consent_state('PRIVACY_NOTICE','privacy-v1'))
        j.append('REVOKE','PRIVACY_NOTICE','privacy-v1',now=1201)
        self.assertFalse(LocalComplianceJournal(self.path).consent_state('PRIVACY_NOTICE','privacy-v1'))
        self.assertEqual(j.verify(),2)

    def test_draft_terms_cannot_be_accepted_via_backend(self):
        j=LocalComplianceJournal(self.path)
        with self.assertRaises(ComplianceError):
            j.append('ACCEPT','TERMS_NOTICE','terms-draft-v1')
        self.assertEqual(j.verify(),0)

    def test_privacy_request_is_metadata_not_provider_submission(self):
        j=LocalComplianceJournal(self.path)
        j.append('PRIVACY_REQUEST','DELETION','1',now=1200)
        obj=json.loads(j.export_redacted())
        self.assertEqual(obj['events'][0]['scope'],'DELETION')
        self.assertNotIn('address',obj['events'][0])
        self.assertNotIn('email',obj['events'][0])

    def test_reject_suspicious_pii_and_secrets(self):
        j=LocalComplianceJournal(self.path)
        for action,scope,version in [('ACCEPT','my-email@example.com','1'),('ACCEPT','PRIVACY_NOTICE','secret value'),('PRIVACY_REQUEST','John Smith','1')]:
            with self.assertRaises(ComplianceError):j.append(action,scope,version)
        self.assertEqual(j.verify(),0)

    def test_tampered_record_cannot_be_extended(self):
        j=LocalComplianceJournal(self.path)
        j.append('ACCEPT','PRIVACY_NOTICE','privacy-v1',now=1200)
        con=sqlite3.connect(self.path)
        con.execute("UPDATE local_events SET action='REVOKE' WHERE seq=1")
        con.commit();con.close()
        with self.assertRaises(ComplianceError):j.verify()
        with self.assertRaises(ComplianceError):j.append('ACCEPT','TERMS_NOTICE','terms-v1')

    def test_deleted_record_detected(self):
        j=LocalComplianceJournal(self.path)
        j.append('ACCEPT','PRIVACY_NOTICE','privacy-v1')
        j.append('ACCEPT','TERMS_NOTICE','terms-v1')
        con=sqlite3.connect(self.path);con.execute('DELETE FROM local_events WHERE seq=1');con.commit();con.close()
        with self.assertRaises(ComplianceError):j.verify()

    def test_audit_symlink_refused(self):
        target=Path(self.tmp.name)/'target'
        target.write_bytes(b'')
        link=Path(self.tmp.name)/'link.sqlite3'
        try:link.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest('symlinks unavailable')
        with self.assertRaises(ComplianceError):LocalComplianceJournal(link)

    def test_unsigned_and_client_only_policy_denied(self):
        envelope=sign_policy_for_server(policy(),KEY)
        args=dict(provider='Provider_Sandbox',country='US',operation='BUY',currency='USD',amount_minor=1200,now=1500)
        self.assertEqual(assess_provider_eligibility(envelope,signing_key=KEY,**args).code,'DESKTOP_NOT_AUTHORITY')
        self.assertEqual(assess_provider_eligibility(None,signing_key=KEY,server_context=True,**args).code,'UNVERIFIED_POLICY')

    def test_signed_policy_scope_accepts_test_evaluation_not_financial_settlement(self):
        e=sign_policy_for_server(policy(),KEY)
        r=assess_provider_eligibility(e,signing_key=KEY,server_context=True,provider='Provider_Sandbox',country='US',operation='BUY',currency='USD',amount_minor=1200,now=1500)
        self.assertTrue(r.allowed)
        self.assertEqual(r.code,'POLICY_SCOPE_MATCH')
        self.assertIn('must still be verified',r.note)

    def test_tamper_signed_policy_denied(self):
        e=sign_policy_for_server(policy(),KEY)
        e['policy']['max_minor']=999999
        r=assess_provider_eligibility(e,signing_key=KEY,server_context=True,provider='Provider_Sandbox',country='US',operation='BUY',currency='USD',amount_minor=1200,now=1500)
        self.assertEqual(r.code,'BAD_SIGNATURE')

    def test_expired_and_mismatched_environment_fail_closed(self):
        e=sign_policy_for_server(policy(),KEY)
        defaults=dict(signing_key=KEY,server_context=True,provider='Provider_Sandbox',country='US',operation='BUY',currency='USD',amount_minor=1200)
        self.assertEqual(assess_provider_eligibility(e,now=2000,**defaults).code,'EXPIRED')
        self.assertEqual(assess_provider_eligibility(e,now=1500,environment='live',**defaults).code,'ENVIRONMENT')

    def test_wrong_country_provider_operation_currency_limit_denied(self):
        e=sign_policy_for_server(policy(),KEY)
        d=dict(signing_key=KEY,server_context=True,provider='Provider_Sandbox',country='US',operation='BUY',currency='USD',amount_minor=1200,now=1500)
        for patch in [dict(country='FR'),dict(provider='Another_Provider'),dict(operation='WITHDRAWAL'),dict(currency='EUR')]:
            self.assertEqual(assess_provider_eligibility(e,**(d|patch)).code,'OUTSIDE_SCOPE')
        self.assertEqual(assess_provider_eligibility(e,**(d|{'amount_minor':200001})).code,'LIMIT')
        self.assertEqual(assess_provider_eligibility(e,**(d|{'amount_minor':True})).code,'LIMIT')

    def test_bad_server_secret_rejected(self):
        with self.assertRaises(ComplianceError):sign_policy_for_server(policy(),b'short')
        e=sign_policy_for_server(policy(),KEY)
        self.assertEqual(assess_provider_eligibility(e,signing_key=b'short',server_context=True).code,'NO_TRUST_KEY')


if __name__=='__main__':unittest.main()
