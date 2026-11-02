"""Backup-display checks use obviously fake sample words, never real secret material."""
from __future__ import annotations
import unittest
from pathlib import Path

from recovery_flow import pick_challenge_positions, check_challenge


class BackupFlowTests(unittest.TestCase):
    def test_challenges_cover_supported_phrase_lengths(self):
        for n in (12,24,25):
            with self.subTest(words=n):
                sample=[f'fakeword{i}' for i in range(n)]
                selected=pick_challenge_positions(sample)
                self.assertEqual(len(selected),4)
                self.assertEqual(len(set(selected)),4)
                self.assertTrue(all(0<=i<n for i in selected))
                self.assertTrue(check_challenge(sample,selected,[sample[i] for i in selected]))

    def test_verification_checks_every_requested_word(self):
        words=[f'fakeword{i}' for i in range(24)]
        positions=(0,7,13,23)
        self.assertTrue(check_challenge(words,positions,['fakeword0','fakeword7','fakeword13','FAKEWORD23']))
        self.assertFalse(check_challenge(words,positions,['fakeword0','wrong','fakeword13','fakeword23']))
        self.assertFalse(check_challenge(words,positions,['fakeword0']))
        self.assertFalse(check_challenge(words,(0,0),['fakeword0','fakeword0']))

    def test_new_wallet_flow_reads_saved_vault_not_a_new_seed(self):
        source=Path(__file__).resolve().parents[1].joinpath('professional_ui.py').read_text(encoding='utf-8')
        self.assertIn("groups.append(read_vault(path,pw)['groups'])",source)
        self.assertIn('RecoveryBackupDialog(self.root,group_sets[i]',source)
        self.assertIn('if restore:',source)
        self.assertNotIn("messagebox.showinfo('Encrypted vault created'",source)

    def test_backup_dialog_never_auto_exports_or_uses_clipboard(self):
        source=Path(__file__).resolve().parents[1].joinpath('recovery_flow.py').read_text(encoding='utf-8')
        self.assertNotIn('clipboard_append',source)
        self.assertIn('SAVE AS .TXT (UNENCRYPTED)',source)
        self.assertIn('if not approved: return',source)
        self.assertNotIn('print(',source)
        self.assertIn('after(300000,self._expire)',source)


if __name__=='__main__':unittest.main()
