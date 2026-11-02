"""Phase 18 non-spending tests: false approval, tampering, signatures, export and installer policy."""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from release_ops import (
    ReleaseOpsError, VERSION, _canonical, assess_release, check_installer_policy,
    make_sbom, verify_signed_update, write_exclusive_json, sha256_file,
)

SOURCE=Path(__file__).resolve().parents[1]

class ReleaseOpsChecks(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='nocturne45test-')
        self.addCleanup(tmp.cleanup)
        self.folder=Path(tmp.name)

    def test_phase18_local_checks_are_not_release_approval(self):
        d=assess_release(SOURCE)
        self.assertEqual(d['version'],'4.5.1')
        self.assertEqual(d['release_status'],'BLOCKED')
        self.assertIs(d['production_ready'],False)
        self.assertIs(d['real_money_approved'],False)
        self.assertEqual(len(d['checks']),3)
        self.assertEqual(len(d['external_requirements']),4)
        self.assertEqual(sum(x['status']=='PASS_LOCAL' for x in d['checks']),3)
        self.assertTrue(all(x['status']=='BLOCKED_EXTERNAL' for x in d['external_requirements']))

    def test_installer_policy_rejects_destructive_rules(self):
        original=(SOURCE/'installer.iss').read_text(encoding='utf-8')
        self.assertTrue(check_installer_policy(SOURCE/'installer.iss')[0])
        candidate=self.folder/'installer.iss'
        candidate.write_text(original+'\n[UninstallDelete]\nType: filesandordirs; Name: "{userappdata}"\n',encoding='utf-8')
        self.assertFalse(check_installer_policy(candidate)[0])
        candidate.write_text(original.replace('UsePreviousAppDir=yes','UsePreviousAppDir=no'),encoding='utf-8')
        self.assertFalse(check_installer_policy(candidate)[0])

    def test_support_report_is_redacted_exclusive_and_outside_project(self):
        d=assess_release(SOURCE)
        target=self.folder/'support.json'
        self.assertEqual(write_exclusive_json(d,target,project_root=SOURCE.parent),target)
        exported=target.read_text(encoding='utf-8')
        self.assertNotIn(str(SOURCE),exported)
        self.assertNotIn('password',exported.lower())
        with self.assertRaises(ReleaseOpsError):write_exclusive_json(d,target,project_root=SOURCE.parent)
        fake=copy.deepcopy(d)
        fake['checks'][0]['note']='wallet seed: totally secret'
        with self.assertRaises(ReleaseOpsError):write_exclusive_json(fake,self.folder/'bad.json',project_root=SOURCE.parent)
        fake=copy.deepcopy(d);fake['production_ready']=True
        with self.assertRaises(ReleaseOpsError):write_exclusive_json(fake,self.folder/'bad2.json',project_root=SOURCE.parent)
        with self.assertRaises(ReleaseOpsError):write_exclusive_json(d,SOURCE/'bad.json',project_root=SOURCE.parent)

    def test_cyclonedx_inventory_direct_deps_only(self):
        result=make_sbom(SOURCE/'requirements.txt')
        self.assertEqual(result['bomFormat'],'CycloneDX')
        self.assertGreaterEqual(len(result['components']),5)
        self.assertTrue(all('version' in x for x in result['components']))
        (self.folder/'req.txt').write_text('unsafe>=0\n')
        with self.assertRaises(ReleaseOpsError):make_sbom(self.folder/'req.txt')

class OfflineSignedUpdates(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='nocturne45sign-')
        self.addCleanup(tmp.cleanup)
        self.folder=Path(tmp.name)
        self.key=Ed25519PrivateKey.generate()  # disposable test key; never packaged
        pub=self.key.public_key()
        der=pub.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.fingerprint=hashlib.sha256(der).hexdigest()
        self.key_path=self.folder/'verified-public-key.pem'
        self.key_path.write_bytes(pub.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        self.file=self.folder/'CRYPTO_NOCTURNE_Setup_v4.5.2.exe'
        self.file.write_bytes(b'FAKE TEST INSTALLER DATA. NEVER EXECUTE OR PUBLISH.')
        self.metadata={
            'schema':1,'application':'CRYPTO_NOCTURNE','channel':'stable',
            'platform':'windows-x86_64','version':'4.5.2','minimum_from':VERSION,
            'artifact':self.file.name,'bytes':self.file.stat().st_size,
            'sha256':sha256_file(self.file),
        }
        self.manifest=self.folder/'manifest.json'
        self.sign()

    def sign(self):
        envelope={'payload':self.metadata,
                  'signature_base64':base64.b64encode(self.key.sign(_canonical(self.metadata))).decode('ascii')}
        self.manifest.write_text(json.dumps(envelope),encoding='utf-8')

    def verify(self,fingerprint=None):
        return verify_signed_update(self.manifest,self.file,self.key_path,
                                    self.fingerprint if fingerprint is None else fingerprint)

    def test_valid_pinned_ed25519_signature_only_verifies_staged_bytes(self):
        # The fixture is deliberately a FAKE, unsigned EXE. On Windows, even a
        # correctly pinned Ed25519 signature MUST NOT bypass Authenticode.
        # On Linux, verification checks only the signed bytes, not installation.
        if os.name == 'nt':
            with self.assertRaisesRegex(ReleaseOpsError, 'Authenticode'):
                self.verify()
            return
        status=self.verify()
        self.assertTrue(status['verified'])
        self.assertFalse(status['installed'])
        self.assertFalse(status['production_ready'])
        self.assertFalse(status['authenticode_checked'])

    def test_untrusted_key_rejected_even_when_signature_matches(self):
        with self.assertRaises(ReleaseOpsError):self.verify('0'*64)

    def test_modified_manifest_or_artifact_is_rejected(self):
        bad=json.loads(self.manifest.read_text())
        bad['payload']['bytes']+=1
        self.manifest.write_text(json.dumps(bad))
        with self.assertRaises(ReleaseOpsError):self.verify()
        self.sign()
        self.file.write_bytes(b'FILE CONTENT WAS TAMPERED')
        with self.assertRaises(ReleaseOpsError):self.verify()

    def test_downgrade_equal_version_and_wrong_channel_rejected(self):
        self.metadata['version']='4.5.0';self.metadata['artifact']=self.file.name
        self.sign()
        with self.assertRaises(ReleaseOpsError):self.verify()
        self.metadata['version']='4.5.1';self.metadata['artifact']=self.file.name
        self.metadata['channel']='canary';self.sign()
        with self.assertRaises(ReleaseOpsError):self.verify()

    def test_bad_trust_model_and_path_traversal_rejected(self):
        self.metadata['artifact']='../' + self.file.name
        self.sign()
        with self.assertRaises(ReleaseOpsError):self.verify()
        self.metadata['artifact']=self.file.name
        self.metadata['unsigned_server_authorization']=True
        self.sign()
        with self.assertRaises(ReleaseOpsError):self.verify()

    def test_older_current_version_must_satisfy_minimum(self):
        with self.assertRaises(ReleaseOpsError):verify_signed_update(
            self.manifest,self.file,self.key_path,self.fingerprint,current_version='4.4.0')

if __name__=='__main__':unittest.main()
