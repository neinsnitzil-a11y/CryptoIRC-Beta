"""Tests use synthetic invalid-wallet words and never any user recovery secrets."""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recovery_export import save_plaintext_backup, format_backup_text, suggested_filename

class RecoveryExportTests(unittest.TestCase):
    def setUp(self):
        self.words=['exampleword' for _ in range(12)]
    def test_text_contains_all_words_numbered_and_safety_warning(self):
        text=format_backup_text(asset='BTC', scheme='bip39', words=self.words, extra_passphrase_used=True)
        self.assertIn('01. exampleword',text)
        self.assertIn('12. exampleword',text)
        self.assertIn('UNENCRYPTED',text)
        self.assertIn('NOT INCLUDED; BACK UP SEPARATELY',text)
        self.assertEqual(len([line for line in text.splitlines() if '. exampleword' in line]),12)
    def test_native_25_words_format(self):
        text=format_backup_text(asset='XMR', scheme='monero',words=['sampleword']*25,extra_passphrase_used=False)
        self.assertIn('Monero 25-word mnemonic',text)
        self.assertIn('25. sampleword',text)
    def test_exclusive_save_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'wallet.txt'
            save_plaintext_backup(path,asset='BTC',scheme='bip39',words=self.words,extra_passphrase_used=False)
            self.assertEqual(path.read_text(encoding='utf-8').count('exampleword'),12)
            with self.assertRaises(FileExistsError):
                save_plaintext_backup(path,asset='BTC',scheme='bip39',words=self.words,extra_passphrase_used=False)
            self.assertEqual(path.read_text(encoding='utf-8').count('exampleword'),12)
    def test_rejects_other_suffix_and_invalid_word_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_plaintext_backup(Path(tmp)/'key.pem',asset='BTC',scheme='bip39',words=self.words,extra_passphrase_used=False)
            with self.assertRaises(ValueError):
                save_plaintext_backup(Path(tmp)/'key.txt',asset='BTC',scheme='bip39',words=['one','two'],extra_passphrase_used=False)
            self.assertFalse((Path(tmp)/'key.txt').exists())
    def test_suggested_filename_sanitizes_asset(self):
        self.assertEqual(suggested_filename('BTC/XMR',1,2),'CRYPTO_RECOVERY_BTC_XMR_W1_G2.txt')
    def test_gui_export_is_explicit_and_dialog_scoped(self):
        src=Path(__file__).resolve().parents[1].joinpath('recovery_flow.py').read_text(encoding='utf-8')
        self.assertIn("self._button('SAVE AS .TXT (UNENCRYPTED)'",src)
        self.assertIn('askyesno(',src)
        self.assertIn('asksaveasfilename(',src)
        self.assertIn('if not approved: return',src)
        self.assertNotIn('clipboard_append',src)

if __name__=='__main__':unittest.main()
