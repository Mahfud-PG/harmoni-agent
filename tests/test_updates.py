import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from update_manager import UpdateError, UpdateManager, parse_version


class UpdatesTest(unittest.TestCase):
    def test_versions_are_numeric_and_strict(self):
        self.assertTrue(parse_version('v1.10.0') > parse_version('1.9.9'))
        with self.assertRaises(UpdateError):
            parse_version('1.2.3-preview')

    def test_manifest_must_match_release_asset_and_hash(self):
        manager = UpdateManager(Path(tempfile.gettempdir()))
        release = {'tag_name': 'v1.1.0', 'draft': False, 'prerelease': False,
                   'assets': [{'name': 'HarmoniAgent-Setup.exe', 'browser_download_url':
                               'https://github.com/Mahfud-PG/harmoni-agent/releases/download/v1.1.0/HarmoniAgent-Setup.exe'}]}
        manifest = {'version': '1.1.0', 'asset': 'HarmoniAgent-Setup.exe', 'sha256': 'a' * 64}
        self.assertEqual(manager.validate_release(release, manifest, '1.0.0')['sha256'], 'a' * 64)
        for bad in ({**manifest, 'sha256': 'bad'}, {**manifest, 'asset': '../evil.exe'},
                    {**manifest, 'version': '1.2.0'}):
            with self.subTest(bad=bad), self.assertRaises(UpdateError):
                manager.validate_release(release, bad, '1.0.0')
        with self.assertRaises(UpdateError):
            manager.validate_release({**release, 'prerelease': True}, manifest, '1.0.0')

    def test_check_requires_manifest_and_returns_release(self):
        manager = UpdateManager(Path(tempfile.gettempdir()))
        release = {'tag_name': 'v1.1.0', 'draft': False, 'prerelease': False,
                   'assets': [{'name': 'update-manifest.json', 'browser_download_url':
                               'https://github.com/Mahfud-PG/harmoni-agent/releases/download/v1.1.0/update-manifest.json'},
                              {'name': 'HarmoniAgent-Setup.exe', 'browser_download_url':
                               'https://github.com/Mahfud-PG/harmoni-agent/releases/download/v1.1.0/HarmoniAgent-Setup.exe'}]}
        manifest = {'version': '1.1.0', 'asset': 'HarmoniAgent-Setup.exe', 'sha256': 'a' * 64}
        with patch.object(manager, '_json', side_effect=[release, manifest]):
            self.assertEqual(manager.check('1.0.0')['version'], '1.1.0')
        with patch.object(manager, '_json', return_value={**release, 'assets': release['assets'][1:]}):
            with self.assertRaises(UpdateError):
                manager.check('1.0.0')

    def test_download_checks_digest_and_cleans_bad_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = UpdateManager(Path(directory))
            payload = b'installer bytes'
            release = {'version': '1.1.0', 'asset': 'HarmoniAgent-Setup.exe',
                       'sha256': hashlib.sha256(payload).hexdigest(),
                       'url': 'https://github.com/Mahfud-PG/harmoni-agent/releases/download/v1.1.0/HarmoniAgent-Setup.exe'}
            with patch.object(manager, '_open', return_value=io.BytesIO(payload)):
                result = manager.download(release)
            self.assertEqual(result.read_bytes(), payload)
            with patch.object(manager, '_open', return_value=io.BytesIO(b'wrong')):
                with self.assertRaises(UpdateError):
                    manager.download(release)
            self.assertFalse(result.exists())
            self.assertFalse(list(Path(directory).rglob('*.part')))

    def test_opt_in_defaults_off_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = UpdateManager(Path(directory))
            self.assertFalse(manager.enabled())
            manager.set_enabled(True)
            self.assertTrue(UpdateManager(Path(directory)).enabled())
            manager.set_enabled(False)
            self.assertFalse(manager.enabled())

    def test_download_rejects_untrusted_url(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = UpdateManager(Path(directory))
            with self.assertRaises(UpdateError):
                manager.download({'version': '1.1.0', 'asset': 'HarmoniAgent-Setup.exe',
                                  'sha256': 'a' * 64, 'url': 'https://evil.example/installer.exe'})

    def test_install_refuses_tampered_staged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = UpdateManager(Path(directory))
            path = Path(directory) / 'updates' / '1.1.0' / 'HarmoniAgent-Setup.exe'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'wrong')
            with patch('update_manager.subprocess.Popen') as launch:
                with self.assertRaises(UpdateError):
                    manager.install(path, 'a' * 64)
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
