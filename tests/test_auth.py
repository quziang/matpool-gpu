import contextlib
import getpass
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import matpool_auth as auth
import matpool_api as paas
import matpool_web as web


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'config'
        # Keep OS/runtime variables (notably SystemRoot on Windows Python 3.9).
        environment = {k: v for k, v in os.environ.items() if not k.startswith('MATPOOL_')}
        environment['MATPOOL_CONFIG_DIR'] = str(self.folder)
        self.environment = patch.dict(os.environ, environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = auth.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_init_creates_private_file_and_reports_no_remote_verification(self):
        with patch.dict(os.environ, {'MATPOOL_WEB_TOKEN': 'Bearer FAKE_WEB_SECRET'}):
            code, out, err = self.run_cli('init', '--service', 'web', '--from-env')
        saved = auth.token_path('web')
        self.assertEqual(code, 0)
        self.assertEqual(saved.read_text(), 'FAKE_WEB_SECRET\n')
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        self.assertFalse(json.loads(out)['verified'])
        self.assertNotIn('FAKE_WEB_SECRET', out + err)
        self.assertIn('takes precedence', err)

    def test_import_file_and_renewal_only_replace_selected_service(self):
        source = Path(self.temp.name) / 'source.token'
        source.write_text('FAKE_IMPORTED_SECRET')
        auth.save_token('paas', 'FAKE_PAAS_SECRET')
        code, _, _ = self.run_cli('init', '--service', 'web', '--token-file', str(source))
        self.assertEqual(code, 0)
        self.assertEqual(auth.load_token('web'), 'FAKE_IMPORTED_SECRET')
        source.write_text('FAKE_RENEWED_SECRET')
        code, _, _ = self.run_cli('init', '--service', 'web', '--token-file', str(source))
        self.assertEqual(code, 2)
        self.assertEqual(auth.load_token('web'), 'FAKE_IMPORTED_SECRET')
        code, _, _ = self.run_cli('init', '--service', 'web', '--token-file', str(source), '--replace')
        self.assertEqual(code, 0)
        self.assertEqual(auth.load_token('web'), 'FAKE_RENEWED_SECRET')
        self.assertEqual(auth.load_token('paas'), 'FAKE_PAAS_SECRET')
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(auth.token_path('web').stat().st_mode), 0o600)

    def test_client_precedence_and_no_fallback_after_invalid_explicit_source(self):
        auth.save_token('web', 'FAKE_SAVED_SECRET')
        explicit = Path(self.temp.name) / 'explicit.token'
        explicit.write_text('FAKE_EXPLICIT_SECRET')
        with patch.dict(os.environ, {'MATPOOL_WEB_TOKEN': 'FAKE_ENV_SECRET'}):
            self.assertEqual(auth.load_token('web'), 'FAKE_ENV_SECRET')
            self.assertEqual(auth.load_token('web', explicit), 'FAKE_EXPLICIT_SECRET')
            explicit.write_text('')
            with self.assertRaises(auth.CredentialError):
                auth.load_token('web', explicit)
        with patch.dict(os.environ, {'MATPOOL_WEB_TOKEN': ''}):
            with self.assertRaises(auth.CredentialError):
                auth.load_token('web')
        self.assertEqual(auth.load_token('web'), 'FAKE_SAVED_SECRET')
        with self.assertRaises(auth.CredentialError):
            auth.load_token('paas')

    def test_status_does_not_connect_or_read_browser_and_never_displays_token(self):
        auth.save_token('web', 'FAKE_STATUS_SECRET')
        with patch.object(web, 'request') as web_request, patch.object(paas, 'request') as paas_request:
            code, out, err = self.run_cli('status')
        self.assertEqual(code, 0)
        states = json.loads(out)['credentials']
        self.assertTrue(states[0]['configured'])
        self.assertFalse(states[0]['verified'])
        self.assertFalse(states[1]['configured'])
        self.assertNotIn('FAKE_STATUS_SECRET', out + err)
        web_request.assert_not_called()
        paas_request.assert_not_called()

    def test_invalid_environment_status_is_not_reported_valid(self):
        with patch.dict(os.environ, {'MATPOOL_WEB_TOKEN': 'bad\nFAKE_SECRET'}):
            code, out, err = self.run_cli('status', '--service', 'web')
        self.assertEqual(code, 2)
        state = json.loads(out)['credentials'][0]
        self.assertFalse(state['local_format_valid'])
        self.assertEqual(state['source'], 'environment')
        self.assertNotIn('FAKE_SECRET', out + err)

    def test_noninteractive_init_fails_before_getpass(self):
        with patch.object(auth.sys.stdin, 'isatty', return_value=False), patch.object(auth.getpass, 'getpass') as prompt:
            code, out, err = self.run_cli('init', '--service', 'web')
        self.assertEqual(code, 2)
        self.assertIn('interactive terminal', err)
        self.assertFalse(self.folder.exists())
        prompt.assert_not_called()

    def test_hidden_input_and_echo_failure(self):
        with patch.object(auth.sys.stdin, 'isatty', return_value=True), patch.object(
                auth.getpass, 'getpass', return_value='FAKE_HIDDEN_SECRET'):
            code, out, err = self.run_cli('init', '--service', 'web')
        self.assertEqual(code, 0)
        self.assertNotIn('FAKE_HIDDEN_SECRET', out + err)
        with patch.object(auth.sys.stdin, 'isatty', return_value=True), patch.object(
                auth.getpass, 'getpass', side_effect=getpass.GetPassWarning('FAKE_WARNING_SECRET')):
            code, out, err = self.run_cli('init', '--service', 'paas')
        self.assertEqual(code, 2)
        self.assertFalse(auth.token_path('paas').exists())
        self.assertNotIn('FAKE_WARNING_SECRET', out + err)

    def test_invalid_tokens_are_rejected_before_writing(self):
        for value in ['', 'Bearer ', 'fake\ninjected', 'fake\rinjected', 'fake\tinjected', '中文']:
            with self.subTest(value=value), self.assertRaises(auth.CredentialError):
                auth.save_token('web', value)
        self.assertFalse(self.folder.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX mode and unprivileged symlink checks')
    def test_unsafe_directory_and_symlinks_refused(self):
        self.folder.mkdir(mode=0o755)
        with self.assertRaises(auth.CredentialError):
            auth.save_token('web', 'FAKE_SECRET')
        self.folder.chmod(0o700)
        outside = Path(self.temp.name) / 'outside'
        outside.write_text('keep')
        auth.token_path('web').symlink_to(outside)
        with self.assertRaises(auth.CredentialError):
            auth.save_token('web', 'FAKE_SECRET', replace=True)
        self.assertEqual(outside.read_text(), 'keep')
        link = Path(self.temp.name) / 'linked-config'
        link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(auth.CredentialError):
            auth.save_token('paas', 'FAKE_SECRET', folder=link)

    def test_failed_atomic_replace_preserves_existing_credential(self):
        auth.save_token('web', 'FAKE_ORIGINAL')
        with patch.object(auth.os, 'replace', side_effect=OSError('FAKE_EXCEPTION_SECRET')):
            with self.assertRaises(OSError):
                auth.save_token('web', 'FAKE_NEW', replace=True)
        self.assertEqual(auth.load_token('web'), 'FAKE_ORIGINAL')
        self.assertEqual(list(self.folder.glob('.token-*')), [])

    def test_check_uses_only_service_get_and_sanitizes_response(self):
        for service, module, route in [('web', web, '/nodes'), ('paas', paas, '/v1/job/stats')]:
            with self.subTest(service=service):
                auth.save_token(service, 'FAKE_CHECK_SECRET')
                with patch.object(module, 'request', return_value=(200, {
                        'code': 0, 'msg': 'FAKE_CHECK_SECRET', 'password': 'FAKE_ACCOUNT_SECRET'})) as request:
                    code, out, err = self.run_cli('check', '--service', service)
                self.assertEqual(code, 0)
                self.assertTrue(json.loads(out)['verified'])
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[:2], ('GET', route))
                self.assertNotIn('FAKE_CHECK_SECRET', out + err)
                self.assertNotIn('FAKE_ACCOUNT_SECRET', out + err)

    def test_check_rejects_http_and_business_failures_without_retry(self):
        auth.save_token('web', 'FAKE_CHECK_SECRET')
        for status, code in [(200, 176), (401, 0), (200, False), (200, '0'), (200, None), (200, 'FAKE_ECHO_SECRET')]:
            with self.subTest(status=status, code=code), patch.object(
                    web, 'request', return_value=(status, {'code': code})) as request:
                result, out, err = self.run_cli('check', '--service', 'web')
                self.assertEqual(result, 1)
                self.assertFalse(json.loads(out)['verified'])
                self.assertEqual(request.call_count, 1)
                self.assertNotIn('FAKE_ECHO_SECRET', out + err)

    def test_check_transport_errors_do_not_leak_credentials(self):
        auth.save_token('paas', 'FAKE_NETWORK_SECRET')
        with patch.object(paas, 'request', side_effect=OSError('FAKE_NETWORK_SECRET')) as request:
            code, out, err = self.run_cli('check', '--service', 'paas')
        self.assertEqual(code, 2)
        self.assertNotIn('FAKE_NETWORK_SECRET', out + err)
        self.assertEqual(request.call_count, 1)

    def test_both_clients_use_initialized_files(self):
        for service, module, command in [('web', web, 'nodes'), ('paas', paas, 'stats')]:
            with self.subTest(service=service):
                auth.save_token(service, 'FAKE_' + service)
                with patch.object(module, 'request', return_value=(200, {'code': 0})) as request:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(module.main([command]), 0)
                token_index = 2 if service == 'web' else 4
                self.assertEqual(request.call_args.args[token_index], 'FAKE_' + service)

    def test_preview_and_unauthenticated_probe_do_not_load_saved_token(self):
        for module, command in [(web, 'release'), (paas, 'cancel')]:
            with patch.object(module, 'load_token') as load, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main([command, '123']), 0)
                load.assert_not_called()
        with patch.object(paas, 'load_token') as load, patch.object(
                paas, 'request', return_value=(200, {'code': 176})) as request:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(paas.main(['probe']), 1)
            load.assert_not_called()
            self.assertEqual(request.call_args.args[4], '')

    def test_cli_entrypoint_and_custom_directory(self):
        custom = Path(self.temp.name) / 'custom'
        env = dict(os.environ, MATPOOL_PAAS_TOKEN='FAKE_SUBPROCESS_SECRET')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/matpool_auth.py'),
                                 '--config-dir', str(custom), 'init', '--service', 'paas', '--from-env'],
                                env=env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.folder.exists())
        self.assertEqual((custom / 'paas.token').read_text(), 'FAKE_SUBPROCESS_SECRET\n')
        self.assertNotIn('FAKE_SUBPROCESS_SECRET', result.stdout + result.stderr)
        for name in ['matpool_auth.py', 'matpool_api.py', 'matpool_web.py']:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts' / name), '--help'],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
