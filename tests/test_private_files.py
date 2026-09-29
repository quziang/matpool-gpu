import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from private_files import open_private_text
import matpool_auth as auth
import matpool_api as paas
import matpool_web as web


class PrivateFilesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='matpool-中文 空格-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_exclusive_utf8_creation(self):
        target = self.folder / '私密 response.json'
        with open_private_text(target) as stream:
            stream.write('中文\n')
        self.assertEqual(target.read_bytes(), '中文\n'.encode('utf-8'))
        with self.assertRaises(OSError):
            open_private_text(target)
        self.assertEqual(target.read_text(encoding='utf-8'), '中文\n')

    def test_bom_token_import_and_read(self):
        target = self.folder / '输入.token'
        target.write_text('Bearer FAKE_BOM_TOKEN\n', encoding='utf-8-sig')
        self.assertEqual(auth.load_token('web', target), 'FAKE_BOM_TOKEN')
        with contextlib.redirect_stdout(io.StringIO()):
            code = auth.main(['--config-dir', str(self.folder / 'config'),
                              'init', '--service', 'web', '--token-file', str(target)])
        self.assertEqual(code, 0)
        self.assertEqual(auth.token_path('web', self.folder / 'config').read_bytes(),
                         b'FAKE_BOM_TOKEN\n')

    def test_clients_reserve_private_output_before_request(self):
        for module, command in [(web, 'nodes'), (paas, 'stats')]:
            target = self.folder / (command + '.json')
            with patch.object(module, 'load_token', return_value='FAKE_TOKEN'), \
                    patch.object(module, 'request', return_value=(200, {'code': 0, 'secret': '中文'})) as request, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.main(['--output', str(target), command]), 0)
                original = target.read_bytes()
                self.assertEqual(json.loads(original)['response']['secret'], '中文')
                self.assertEqual(module.main(['--output', str(target), command]), 2)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(target.read_bytes(), original)

    def test_bom_rent_json_is_previewed_without_network(self):
        target = self.folder / '租用.json'
        target.write_text(json.dumps(dict(resource_pool_id='TEST_POOL', image_id=1,
                                         hardware_qty=1, machine_category=0, cmd='echo 中文'),
                                    ensure_ascii=False), encoding='utf-8-sig')
        output = io.StringIO()
        with patch.object(web, 'request') as request, contextlib.redirect_stdout(output):
            self.assertEqual(web.main(['rent', '--file', str(target)]), 0)
        self.assertTrue(json.loads(output.getvalue())['preview'])
        request.assert_not_called()

    @unittest.skipIf(sys.platform == 'darwin', 'macOS importer is supported')
    def test_unsupported_importer_exits_before_creating_directory(self):
        target = self.folder / 'must-not-create'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/import_chrome_session.py'),
                                 '--output-dir', str(target)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('macOS only', result.stderr)
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == 'nt', 'real Windows ACL check')
    def test_windows_acl_is_protected_current_user_only_even_after_replace(self):
        credential_dir = self.folder / '凭据'
        auth.save_token('web', 'FAKE_FIRST', credential_dir)
        auth.save_token('web', 'FAKE_RENEWED', credential_dir, replace=True)
        response = self.folder / 'response.json'
        with open_private_text(response) as stream:
            stream.write('{}')
        # Inspect with an independent OS interface; test data is synthetic.
        script = """
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$acl = Get-Acl -LiteralPath $env:MATPOOL_TEST_ACL_PATH
if (-not $acl.AreAccessRulesProtected) { throw 'inherited ACL' }
$rules = @($acl.Access)
if ($rules.Count -ne 1) { throw 'unexpected ACL entries' }
$rule = $rules[0]
if ($rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ne $sid) { throw 'wrong user' }
if ($rule.IsInherited -or $rule.AccessControlType -ne 'Allow' -or $rule.FileSystemRights -ne 'FullControl') { throw 'wrong rights' }
"""
        for path in [credential_dir, auth.token_path('web', credential_dir), response]:
            env = dict(os.environ, MATPOOL_TEST_ACL_PATH=str(path))
            # Do not load PowerShell 7 modules into inbox Windows PowerShell 5.1.
            for key in list(env):
                if key.lower() == 'psmodulepath':
                    del env[key]
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
