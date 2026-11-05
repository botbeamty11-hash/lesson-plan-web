"""Public legal pages, sitemap, and footer links."""
import os
import tempfile
import unittest
from pathlib import Path


class LegalPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        data = Path(cls._tmpdir.name) / "data"
        data.mkdir()
        cls._old_env = {
            k: os.environ.get(k)
            for k in (
                "SECRET_KEY",
                "LP_COOKIE_SECURE",
                "ADMIN_PASSWORD",
                "WORKER_TOKEN",
                "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET",
                "LP_TEST_LOGIN",
                "LP_DATA_DIR",
            )
        }
        os.environ.update({
            "SECRET_KEY": "test-secret-key-32chars-minimum!!",
            "LP_COOKIE_SECURE": "0",
            "ADMIN_PASSWORD": "",
            "WORKER_TOKEN": "",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "LP_TEST_LOGIN": "0",
            "LP_DATA_DIR": str(data),
        })
        # Ensure a clean import with the test env (app loads dotenv then reads env)
        import importlib
        import sys
        for mod in ("app", "store", "users", "brand", "catalog"):
            sys.modules.pop(mod, None)
        import app as app_mod
        # Re-bind store paths in case module was partially cached
        import store
        store.DATA_DIR = str(data)
        store.JOBS_DIR = str(data / "jobs")
        store.SETTINGS_PATH = str(data / "settings.json")
        cls.app = app_mod.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls._tmpdir.cleanup()

    def test_privacy_ok(self):
        r = self.client.get("/privacy")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("นโยบายความเป็นส่วนตัว", body)
        self.assertIn("ไม่ขาย", body)
        self.assertIn("Google", body)
        self.assertIn("ชื่อ", body)
        self.assertIn("อีเมล", body)

    def test_terms_ok(self):
        r = self.client.get("/terms")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("ข้อกำหนดการใช้บริการ", body)

    def test_footer_links_on_home(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn('href="/privacy"', body)
        self.assertIn('href="/terms"', body)

    def test_sitemap_lists_legal(self):
        r = self.client.get("/sitemap.xml")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("/privacy", body)
        self.assertIn("/terms", body)

    def test_robots_ok(self):
        r = self.client.get("/robots.txt")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Sitemap:", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
