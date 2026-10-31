"""Explicit OpenAI-compatible profiles. No network activity on save/list/resolve."""
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid
from contextlib import contextmanager

_LOCK = threading.RLock()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def config_lock(root):
    """Serialize read/modify/write across threads and application processes."""
    with _LOCK:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        with open(root / '.custom-provider.lock', 'a+b') as handle:
            handle.seek(0, 2)
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def validate_url(value):
    from urllib.parse import urlsplit
    import ipaddress
    try:
        url = urlsplit(value)
        port = url.port
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username is not None
                or url.password is not None or '?' in value or '#' in value
                or '\\' in value or any(c.isspace() or ord(c) < 32 for c in value)):
            raise ValueError()
        local = url.hostname == 'localhost'
        try:
            ip = ipaddress.ip_address(url.hostname)
            local = local or ip.is_loopback or ip.is_private
        except ValueError:
            pass
        if url.scheme == 'http' and not local:
            raise ValueError()
    except Exception:
        raise ValueError('URL harus HTTP(S), tanpa kredensial/query/fragmen; HTTP hanya alamat lokal.') from None
    return value.rstrip('/')


class Registry:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'custom_providers.json'
        self.secret_dir = self.root / '.provider_keys'

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except Exception:
            raise ValueError('Penyimpanan provider tidak dapat dibaca.') from None

    @staticmethod
    def _public(record):
        return {k: record[k] for k in ('id', 'name', 'base_url', 'no_auth')} | {'has_key': bool(record.get('secret_ref'))}

    def list(self):
        return [self._public(p) for p in self._read().values()]

    def resolve(self, profile_id):
        record = self._read().get(profile_id)
        if record is None:
            raise ValueError('Profil provider tidak ditemukan.')
        key = ''
        if record.get('secret_ref'):
            try:
                key = (self.secret_dir / record['secret_ref']).read_text(encoding='utf-8')
            except Exception:
                raise ValueError('Kunci profil tidak dapat dibaca; simpan ulang kunci.') from None
        return self._public(record) | {'api_key': key}

    def client(self, profile_id):
        import httpx
        from openai import OpenAI
        profile = self.resolve(profile_id)
        validate_url(profile['base_url'])
        def protect(request):
            if profile['no_auth']:
                request.headers.pop('Authorization', None)
        transport = httpx.Client(follow_redirects=False, trust_env=False,
                                 event_hooks={'request': [protect]}, timeout=25)
        return OpenAI(base_url=profile['base_url'], api_key=profile['api_key'] or 'no-auth',
                      http_client=transport, max_retries=0)

    def discover(self, profile_id):
        try:
            with self.client(profile_id) as client:
                result = client.models.list()
                return [m.id for m in result.data if isinstance(m.id, str)]
        except Exception:
            raise ValueError('Discovery gagal. Masukkan model ID secara manual; periksa URL dan autentikasi.') from None

    def probe(self, profile_id, model_id, tools=False):
        if not model_id or model_id != model_id.strip():
            raise ValueError('Model ID wajib diisi persis tanpa spasi tepi.')
        options = {}
        if tools:
            options = {'tools': [{'type': 'function', 'function': {'name': 'harmoni_probe',
                       'description': 'Harmless capability probe, never executed',
                       'parameters': {'type': 'object', 'properties': {}}}}],
                       'tool_choice': {'type': 'function', 'function': {'name': 'harmoni_probe'}}}
        try:
            with self.client(profile_id) as client:
                result = client.chat.completions.create(model=model_id,
                    messages=[{'role': 'user', 'content': 'Say OK or call harmoni_probe if offered.'}],
                    max_tokens=64, **options)
                message = result.choices[0].message
                tool_ok = bool(message.tool_calls and any(t.function.name == 'harmoni_probe' for t in message.tool_calls))
                if not (message.content or tool_ok):
                    raise ValueError()
                return {'chat': True, 'tools': tool_ok if tools else None}
        except Exception:
            raise ValueError('Tes provider gagal. Periksa URL, kunci, model, dan dukungan chat/tools.') from None

    def delete(self, profile_id):
        with config_lock(self.root):
            records = self._read()
            if profile_id not in records:
                raise ValueError('Profil provider tidak ditemukan.')
            old = records.pop(profile_id)
            atomic_json(self.path, records)
            if old.get('secret_ref'):
                (self.secret_dir / old['secret_ref']).unlink(missing_ok=True)

    def save(self, *, name, base_url, api_key=None, no_auth=False, profile_id=None):
        base_url = validate_url(base_url)
        if api_key is not None and any(ord(c) < 32 for c in api_key):
            raise ValueError('Format kunci tidak valid.')
        if not name.strip():
            raise ValueError('Nama provider wajib diisi.')
        with config_lock(self.root):
            records = self._read()
            if profile_id and profile_id not in records:
                raise ValueError('Profil provider tidak ditemukan.')
            profile_id = profile_id or 'custom-' + uuid.uuid4().hex
            previous = records.get(profile_id, {})
            secret_ref = previous.get('secret_ref')
            if previous and previous['base_url'] != base_url and not (api_key or no_auth):
                raise ValueError('URL berubah: masukkan kunci baru atau pilih tanpa autentikasi.')
            if not no_auth and not (api_key or secret_ref):
                raise ValueError('Masukkan kunci atau pilih tanpa autentikasi secara eksplisit.')
            if api_key:
                self.secret_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                secret_ref = uuid.uuid4().hex
                fd = os.open(self.secret_dir / secret_ref, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    handle.write(api_key)
                    handle.flush()
                    os.fsync(handle.fileno())
            if no_auth:
                secret_ref = None
            record = {'id': profile_id, 'name': name.strip(), 'base_url': base_url,
                      'no_auth': no_auth, 'secret_ref': secret_ref}
            records[profile_id] = record
            atomic_json(self.path, records)
            old = previous.get('secret_ref')
            if old and old != secret_ref:
                (self.secret_dir / old).unlink(missing_ok=True)
            return self._public(record)


def registry():
    from sari_core.paths import DATA_ROOT
    return Registry(DATA_ROOT)
