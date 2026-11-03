"""Local secret configuration is offline and cannot implicitly enable live API."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from setup_amap import FIELDS, private_key_path, read_private_keys, save_private_keys
from amap_client import LiveGateway


class LocalSecretTests(unittest.TestCase):
    def test_writes_three_secrets_but_never_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            secrets = {
                "MRM_AMAP_WEB_KEY": "EXAMPLE_WEB_KEY_123",
                "MRM_AMAP_JS_KEY": "EXAMPLE_JS_KEY_456",
                "MRM_AMAP_JS_SECURITY": "EXAMPLE_JS_SECURITY_789",
            }
            path = save_private_keys(root, secrets)
            self.assertEqual(path, private_key_path(root))
            self.assertEqual(read_private_keys(root), secrets)
            self.assertFalse(any("AUTHORIZED" in x or "OPT_IN" in x for x in json.loads(path.read_text())))
            with patch.dict(os.environ, {}, clear=True):
                gateway = LiveGateway(root)
                self.assertEqual(gateway.key, secrets["MRM_AMAP_WEB_KEY"])
                self.assertEqual(gateway.js_key, secrets["MRM_AMAP_JS_KEY"])
                self.assertEqual(gateway.js_security, secrets["MRM_AMAP_JS_SECURITY"])
                self.assertFalse(gateway.status()["live_enabled"])
                self.assertFalse(gateway.status()["js_map_enabled"])
                self.assertNotIn(secrets["MRM_AMAP_WEB_KEY"], json.dumps(gateway.status()))
                self.assertNotIn(secrets["MRM_AMAP_JS_SECURITY"], json.dumps(gateway.status()))

    def test_invalid_file_and_unknown_flags_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path = private_key_path(root)
            path.parent.mkdir()
            path.write_text('{"MRM_USAGE_AUTHORIZED":"YES","MRM_AMAP_JS_SECURITY":"bad"}')
            self.assertEqual(read_private_keys(root), {})
            with self.assertRaises(ValueError):
                save_private_keys(root, {"MRM_EXPLICIT_LIVE_OPT_IN":"YES"})
            with self.assertRaises(ValueError):
                save_private_keys(root, {"MRM_AMAP_WEB_KEY":"not a valid key"})
            self.assertEqual(read_private_keys(root), {})

    def test_incremental_update_preserves_existing_secret(self):
        with tempfile.TemporaryDirectory() as root:
            first={"MRM_AMAP_WEB_KEY":"EXAMPLE_VALID_WEB"}
            save_private_keys(root, first)
            update={**read_private_keys(root), "MRM_AMAP_JS_KEY":"EXAMPLE_VALID_JS"}
            save_private_keys(root, update)
            self.assertEqual(read_private_keys(root), update)


if __name__ == "__main__":
    unittest.main()
