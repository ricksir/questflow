from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_server import QuestFlowLocalServer


class DummyApi:
    pass


class DynamicMobileNetwork692Tests(unittest.TestCase):
    def test_default_route_ip_is_ranked_before_stale_or_virtual_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('ok', encoding='utf-8')
            server = QuestFlowLocalServer(DummyApi(), root, bind_host='0.0.0.0')
            server.start()
            try:
                fake_info = [
                    (2, 1, 6, '', ('192.168.128.84', 0)),
                    (2, 1, 6, '', ('192.168.15.131', 0)),
                ]
                with patch.object(QuestFlowLocalServer, '_default_route_ipv4', return_value='192.168.15.131'), \
                     patch('web_server.socket.getaddrinfo', return_value=fake_info):
                    info = server.mobile_network_info()
                self.assertEqual(info['preferred_ip'], '192.168.15.131')
                self.assertEqual(info['addresses'][0], '192.168.15.131')
                self.assertTrue(info['api_urls'][0].startswith('http://192.168.15.131:'))
                self.assertTrue(any(url.startswith('http://192.168.128.84:') for url in info['api_urls'][1:]))
            finally:
                server.stop()

    def test_lan_addresses_are_recomputed_each_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('ok', encoding='utf-8')
            server = QuestFlowLocalServer(DummyApi(), root, bind_host='0.0.0.0')
            server.start()
            try:
                with patch.object(QuestFlowLocalServer, '_default_route_ipv4', return_value='192.168.1.10'), \
                     patch('web_server.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('192.168.1.10', 0))]):
                    first = server.mobile_network_info()['preferred_ip']
                with patch.object(QuestFlowLocalServer, '_default_route_ipv4', return_value='10.0.0.55'), \
                     patch('web_server.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.0.0.55', 0))]):
                    second = server.mobile_network_info()['preferred_ip']
                self.assertEqual(first, '192.168.1.10')
                self.assertEqual(second, '10.0.0.55')
            finally:
                server.stop()

    def test_loopback_and_link_local_are_not_offered_to_mobile(self):
        self.assertFalse(QuestFlowLocalServer._usable_lan_ipv4('127.0.0.1'))
        self.assertFalse(QuestFlowLocalServer._usable_lan_ipv4('169.254.1.9'))
        self.assertTrue(QuestFlowLocalServer._usable_lan_ipv4('192.168.15.131'))

    def test_mobile_package_is_sdk57_aligned_and_contains_dynamic_discovery(self):
        import json
        root = Path(__file__).resolve().parents[1]
        package = json.loads((root / "mobile" / "package.json").read_text(encoding="utf-8"))
        deps = package["dependencies"]
        self.assertEqual(deps["react"], "19.2.3")
        self.assertEqual(deps["react-dom"], "19.2.3")
        self.assertIn("expo-dev-client", deps)
        app = json.loads((root / "mobile" / "app.json").read_text(encoding="utf-8"))
        self.assertNotIn("newArchEnabled", app["expo"])
        self.assertEqual(app["expo"]["extra"]["eas"]["projectId"], "f6973b2c-c748-424a-a074-56cff9511951")
        context = (root / "mobile" / "src" / "context" / "QuestFlowContext.tsx").read_text(encoding="utf-8")
        self.assertIn("discoverAuthenticatedServer", context)
        self.assertIn("serverFingerprint", context)
        self.assertIn("ipv4SubnetCandidates", context)
        pairing = (root / "web_api.py").read_text(encoding="utf-8")
        self.assertIn('for api_url in api_urls', pairing)
        self.assertIn('network_dynamic', pairing)


if __name__ == '__main__':
    unittest.main()
