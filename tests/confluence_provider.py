"""A loopback-only HTTPS Confluence Data Center fixture with synthetic records."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
import json
from pathlib import Path
import secrets
import ssl
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


PAGE_ID = '27182'
PAGE = {'title': '점검 기준서', 'id': PAGE_ID, 'type': 'page'}
CHILDREN = [{'title': '교대 점검표', 'id': '31415', 'type': 'page'},
            {'title': '주간 점검표', 'id': '31416', 'type': 'page'}]


def local_certificate(directory):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Local test Confluence')])
    now = datetime.now(timezone.utc)
    key_id = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
            .add_extension(key_id, critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(key_id), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address('127.0.0.1'))]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = Path(directory) / 'local.crt', Path(directory) / 'local.key'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return cert_path, key_path


@contextmanager
def confluence_provider(directory):
    """Yield server.base_url, .bearer, .ca for the real product HTTP transport."""
    cert_path, key_path = local_certificate(directory)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            authenticated = self.headers.get('Authorization') == self.server.bearer
            self.server.records.append((url.path, query, authenticated))
            status = self.server.upstream_status if authenticated else 401
            if status != 200:
                payload = {'message': 'private fixture diagnostic'}
            elif url.path == '/rest/api/content/' + PAGE_ID:
                payload = {**PAGE, '_links': {'webui': '/pages/' + PAGE_ID}}
            elif url.path == '/rest/api/content/' + PAGE_ID + '/child/page':
                children = self.server.children[:int(query.get('limit', ['25'])[0])]
                payload = {'results': children, 'start': 0, 'limit': int(query.get('limit', ['25'])[0]),
                           'size': len(children), '_links': {}}
            else:
                status, payload = 404, {'message': 'Unknown content ID'}
            body = json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.ca = str(cert_path)
        server.bearer = 'Bearer ' + secrets.token_urlsafe(24)
        server.base_url = f'https://127.0.0.1:{server.server_port}/rest/api'
        server.records = []
        server.children = CHILDREN
        server.upstream_status = 200
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.025}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()
