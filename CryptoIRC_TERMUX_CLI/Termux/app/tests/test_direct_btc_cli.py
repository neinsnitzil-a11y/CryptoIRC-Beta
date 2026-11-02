"""Direct Bitcoin CLI routing tests; no actual node, wallet or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vaultforge
import transfer_engine as te

class DirectCommandTests(unittest.TestCase):
    def test_spend_and_alias_route_to_btc_signer(self):
        for cmd in ('spend-btc', 'send-btc'):
            with self.subTest(cmd=cmd):
                with patch('vaultforge.btc.bitcoin_send') as spend, redirect_stdout(io.StringIO()):
                    self.assertEqual(vaultforge.main([cmd]), 0)
                spend.assert_called_once_with()

    def test_receive_and_balance_routes(self):
        for cmd, method in [('receive-btc','bitcoin_receive'), ('btc-balance','bitcoin_balance'), ('btc-status','bitcoin_status')]:
            with self.subTest(cmd=cmd):
                with patch.object(vaultforge.btc, method) as action, redirect_stdout(io.StringIO()):
                    self.assertEqual(vaultforge.main([cmd]), 0)
                action.assert_called_once_with()

    def test_spend_error_propagates_nonzero_without_trace(self):
        with patch('vaultforge.btc.bitcoin_send', side_effect=te.TransferError('RPC offline')), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(vaultforge.main(['spend-btc']), 2)
        self.assertIn('RPC offline', err.getvalue())

    def test_mainnet_send_still_requires_explicit_authorization(self):
        from unittest.mock import patch as p
        import bitcoin_vault as btc
        payload={'wallets':[{'coin':'BTC'}]}
        with p('bitcoin_vault.bridge.unlock_selected', return_value=(Path('test.vault'),payload)), \
             p('bitcoin_vault.require_btc_entry',return_value=payload['wallets'][0]), \
             p('bitcoin_vault.derive_identity',return_value=btc.Identity('bc1qtest','0014'+'ab'*20,None,'main')), \
             p('builtins.input', side_effect=['main','NO']), \
             p('bitcoin_vault.get_rpc') as rpc, redirect_stdout(io.StringIO()):
            self.assertEqual(vaultforge.main(['spend-btc']),0)
        rpc.assert_not_called()

if __name__=='__main__': unittest.main()
