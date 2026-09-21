import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import matpool_api as paas
import matpool_web as web
from make_torch_startup import build


class ClientsTest(unittest.TestCase):
    def test_examples_cannot_be_submitted_unchanged(self):
        for name, prepare in [('rent', web.prepare_rent), ('job', paas.prepare_fields)]:
            with self.subTest(name=name), self.assertRaises(paas.InputError):
                prepare(json.loads((ROOT / 'examples' / (name + '.example.json')).read_text()))

    def test_default_mutations_do_not_connect(self):
        for module, command in [(web, 'release'), (paas, 'cancel')]:
            with self.subTest(command=command), patch.object(module, 'request') as request:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(module.main([command, '123']), 0)
                self.assertTrue(json.loads(output.getvalue())['preview'])
                request.assert_not_called()

    def test_website_summary_excludes_connection_details(self):
        result = {'code': 0, 'token': 'FAKE_TEST_SECRET', 'userNode': {
            'node': {'id': 123, 'password': 'FAKE_TEST_SECRET'},
            'status': 2, 'urls': ['https://example.invalid/?token=FAKE_TEST_SECRET']}}
        output = json.dumps(web.summary(result))
        self.assertNotIn('FAKE_TEST_SECRET', output)
        self.assertEqual(web.summary(result)['nodes'][0]['id'], 123)

    def test_paas_redacts_nested_secrets(self):
        output = paas.redact({'job': [{'envs': 'PRIVATE=example', 'password': 'example',
                                      'msg': 'token FAKE_TEST_SECRET'}]}, 'FAKE_TEST_SECRET')
        self.assertNotIn('PRIVATE=example', json.dumps(output))
        self.assertNotIn('FAKE_TEST_SECRET', json.dumps(output))

    def test_website_delete_uses_json_body_and_header(self):
        with patch.object(web.urllib.request, 'build_opener') as factory:
            response = factory.return_value.open.return_value
            response.code = 200
            response.read.return_value = b'{"code":0}'
            self.assertEqual(web.request('DELETE', '/node', 'FAKE_TEST_SECRET', body={'id': 123}),
                             (200, {'code': 0}))
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'DELETE')
            self.assertEqual(json.loads(request.data), {'id': 123})
            self.assertEqual(request.get_header('Authorization'), 'Bearer FAKE_TEST_SECRET')
            self.assertNotIn('FAKE_TEST_SECRET', request.full_url)

    def test_newline_in_credential_rejected_before_network(self):
        with patch.object(web.urllib.request, 'build_opener') as factory:
            with self.assertRaises(paas.InputError):
                web.request('GET', '/nodes', 'fake\ninjected')
            factory.assert_not_called()

    def test_redirects_are_not_followed(self):
        self.assertIsNone(paas.NoRedirect().redirect_request(
            None, None, 302, 'Found', {}, 'http://example.invalid'))

    def test_short_startup_limit_and_filename_validation(self):
        self.assertLessEqual(len(build('torch-result.json').encode()), 1024)
        with self.assertRaises(ValueError):
            build('../result.json')


if __name__ == '__main__':
    unittest.main()
