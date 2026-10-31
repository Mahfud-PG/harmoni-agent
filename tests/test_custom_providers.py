"""Isolated tests: no application startup, .env, or real provider calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def registry(self):
        path = ROOT / 'sari_core/custom_providers.py'
        self.assertTrue(path.exists(), 'Custom provider registry is not implemented')
        spec = importlib.util.spec_from_file_location('custom_providers_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Registry(Path(self.tmp.name))

    def test_profiles_keep_distinct_identity_and_never_list_secrets(self):
        r = self.registry()
        a = r.save(name='First', base_url='https://one.example/v1', api_key='secret-A')
        b = r.save(name='Second', base_url='https://two.example/v1', api_key='secret-B')
        self.assertNotEqual(a['id'], b['id'])
        self.assertNotIn('secret-', json.dumps(r.list()))
        self.assertEqual(r.resolve(a['id'])['api_key'], 'secret-A')
        self.assertEqual(r.resolve(b['id'])['api_key'], 'secret-B')
        edited = r.save(profile_id=a['id'], name='Renamed', base_url=a['base_url'])
        self.assertEqual(edited['id'], a['id'])
        self.assertEqual(r.resolve(a['id'])['api_key'], 'secret-A')
        self.assertEqual(len(self.registry().list()), 2)

    def test_url_and_credentials_are_explicit(self):
        r = self.registry()
        for url in ['ftp://host/v1', 'https://u:p@host/v1', 'https://host/v1?q=x', 'https://host/#x', 'https://host/?', 'http://remote.example/v1']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                r.save(name='Bad', base_url=url, api_key='secret')
        with self.assertRaises(ValueError):
            r.save(name='Missing', base_url='https://host/v1')
        a = r.save(name='Local', base_url='http://127.0.0.1:9999/v1/', no_auth=True)
        self.assertEqual(a['base_url'], 'http://127.0.0.1:9999/v1')
        b = r.save(name='Key', base_url='https://host/v1', api_key='secret')
        with self.assertRaises(ValueError):
            r.save(profile_id=b['id'], name='Moved', base_url='https://other/v1')
        r.delete(a['id'])
        with self.assertRaises(ValueError):
            r.resolve(a['id'])

class ModelTests(RegistryTests):
    def load_config(self):
        import sys
        import types
        from unittest.mock import patch
        root = Path(self.tmp.name)
        paths = types.ModuleType('sari_core.paths')
        paths.PROJECT_ROOT = paths.DATA_ROOT = root
        paths.ENV_FILE = root / '.env'
        paths.OPENROUTER_CACHE_FILE = root / 'cache.json'
        spec = importlib.util.spec_from_file_location('sari_core.custom_providers', ROOT / 'sari_core/custom_providers.py')
        custom = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(custom)
        isolation = patch.dict(sys.modules, {'sari_core.paths': paths, 'sari_core.custom_providers': custom})
        isolation.start()
        self.addCleanup(isolation.stop)
        spec = importlib.util.spec_from_file_location('isolated_model_config', ROOT / 'sari_core/model_config.py')
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config, custom

    def test_registration_selection_and_deletion_keep_exact_entry(self):
        cfg, custom = self.load_config()
        self.assertTrue(hasattr(cfg, 'add_profile_model'), 'Profile model registration missing')
        r = custom.registry()
        a = r.save(name='A', base_url='https://a.example/v1', api_key='A')
        b = r.save(name='B', base_url='https://b.example/v1', api_key='B')
        before = cfg.load_model_config()['active_id']
        first = cfg.add_profile_model(a['id'], 'Same/CASE', 'First')
        second = cfg.add_profile_model(b['id'], 'Same/CASE', 'Second')
        self.assertNotEqual(first['entry_id'], second['entry_id'])
        self.assertEqual(cfg.load_model_config()['active_id'], before)
        self.assertTrue(cfg.set_active_model(first['entry_id'])[0])
        self.assertTrue(cfg.set_fallback_model(second['entry_id'])[0])
        self.assertEqual(cfg.resolve_model_for_task()['provider'], a['id'])
        with self.assertRaises(ValueError):
            cfg.delete_provider_profile(a['id'])
        self.assertFalse(cfg.remove_custom_model(second['entry_id'])[0])
        cfg.set_fallback_model('2')
        cfg.set_active_model('1')
        self.assertTrue(cfg.remove_custom_model(first['entry_id'])[0])
        self.assertIn(second['entry_id'], cfg.load_model_config()['available_models'])
        cfg.delete_provider_profile(a['id'])
        self.assertEqual(len(r.list()), 1)
        cfg.set_specialist('system', second['entry_id'])
        self.assertEqual(cfg.resolve_model_for_task(domain='system')['id'], second['entry_id'])
        self.assertFalse(cfg.remove_custom_model(second['entry_id'])[0])

    def test_legacy_add_dispatches_custom_without_heuristics(self):
        cfg, custom = self.load_config()
        a = custom.registry().save(name='Chosen', base_url='https://chosen.example/v1', api_key='A')
        from unittest.mock import patch
        with patch('openai.OpenAI', side_effect=AssertionError('Unexpected network client')):
            ok, _, info = cfg.verify_and_add_model('ag/Exact-CASE', 'Opus', a['id'])
        self.assertTrue(ok)
        self.assertEqual(info['provider'], a['id'])
        self.assertEqual(info['id'], 'ag/Exact-CASE')

    def test_brain_selection_preserves_profiles_for_same_model(self):
        import textwrap
        from unittest.mock import patch
        import sys
        cfg, custom = self.load_config()
        r = custom.registry()
        a = r.save(name='A', base_url='https://a.example/v1', api_key='A')
        b = r.save(name='B', base_url='https://b.example/v1', api_key='B')
        first = cfg.add_profile_model(a['id'], 'gpt-4o', 'First')
        second = cfg.add_profile_model(b['id'], 'gpt-4o', 'Second')
        cfg.set_active_model(first['entry_id'])
        cfg.set_fallback_model(second['entry_id'])
        source = (ROOT / 'sari_core/brain.py').read_text(encoding='utf-8')
        start = source.index('        # Periksa apakah chosen_model_id')
        end = source.index('        # Rotasi multi-akun Groq', start)
        block = textwrap.dedent(source[start:end])
        env = dict(load_model_config=cfg.load_model_config, chosen_model_id='gpt-4o',
                   task_info=cfg.resolve_model_for_task(), model_candidates={},
                   get_provider_keys=lambda p: [], openrouter_key='WRONG', openai_key='WRONG',
                   deepseek_key=None, mimo_key=None, os=__import__('os'),
                   OpenAI=lambda **kwargs: kwargs)
        with patch.dict(sys.modules, {'sari_core.model_config':cfg}):
            exec(block, env)
        providers = env['providers']
        self.assertEqual(len(providers), 2)
        self.assertEqual(str(providers[0]['client'].base_url), 'https://a.example/v1/')
        self.assertEqual(str(providers[1]['client'].base_url), 'https://b.example/v1/')
        self.assertEqual(providers[0]['client'].api_key, 'A')
        self.assertEqual(providers[1]['client'].api_key, 'B')
        for p in providers:
            p['client'].close()

class RouteTests(ModelTests):
    def test_routes_saved_profiles_manual_models_and_access(self):
        import ast
        import sys
        from unittest.mock import patch
        from fastapi import FastAPI, HTTPException, Request, Depends
        from fastapi.testclient import TestClient
        from pydantic import BaseModel, SecretStr
        from typing import Optional
        cfg, custom = self.load_config()
        tree = ast.parse((ROOT / 'server_core.py').read_text(encoding='utf-8'))
        names = {'CustomProviderRequest', 'CustomProbeRequest', 'CustomModelRequest',
                 '_custom_local_access', 'custom_provider_list', 'custom_provider_save',
                 'custom_provider_delete', 'custom_provider_discover', 'custom_provider_test',
                 'custom_provider_add_model'}
        nodes = [n for n in tree.body if getattr(n, 'name', '') in names]
        self.assertEqual(len(nodes), len(names), 'Custom routes/schemas missing')
        app = FastAPI()
        env = dict(app=app, BaseModel=BaseModel, SecretStr=SecretStr, Optional=Optional,
                   HTTPException=HTTPException, Request=Request, Depends=Depends)
        with patch.dict(sys.modules, {'sari_core.model_config':cfg}):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), '<isolated routes>', 'exec'), env)
            client = TestClient(app, client=('127.0.0.1', 1234))
            response = client.post('/custom-providers', json={'name':'API', 'base_url':'https://host/v1','api_key':'secret'})
            self.assertEqual(response.status_code, 200, response.text)
            profile_id = response.json()['profile']['id']
            self.assertNotIn('secret', client.get('/custom-providers').text)
            result = client.post('/custom-providers/'+profile_id+'/models', json={'model_id':'ag/Exact-CASE','display_name':'Opus'})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['info']['id'], 'ag/Exact-CASE')
            self.assertEqual(result.json()['info']['provider'], profile_id)
            self.assertEqual(client.delete('/custom-providers/'+profile_id).status_code, 400)
            self.assertEqual(client.get('/custom-providers', headers={'Origin':'https://evil.example'}).status_code, 403)
            remote = TestClient(app, client=('203.0.113.1', 42))
            self.assertEqual(remote.get('/custom-providers').status_code, 403)

class UITests(unittest.TestCase):
    def test_accessible_explicit_custom_controls(self):
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = {}
                self.labels = set()
            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if 'id' in a:
                    self.ids[a['id']] = a
                if tag == 'label':
                    self.labels.add(a.get('for'))
        parser = Parser()
        source = (ROOT / 'index.html').read_text(encoding='utf-8')
        parser.feed(source)
        for name in ['cp-profile', 'cp-name', 'cp-url', 'cp-key', 'cp-no-auth', 'cp-model', 'cp-model-name']:
            self.assertIn(name, parser.ids)
            self.assertIn(name, parser.labels)
        self.assertEqual(parser.ids['cp-key']['type'], 'password')
        self.assertEqual(parser.ids['cp-status']['aria-live'], 'polite')
        for action in ['save', 'discover', 'chat', 'tools', 'add', 'delete']:
            self.assertIn('cp-'+action, parser.ids)

class ErrorTests(unittest.TestCase):
    def test_custom_inference_errors_do_not_expose_upstream_body(self):
        import ast
        import textwrap
        source = (ROOT / 'sari_core/brain.py').read_text(encoding='utf-8')
        start = source.index('                err_msg = str(e)', source.index('# === EKSEKUSI DENGAN RANTAI'))
        line = source[start:source.index('\n', start)]
        env = {'e': ValueError('SECRET upstream echo'), 'provider': {'custom_profile': True}}
        exec(textwrap.dedent(line), env)
        self.assertNotIn('SECRET', env['err_msg'])

class HTTPTests(RegistryTests):
    def test_mock_discovery_chat_tools_auth_redirect_and_errors(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.respond()
            def do_POST(self):
                self.respond()
            def respond(self):
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                seen.append((self.path, self.headers.get('Authorization'), body))
                if self.path.startswith('/redirect'):
                    self.send_response(302)
                    self.send_header('Location', '/stolen')
                    self.end_headers()
                    return
                if self.path.startswith('/error'):
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'secret-A')
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                message = {'role': 'assistant', 'content': 'OK'}
                if body.get('tools'):
                    message['tool_calls'] = [{'id':'call_1', 'type':'function', 'function':{'name':'harmoni_probe', 'arguments':'{}'}}]
                payload = {'data':[{'id':'Case/Sensitive'}]} if self.command == 'GET' else {'id':'x', 'choices':[{'index':0, 'message':message, 'finish_reason':'stop'}]}
                self.wfile.write(json.dumps(payload).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        r = self.registry()
        self.assertTrue(hasattr(r, 'probe'), 'Explicit provider probes are not implemented')
        base = 'http://127.0.0.1:' + str(server.server_port)
        a = r.save(name='Mock', base_url=base+'/v1', api_key='secret-A')
        self.assertEqual(r.discover(a['id']), ['Case/Sensitive'])
        self.assertEqual(r.probe(a['id'], 'Case/Sensitive', tools=False), {'chat':True, 'tools':None})
        self.assertEqual(r.probe(a['id'], 'Case/Sensitive', tools=True), {'chat':True, 'tools':True})
        self.assertEqual(seen[-1][0:2], ('/v1/chat/completions', 'Bearer secret-A'))
        self.assertEqual(seen[-1][2]['model'], 'Case/Sensitive')
        local = r.save(name='Local', base_url=base+'/v1', no_auth=True)
        r.probe(local['id'], 'Case/Sensitive')
        self.assertIsNone(seen[-1][1])
        for endpoint in ('redirect', 'error'):
            p = r.save(name='Failure', base_url=base+'/'+endpoint, api_key='secret-A')
            with self.assertRaises(ValueError) as error:
                r.probe(p['id'], 'Case/Sensitive')
            self.assertNotIn('secret-A', str(error.exception))
        self.assertFalse(any(path == '/stolen' for path, _, _ in seen))

if __name__ == '__main__':
    unittest.main()
