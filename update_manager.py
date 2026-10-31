"""Opt-in GitHub Releases updater; never runs an unverified installer."""
import hashlib
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

REPO = 'Mahfud-PG/harmoni-agent'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
MAX_JSON = 1024 * 1024
MAX_INSTALLER = 800 * 1024 * 1024
ASSET_NAME = 'HarmoniAgent-Setup.exe'
MANIFEST_NAME = 'update-manifest.json'


class UpdateError(Exception):
    pass


def parse_version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    if not match:
        raise UpdateError('Versi rilis tidak valid.')
    return tuple(map(int, match.groups()))


class UpdateManager:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    @property
    def config_path(self):
        return self.data_dir / 'update-settings.json'

    def enabled(self):
        try:
            return json.loads(self.config_path.read_text(encoding='utf-8')).get('auto_check') is True
        except (OSError, ValueError, TypeError):
            return False

    def set_enabled(self, enabled):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps({'auto_check': enabled is True}), encoding='utf-8')
        return self.enabled()

    def _open(self, url):
        if urllib.parse.urlsplit(url).scheme != 'https':
            raise UpdateError('Pembaruan harus memakai HTTPS.')
        request = urllib.request.Request(url, headers={'User-Agent': 'HarmoniAgent-Updater',
                                                       'Accept': 'application/vnd.github+json'})
        response = urllib.request.urlopen(request, timeout=25)
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != 'https' or final.hostname not in (
                'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
                'objects.githubusercontent.com'):
            response.close()
            raise UpdateError('Alamat pengalihan unduhan tidak tepercaya.')
        return response

    def _json(self, url):
        with self._open(url) as response:
            raw = response.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise UpdateError('Metadata pembaruan terlalu besar.')
        return json.loads(raw)

    def validate_release(self, release, manifest, current_version):
        if release.get('draft') or release.get('prerelease'):
            raise UpdateError('Rilis bukan versi stabil.')
        tag = release.get('tag_name', '')
        if parse_version(tag) <= parse_version(current_version):
            return None
        if not isinstance(manifest, dict) or manifest.get('version') != tag.lstrip('v'):
            raise UpdateError('Versi manifest tidak sesuai rilis.')
        if manifest.get('asset') != ASSET_NAME or not re.fullmatch(r'[0-9a-fA-F]{64}', str(manifest.get('sha256', ''))):
            raise UpdateError('Manifest installer atau SHA-256 tidak valid.')
        assets = [a for a in release.get('assets', []) if a.get('name') == ASSET_NAME]
        if len(assets) != 1:
            raise UpdateError('Installer rilis tidak tersedia atau ambigu.')
        url = assets[0].get('browser_download_url', '')
        expected = f'https://github.com/{REPO}/releases/download/{urllib.parse.quote(tag, safe="")}/{ASSET_NAME}'
        if url != expected:
            raise UpdateError('Alamat installer tidak sesuai repositori resmi.')
        return {'version': manifest['version'], 'asset': ASSET_NAME,
                'sha256': manifest['sha256'].lower(), 'url': url,
                'notes': str(release.get('body') or '')[:8000]}

    def check(self, current_version):
        release = self._json(API)
        if parse_version(release.get('tag_name', '')) <= parse_version(current_version):
            return None
        manifests = [a for a in release.get('assets', []) if a.get('name') == MANIFEST_NAME]
        if len(manifests) != 1:
            raise UpdateError('Manifest SHA-256 rilis tidak tersedia.')
        manifest_url = manifests[0].get('browser_download_url', '')
        expected = f'https://github.com/{REPO}/releases/download/{urllib.parse.quote(release["tag_name"], safe="")}/{MANIFEST_NAME}'
        if manifest_url != expected:
            raise UpdateError('Alamat manifest tidak tepercaya.')
        return self.validate_release(release, self._json(manifest_url), current_version)

    def download(self, release):
        version = release['version']
        parse_version(version)
        if release['asset'] != ASSET_NAME or not re.fullmatch(r'[0-9a-f]{64}', release['sha256']):
            raise UpdateError('Metadata unduhan tidak valid.')
        expected_url = f'https://github.com/{REPO}/releases/download/v{version}/{ASSET_NAME}'
        if release['url'] != expected_url:
            raise UpdateError('Alamat unduhan installer tidak valid.')
        directory = self.data_dir / 'updates' / version
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / ASSET_NAME
        partial = directory / (ASSET_NAME + '.part')
        digest = hashlib.sha256()
        size = 0
        try:
            with self._open(release['url']) as response, partial.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_INSTALLER:
                        raise UpdateError('Installer terlalu besar.')
                    digest.update(chunk)
                    output.write(chunk)
            if not size or digest.hexdigest() != release['sha256']:
                raise UpdateError('SHA-256 installer tidak cocok; berkas dibuang.')
            partial.replace(target)
            return target
        except Exception:
            partial.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise

    def install(self, path, expected_sha256):
        path = Path(path)
        if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256) or path.name != ASSET_NAME or path.parent.parent != self.data_dir / 'updates':
            raise UpdateError('Lokasi atau SHA-256 installer tidak valid.')
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise UpdateError('Installer berubah setelah diunduh; pemasangan dibatalkan.')
        if os.name != 'nt':
            raise UpdateError('Installer ini hanya untuk Windows.')
        subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
        return True
