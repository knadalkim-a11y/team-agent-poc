"""Synthetic, offline candidate preparation tests; no live application imports."""

import base64
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from scripts import ees_deploy_release as release


COMMIT = "a" * 40


def digest(value):
    return hashlib.sha256(value).hexdigest()


def wheel_bytes(corrupt_record=False, distribution="open_webui", version=release.branding.VERSION):
    info = f"{distribution}-{version}.dist-info/"
    dependency = "Requires-Dist: example==1.0\n" if distribution == "open_webui" else ""
    members = {
        info + "METADATA": (f"Metadata-Version: 2.1\nName: {distribution.replace('_', '-')}\nVersion: {version}\n" + dependency).encode(),
        info + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        info + "licenses/LICENSE": b"synthetic license fixture\n",
        distribution + "/__init__.py": b"raise RuntimeError('Application must never be imported')\n",
    }
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, content in members.items():
        encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + encoded, str(len(content))])
    writer.writerow([info + "RECORD", "", ""])
    members[info + "RECORD"] = record.getvalue().encode()
    if corrupt_record:
        members["open_webui/__init__.py"] += b"# unexpected change\n"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


class WindowsCaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic EES test CA")])
        now = datetime.now(timezone.utc)
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                       .public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                       .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                       .sign(key, hashes.SHA256()))
        cls.pem = certificate.public_bytes(serialization.Encoding.PEM)
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([
                    x509.NameAttribute(NameOID.COMMON_NAME, "ees-test.local")])).issuer_name(name)
                .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("ees-test.local")]), critical=False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        cls.leaf_pem = leaf.public_bytes(serialization.Encoding.PEM)
        cls.leaf_key = leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "candidate"
        self.target.mkdir()

    def prepare(self, payload=None):
        with mock.patch.object(release, "_collect_windows_ca", return_value=self.pem if payload is None else payload):
            return release.prepare_windows_ca(self.target, "candidate-python", {})

    def test_snapshot_is_immutable_reused_and_outside_venv(self):
        metadata = self.target / "release.json"
        metadata.write_bytes(b"preserved candidate metadata")
        fingerprint = self.prepare()
        path = release.windows_ca_path(self.target, fingerprint)
        self.assertEqual(path, self.target / "trusted-ca" / (digest(self.pem) + ".pem"))
        self.assertEqual(path.read_bytes(), self.pem)
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        before = path.stat().st_mtime_ns
        self.assertEqual(self.prepare(), fingerprint)
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual(metadata.read_bytes(), b"preserved candidate metadata")
        self.assertFalse((self.target / "venv").exists())

    def test_bad_export_is_rejected_without_creating_bundle(self):
        for payload in (b"", b"not a certificate", self.leaf_pem, self.pem + b"-----BEGIN PRIVATE KEY-----\nprivate\n",
                        b"-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"):
            with self.subTest(payload_kind=len(payload)):
                with self.assertRaises(release.ReleaseError):
                    self.prepare(payload)
                self.assertFalse((self.target / "trusted-ca").exists())

    def test_invalid_digest_missing_tampered_and_unparseable_snapshots_fail(self):
        for fingerprint in (None, [], "A" * 64, "../escape", "a" * 63, "a" * 64 + "\n"):
            with self.subTest(fingerprint=fingerprint):
                with self.assertRaises(release.ReleaseError):
                    release.windows_ca_path(self.target, fingerprint)
        with self.assertRaises(release.ReleaseError):
            release.windows_ca_path(self.target, "a" * 64)
        fingerprint = self.prepare()
        path = release.windows_ca_path(self.target, fingerprint)
        path.write_bytes(self.pem + b"\n")
        with self.assertRaisesRegex(release.ReleaseError, "changed"):
            release.windows_ca_path(self.target, fingerprint)
        with self.assertRaisesRegex(release.ReleaseError, "changed"):
            self.prepare()
        self.assertEqual(path.read_bytes(), self.pem + b"\n")
        invalid = b"not a public CA"
        (path.parent / (digest(invalid) + ".pem")).write_bytes(invalid)
        with self.assertRaisesRegex(release.ReleaseError, "valid public CA"):
            release.windows_ca_path(self.target, digest(invalid))

    def test_reparse_directory_or_file_is_rejected_without_overwrite(self):
        fingerprint = self.prepare()
        path = release.windows_ca_path(self.target, fingerprint)
        linked = release._linked
        for unsafe in (self.target, path.parent, path):
            with self.subTest(unsafe=unsafe.name), mock.patch.object(
                    release, "_linked", side_effect=lambda candidate: candidate == unsafe or linked(candidate)):
                with self.assertRaises(release.ReleaseError):
                    release.windows_ca_path(self.target, fingerprint)
                with self.assertRaises(release.ReleaseError):
                    self.prepare()
        self.assertEqual(path.read_bytes(), self.pem)
        with mock.patch.object(Path, "is_symlink", return_value=False), \
             mock.patch.object(Path, "exists", return_value=True), \
             mock.patch.object(Path, "lstat", return_value=mock.Mock(st_file_attributes=0x400)):
            self.assertTrue(release._linked(path))

    def test_hardlinked_snapshot_is_rejected(self):
        fingerprint = self.prepare()
        path = release.windows_ca_path(self.target, fingerprint)
        os.link(path, self.root / "other.pem")
        with self.assertRaisesRegex(release.ReleaseError, "regular file"):
            release.windows_ca_path(self.target, fingerprint)

    def test_collector_is_isolated_uses_saved_environment_and_removes_key_logging(self):
        environment = {"HTTPS_PROXY": "synthetic proxy", "SSL_CERT_FILE": "synthetic CA path",
                       "SSLKEYLOGFILE": "private key log", "sslkeylogfile": "another key log"}
        with mock.patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, self.pem)) as run:
            self.assertEqual(release._collect_windows_ca("candidate-python", environment, cwd=self.root), self.pem)
        command = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(command[:5], ["candidate-python", "-I", "-S", "-B", "-c"])
        self.assertNotIn("open_webui", command[5])
        self.assertEqual(options["env"], {"HTTPS_PROXY": "synthetic proxy", "SSL_CERT_FILE": "synthetic CA path"})
        self.assertEqual(options["timeout"], 30)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(options["cwd"], self.root)
        self.assertTrue(options["check"] and options["capture_output"])
        self.assertEqual(environment["SSLKEYLOGFILE"], "private key log")

    def test_export_process_failures_are_sanitized_and_leave_no_bundle(self):
        for failure in (subprocess.TimeoutExpired("synthetic-private", 30, output=b"secret", stderr=b"secret"),
                        subprocess.CalledProcessError(1, "synthetic-private", stderr=b"secret"),
                        OSError("synthetic-private")):
            with self.subTest(error=type(failure).__name__), mock.patch.object(release.subprocess, "run", side_effect=failure):
                with self.assertRaises(release.ReleaseError) as caught:
                    release.prepare_windows_ca(self.target, "candidate-python", {})
                self.assertNotIn("synthetic-private", str(caught.exception))
                self.assertNotIn("secret", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertFalse((self.target / "trusted-ca").exists())

    def test_real_export_requires_windows(self):
        environment = {k: v for k, v in os.environ.items() if k.upper() not in {"SSL_CERT_FILE", "SSL_CERT_DIR"}}
        if sys.platform == "win32":
            payload = release._collect_windows_ca(sys.executable, environment)
            release._validate_ca_payload(payload)
        else:
            with self.assertRaisesRegex(release.ReleaseError, "Windows CA export failed"):
                release._collect_windows_ca(sys.executable, environment)

    def test_snapshot_verifies_tls_chain_and_still_rejects_hostname_or_untrusted_ca(self):
        bundle = release.windows_ca_path(self.target, self.prepare())
        cert_path, key_path = self.root / "server.pem", self.root / "server-key.pem"
        cert_path.write_bytes(self.leaf_pem + self.pem)
        key_path.write_bytes(self.leaf_key)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path, key_path)

        def handshake(hostname, trusted):
            client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            if trusted:
                client_context.load_verify_locations(cafile=str(bundle))
            incoming, outgoing, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
            client = client_context.wrap_bio(incoming, outgoing, server_hostname=hostname)
            server = server_context.wrap_bio(server_in, server_out, server_side=True)
            for _ in range(10):
                client_done = server_done = False
                try:
                    client.do_handshake()
                    client_done = True
                except ssl.SSLWantReadError:
                    pass
                server_in.write(outgoing.read())
                try:
                    server.do_handshake()
                    server_done = True
                except ssl.SSLWantReadError:
                    pass
                incoming.write(server_out.read())
                if client_done and server_done:
                    return
            self.fail("Synthetic TLS handshake did not finish")

        handshake("ees-test.local", True)
        for hostname, trusted in (("other-test.local", True), ("ees-test.local", False)):
            with self.subTest(hostname=hostname, trusted=trusted), self.assertRaises(ssl.SSLCertVerificationError):
                handshake(hostname, trusted)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / ("EES-demo-" + COMMIT[:12] + ".zip")
        self.target = self.root / "candidate"
        self.source_python = self.root / "source-python.exe"
        self.uv = self.root / "uv.exe"
        self.source_python.write_bytes(b"existing interpreter placeholder")
        self.uv.write_bytes(b"existing uv placeholder")
        self.prepare_members()
        self.write_bundle()

    def prepare_members(self, corrupt_record=False):
        wheel = wheel_bytes(corrupt_record)
        branding = {
            "schema_version": 1, "upstream_version": "0.11.3", "version": "0.11.3+ees.2",
            "source": {"filename": release.branding.SOURCE_FILENAME, "sha256": release.branding.SOURCE_SHA256},
            "wheel": {"filename": release.branding.WHEEL_FILENAME, "sha256": digest(wheel), "size": len(wheel)},
        }
        self.members = {name: b"synthetic documentation\n" for name in release.bundles.GUIDES}
        self.members.update({"agent-pack/skill.md": b"synthetic skill\n", "BUNDLE-README.md": b"fixture\n",
                             "branding/manifest.json": json.dumps(branding).encode(),
                             "branding/" + release.branding.WHEEL_FILENAME: wheel})
        self.manifest = {"schema_version": 1, "source_commit": COMMIT, "source_dirty": False,
                         "source_url": release.bundles.REPOSITORY_URL + "/tree/" + COMMIT, "branding": branding}

    def write_bundle(self, extras=(), altered=None, compression=zipfile.ZIP_STORED):
        self.manifest["files"] = [{"path": name, "size": len(content), "sha256": digest(content)}
                                  for name, content in self.members.items()]
        with zipfile.ZipFile(self.bundle, "w", compression=compression) as archive:
            for name, content in self.members.items():
                archive.writestr(name, altered.get(name, content) if altered else content)
            archive.writestr("manifest.json", json.dumps(self.manifest).encode())
            for name, content in extras:
                archive.writestr(name, content)

    def baseline(self, after=False):
        return {"python_version": "3.11.9 (synthetic Windows runtime)", "platform": "win32",
                "packages": {"open-webui": "0.11.3+ees.2" if after else "0.11.3", "example": "1.0"},
                "requires": ["example==1.0"]}

    def prepare(self, **kwargs):
        return release.prepare_release(self.bundle, COMMIT, self.target, self.source_python, self.uv, **kwargs)

    def test_validated_extraction_does_not_import_application(self):
        result = release.validate_bundle(self.bundle, COMMIT)
        self.assertEqual(result["source_commit"], COMMIT)
        self.assertFalse(self.target.exists())
        release.extract_bundle(self.bundle, COMMIT, self.target)
        self.assertEqual((self.target / "agent-pack/skill.md").read_bytes(), b"synthetic skill\n")
        self.assertEqual(len(list(p for p in self.target.rglob("*") if p.is_file())), len(self.members) + 1)

    def test_invalid_zip_paths_duplicates_and_links_fail_before_extraction(self):
        for name in ("../escape.py", "/absolute.py", "dir\\escape.py", "dir/../escape.py", "dir//escape.py",
                     "dir/CON.txt", "dir/file:stream", "dir/trailing. ", "Agent-Pack/Skill.md", "manifest.json"):
            with self.subTest(name=name):
                with mock.patch("warnings.warn"):
                    self.write_bundle(extras=[(name, b"bad")])
                with self.assertRaises(release.ReleaseError):
                    release.extract_bundle(self.bundle, COMMIT, self.target)
                self.assertFalse(self.target.exists())
        symlink = zipfile.ZipInfo("agent-pack/link.md")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.write_bundle(extras=[(symlink, b"../../secret")])
        with self.assertRaisesRegex(release.ReleaseError, "unsafe"):
            release.validate_bundle(self.bundle, COMMIT)

    def test_manifest_commit_dirty_type_and_digest_mismatches_are_rejected(self):
        for field, value in (("source_commit", "b" * 40), ("source_dirty", True), ("source_dirty", 0), ("schema_version", True)):
            with self.subTest(field=field, value=value):
                self.prepare_members()
                self.manifest[field] = value
                self.write_bundle()
                with self.assertRaises(release.ReleaseError):
                    release.validate_bundle(self.bundle, COMMIT)
        self.prepare_members()
        self.write_bundle(altered={"agent-pack/skill.md": b"changed after manifest"})
        with self.assertRaises(release.ReleaseError):
            release.validate_bundle(self.bundle, COMMIT)
        with self.assertRaises(release.ReleaseError):
            release.validate_bundle(self.bundle, COMMIT[:12])

    def test_extra_missing_oversize_and_compression_bomb_are_rejected(self):
        self.write_bundle(extras=[("extra.md", b"unexpected")])
        with self.assertRaises(release.ReleaseError):
            release.validate_bundle(self.bundle, COMMIT)
        self.write_bundle()
        with mock.patch.object(release, "MAX_EXPANDED_BYTES", 100):
            with self.assertRaisesRegex(release.ReleaseError, "limits"):
                release.validate_bundle(self.bundle, COMMIT)
        self.members["agent-pack/compressed.md"] = b"x" * 500000
        self.write_bundle(compression=zipfile.ZIP_DEFLATED)
        with self.assertRaisesRegex(release.ReleaseError, "limits"):
            release.validate_bundle(self.bundle, COMMIT)

    def test_wheel_record_and_nested_manifest_are_checked(self):
        self.prepare_members(corrupt_record=True)
        self.write_bundle()
        with self.assertRaisesRegex(release.ReleaseError, "RECORD"):
            release.validate_bundle(self.bundle, COMMIT)
        self.prepare_members()
        self.manifest["branding"] = {"version": "unsupported"}
        self.write_bundle()
        with self.assertRaisesRegex(release.ReleaseError, "disagree"):
            release.validate_bundle(self.bundle, COMMIT)

    def test_existing_extraction_directory_is_never_overwritten(self):
        self.target.mkdir()
        marker = self.target / "user-data.db"
        marker.write_bytes(b"do not change")
        with self.assertRaises(release.ReleaseError):
            release.extract_bundle(self.bundle, COMMIT, self.target)
        self.assertEqual(marker.read_bytes(), b"do not change")

    def test_prepare_uses_exact_offline_inventory_and_preserves_source(self):
        commands = []
        environment = {"PATH": "safe-path", "WEBUI_SECRET_KEY": "do-not-forward", "UV_SYSTEM_PYTHON": "true", "PYTHONPATH": "unsafe"}
        with mock.patch.object(release, "probe_python", side_effect=[self.baseline(), self.baseline(True)]), \
             mock.patch.object(release.subprocess, "run", side_effect=lambda command, **kwargs: commands.append((command, kwargs))):
            result = self.prepare(env=environment)
        self.assertEqual(result["state"], "prepared")
        self.assertTrue((self.target / "release.json").is_file())
        self.assertEqual((self.target / "dependencies.txt").read_text(), "example==1.0\n")
        self.assertEqual(self.source_python.read_bytes(), b"existing interpreter placeholder")
        self.assertEqual(len(commands), 3)
        for command, kwargs in commands:
            for flag in ("--offline", "--no-config", "--no-python-downloads"):
                self.assertIn(flag, command)
            self.assertEqual(kwargs["env"], {"PATH": "safe-path"})
            self.assertEqual(kwargs["cwd"], self.target)
        install = commands[1][0]
        self.assertIn("--no-deps", install)
        self.assertIn("--only-binary", install)
        self.assertIn(":all:", install)
        self.assertIn("--no-sources", install)
        self.assertIn(str(self.target / "venv" / "Scripts/python.exe"), install)
        self.assertNotIn(str(self.source_python), install)
        self.assertEqual(commands[2][0][4:6], ["pip", "check"])

    def test_missing_offline_dependency_leaves_candidate_inactive(self):
        def fail(*args, **kwargs):
            raise subprocess.CalledProcessError(1, args[0], stderr=b"private registry token")
        with mock.patch.object(release, "probe_python", return_value=self.baseline()), \
             mock.patch.object(release.subprocess, "run", side_effect=fail):
            with self.assertRaisesRegex(release.ReleaseError, "Offline preparation failed") as error:
                self.prepare()
        self.assertNotIn("private", str(error.exception))
        self.assertFalse((self.target / "release.json").exists())
        self.assertEqual(self.source_python.read_bytes(), b"existing interpreter placeholder")

    def test_inventory_drift_or_changed_requirements_never_marks_prepared(self):
        after = self.baseline(True)
        after["packages"]["example"] = "2.0"
        with mock.patch.object(release, "probe_python", side_effect=[self.baseline(), after]), \
             mock.patch.object(release.subprocess, "run"):
            with self.assertRaisesRegex(release.ReleaseError, "inventory"):
                self.prepare()
        self.assertFalse((self.target / "release.json").exists())
        other = self.root / "other"
        before = self.baseline()
        before["requires"] = ["example>=2"]
        with mock.patch.object(release, "probe_python", return_value=before), \
             mock.patch.object(release.subprocess, "run") as run:
            with self.assertRaisesRegex(release.ReleaseError, "declarations"):
                release.prepare_release(self.bundle, COMMIT, other, self.source_python, self.uv)
        run.assert_not_called()
        self.assertFalse(other.exists())

    def test_probe_rejects_direct_url_and_sanitizes_inspection_failures(self):
        payload = {"python_version": "3.11.9", "python_minor": [3, 11], "platform": "win32", "packages": [
            {"name": "open-webui", "version": "0.11.3", "direct": False, "requires": []},
            {"name": "private-package", "version": "1.0", "direct": True, "requires": []}]}
        with mock.patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(payload).encode())) as run:
            with self.assertRaisesRegex(release.ReleaseError, "direct-URL"):
                release.probe_python(self.source_python)
            self.assertEqual(run.call_args.args[0][1:4], ["-I", "-B", "-c"])
            self.assertNotIn("import open_webui", run.call_args.args[0][4])

    def test_prepared_fingerprint_and_inventory_are_revalidated(self):
        with mock.patch.object(release, "probe_python", side_effect=[self.baseline(), self.baseline(True)]), \
             mock.patch.object(release.subprocess, "run"):
            self.prepare()
        with mock.patch.object(release, "probe_python", side_effect=[self.baseline(), self.baseline(True)]):
            self.assertEqual(release.validate_prepared(self.target, COMMIT, self.source_python)["source_commit"], COMMIT)
        metadata = self.target / "release.json"
        data = json.loads(metadata.read_text())
        data["target_python"] = str(self.source_python)
        metadata.write_text(json.dumps(data))
        with self.assertRaisesRegex(release.ReleaseError, "metadata"):
            release.validate_prepared(self.target, COMMIT, self.source_python)

    @unittest.skipUnless(os.environ.get("EES_RUN_REAL_UV_TEST") == "1" and sys.version_info[:2] == (3, 11)
                         and shutil.which("uv"), "Opt-in real uv test requires Python 3.11 and installed uv.")
    def test_real_uv_prepares_tiny_wheels_offline_without_application_import(self):
        uv = Path(shutil.which("uv"))
        wheelhouse = self.root / "wheelhouse"
        wheelhouse.mkdir()
        (wheelhouse / "open_webui-0.11.3-py3-none-any.whl").write_bytes(wheel_bytes(version="0.11.3"))
        (wheelhouse / "example-1.0-py3-none-any.whl").write_bytes(wheel_bytes(distribution="example", version="1.0"))
        environment = dict(os.environ, UV_CACHE_DIR=str(self.root / "isolated-cache"))
        source_env = self.root / "source-env"
        source_python = source_env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        common = [str(uv), "--offline", "--no-config", "--no-python-downloads"]
        subprocess.run(common + ["venv", "--no-project", "--python", sys.executable, str(source_env)],
                       check=True, capture_output=True, env=release._environment(environment))
        subprocess.run(common + ["pip", "install", "--python", str(source_python), "--no-index", "--find-links", str(wheelhouse),
                                  "--only-binary", ":all:", "--no-deps", "open-webui==0.11.3", "example==1.0"],
                       check=True, capture_output=True, env=release._environment(environment))
        metadata = release.prepare_release(self.bundle, COMMIT, self.target, source_python, uv,
                                           wheelhouse=wheelhouse, env=environment)
        self.assertEqual(metadata["packages"]["after"], {"open-webui": release.branding.VERSION, "example": "1.0"})
        self.assertEqual(release.probe_python(source_python, env=environment)["packages"]["open-webui"], "0.11.3")
        self.assertEqual(release.validate_prepared(self.target, COMMIT, source_python, env=environment), metadata)


if __name__ == "__main__":
    unittest.main()
