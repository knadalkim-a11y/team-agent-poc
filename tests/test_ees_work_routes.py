"""Real FastAPI routing with a synthetic verified-user dependency, no user DB.

This checks dependency enforcement and fixed file delivery, not real sign-in.
The build test separately checks the host passes its get_verified_user helper.
"""

import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient
except ImportError:
    FastAPI = None

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agent-pack/skills/ees-work-demo"


class EESWorkRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if FastAPI is None:
            if os.environ.get("EES_REQUIRE_WORK_ROUTES"):
                raise RuntimeError("Pinned FastAPI/httpx test dependencies are required.")
            raise unittest.SkipTest("FastAPI test dependencies unavailable; CI requires this gate.")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        module = self.root / "ees_work_demo.py"
        shutil.copyfile(SOURCE / "scripts/ees_work_demo.py", module)
        shutil.copytree(SOURCE / "ui", self.root / "ees_work_demo_ui")
        spec = importlib.util.spec_from_file_location("ees_work_route_fixture", module)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.calls = 0

        async def verified(request: Request):
            self.calls += 1
            if request.headers.get("x-fixture-user") != "verified":
                raise HTTPException(status_code=401, detail="Synthetic unauthenticated user")
            return object()

        self.app = FastAPI()
        self.module.install(self.app, verified)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"x-fixture-user": "verified"}
        for route in self.app.routes:
            if route.path.startswith("/ees-work-demo/"):
                self.assertIs(route.dependant.dependencies[0].call, verified)

    def test_all_documents_and_assets_require_existing_user_dependency(self):
        for path in ("", "index.html", "ees-work.css", "ees-work.js"):
            url = "/ees-work-demo/" + path
            self.assertEqual(self.client.get(url).status_code, 401)
            response = self.client.get(url, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, (SOURCE / "ui" / (path or "index.html")).read_bytes())
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertIn("connect-src 'none'", response.headers["content-security-policy"])
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(self.calls, 8)

    def test_no_path_traversal_public_static_copy_or_write_route(self):
        for path in ("unknown", "..%2Fees_work_demo.py", "nested/ees-work.js"):
            self.assertEqual(self.client.get("/ees-work-demo/" + path, headers=self.headers).status_code, 404)
        for path in ("/ees_work_demo_ui/index.html", "/_ees5/ees-work-demo/index.html"):
            self.assertEqual(self.client.get(path, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post("/ees-work-demo/", headers=self.headers, json={"publish": True}).status_code, 405)

    def test_missing_asset_fails_without_spa_fallback(self):
        (self.root / "ees_work_demo_ui/ees-work.js").unlink()
        self.assertEqual(self.client.get("/ees-work-demo/ees-work.js", headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
