"""Multi-relay regression tests: no AWS/network calls or wallet funds."""
from pathlib import Path
import asyncio
import tempfile
import unittest
from unittest.mock import patch

import mesh_chat as mesh


class RelayDirectoryTests(unittest.TestCase):
    def test_preserves_hosts_pins_active_and_custom_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mesh.secure_save(root/'known_peers.json', {'example.org:6123':'a'*16})
            first = mesh.load_relay_hosts(root)
            self.assertEqual(first['active'], '18.227.91.173:6667')
            self.assertIn('18.188.145.207:6667', [x['endpoint'] for x in first['hosts']])
            self.assertIn('example.org:6123', [x['endpoint'] for x in first['hosts']])
            identity = mesh.create_account(root, 'LocalUser', 'testing strong password')
            node = mesh.MeshNode(identity, root, notify=lambda x:None)
            node.relay_add('chat.example.net:6655','Friend Server')
            node.relay_select('chat.example.net:6655')
            self.assertEqual(mesh.load_relay_hosts(root)['active'],'chat.example.net:6655')
            self.assertEqual(mesh.load_relay_hosts(root)['hosts'][-1]['label'],'Friend Server')
            node.relay_remove('18.188.145.207:6667')
            self.assertNotIn('18.188.145.207:6667', [r['endpoint'] for r in mesh.load_relay_hosts(root)['hosts']])
            self.assertEqual(mesh.secure_load(root/'known_peers.json')['example.org:6123'],'a'*16)
            with self.assertRaises(ValueError):
                node.relay_remove('chat.example.net:6655')

class LiveConnectionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_multi_host_live_links_and_tofu_first_contact(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Path(folder)
            nodes=[]
            with patch('security_center.load_settings', return_value={'mode':'direct', 'port':9050}):
                try:
                    for nick in ('AlphaRelay','BetaRelay','Visitor'):
                        ident=mesh.create_account(r/nick, nick, 'test password long enough')
                        node=mesh.MeshNode(ident, r/nick, notify=lambda x:None)
                        await node.start('127.0.0.1',0)
                        nodes.append(node)
                    client=nodes[2]
                    for relay in nodes[:2]:
                        endpoint='127.0.0.1:'+str(relay.current_port)
                        await client.connect(endpoint)
                        client.relay_add(endpoint, relay.ident.nick)
                    rows=client.relay_rows()
                    connected=[row for row in rows if row['state']=='CONNECTED']
                    self.assertEqual(len(connected),2)
                    self.assertTrue(all(row['trusted'] for row in connected))
                    self.assertEqual(len(client.links),2)
                    self.assertEqual(len(mesh.secure_load(client.pins_path)),2)
                    self.assertEqual(len(mesh.load_relay_hosts(client.root)['hosts']),4)
                finally:
                    for node in reversed(nodes):
                        await node.stop()
