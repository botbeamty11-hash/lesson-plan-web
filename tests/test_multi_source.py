"""Lesson-plan form: multiple source (file 2) uploads, saved and claimed."""
import os
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PDF_A = b"%PDF-1.4 file-a"
PDF_B = b"%PDF-1.4 file-b"
DOCX_T = b"PK\x03\x04 fake-template"


class MultiSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        data = Path(cls._tmpdir.name) / "data"
        data.mkdir()
        work = Path(cls._tmpdir.name) / "work"
        work.mkdir()
        cls.work = work
        cls._old_env = {
            k: os.environ.get(k)
            for k in (
                "SECRET_KEY", "LP_COOKIE_SECURE", "ADMIN_PASSWORD", "WORKER_TOKEN",
                "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "LP_TEST_LOGIN", "LP_DATA_DIR",
                "LP_BASE_URL", "LP_WORKER_TOKEN", "LP_WORK_DIR",
            )
        }
        token = "test-worker-token-16ch"
        os.environ.update({
            "SECRET_KEY": "test-secret-key-32chars-minimum!!",
            "LP_COOKIE_SECURE": "0",
            "ADMIN_PASSWORD": "",
            "WORKER_TOKEN": token,
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "LP_TEST_LOGIN": "1",
            "LP_DATA_DIR": str(data),
            "LP_BASE_URL": "http://localhost",
            "LP_WORKER_TOKEN": token,
            "LP_WORK_DIR": str(work),
        })
        for mod in ("app", "store", "users", "brand", "catalog", "remote_worker"):
            sys.modules.pop(mod, None)
        import app as app_mod
        import store, users, remote_worker
        store.DATA_DIR = str(data)
        store.JOBS_DIR = str(data / "jobs")
        store.SETTINGS_PATH = str(data / "settings.json")
        Path(store.JOBS_DIR).mkdir(parents=True, exist_ok=True)
        if hasattr(users, "USERS_DIR"):
            users.USERS_DIR = str(data / "users")
            Path(users.USERS_DIR).mkdir(parents=True, exist_ok=True)
        cls.app = app_mod.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.store = store
        cls.users = users
        cls.remote_worker = remote_worker
        cls.token = token
        remote_worker.BASE = "http://localhost"
        remote_worker.TOKEN = token
        remote_worker.WORK_DIR = str(work)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls._tmpdir.cleanup()

    def setUp(self):
        self.store.save_settings({"free_trial_mode": False, "points_topup_enabled": False})

    def _login(self, email="multi@example.com"):
        r = self.client.get(f"/auth/test-login?email={email}&name=Teacher")
        self.assertIn(r.status_code, (302, 200))

    def _auth(self):
        return {"Authorization": "Bearer " + self.token}

    def test_plan_form_source_is_multiple(self):
        r = self.client.get("/plan")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('id="source"', html)
        self.assertIn("multiple", html)
        self.assertIn("เลือกได้หลายไฟล์", html)
        # template stays single
        self.assertRegex(html, r'id="template"[^>]*accept="[^"]*"\s*>')
        self.assertNotRegex(html, r'id="template"[^>]*\bmultiple\b')

    def test_create_job_single_tuple_still_works(self):
        def save_a(dest):
            Path(dest).write_bytes(PDF_A)

        def save_t(dest):
            Path(dest).write_bytes(DOCX_T)

        job = self.store.create_job(
            {"template": ("form.docx", save_t), "source": ("one.pdf", save_a)},
            {"teacher": "ครูเอ"},
            "",
        )
        self.assertEqual(job["files"]["source"], "source.pdf")
        self.assertEqual(job["files"]["source_original_name"], "one.pdf")
        self.assertEqual(len(job["files"]["sources"]), 1)
        self.assertEqual(job["files"]["sources"][0]["original_name"], "one.pdf")
        d = self.store.job_dir(job["id"])
        self.assertTrue((Path(d) / "source.pdf").is_file())
        self.assertEqual((Path(d) / "source.pdf").read_bytes(), PDF_A)
        # legacy helper
        names = self.store.source_original_names(job)
        self.assertEqual(names, ["one.pdf"])

    def test_legacy_job_without_sources_key(self):
        job = {"files": {"source": "source.pdf", "source_original_name": "old.pdf"}}
        entries = self.store.source_file_entries(job)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["original_name"], "old.pdf")
        self.assertEqual(self.store.source_original_names({"files": {}}), [])

    def test_submit_two_sources_then_claim_download(self):
        self._login()
        data = {
            "instructions": "",
            "template": (BytesIO(DOCX_T), "form.docx"),
            "source": [
                (BytesIO(PDF_A), "plan-a.pdf"),
                (BytesIO(PDF_B), "plan-b.pdf"),
            ],
        }
        r = self.client.post("/submit", data=data, content_type="multipart/form-data")
        self.assertIn(r.status_code, (302, 303), r.get_data(as_text=True)[:500])
        loc = r.headers.get("Location") or ""
        import re
        m = re.search(r"/job/([^/]+)", loc)
        self.assertTrue(m, f"expected /job/<id> in Location, got {loc!r}")
        jid = m.group(1)
        job = self.store.load(jid)
        self.assertIsNotNone(job)
        self.assertEqual(job["files"]["source_original_name"], "plan-a.pdf")
        sources = job["files"]["sources"]
        self.assertEqual(len(sources), 2)
        self.assertEqual([s["original_name"] for s in sources], ["plan-a.pdf", "plan-b.pdf"])
        d = Path(self.store.job_dir(jid))
        self.assertEqual((d / sources[0]["stored"]).read_bytes(), PDF_A)
        self.assertEqual((d / sources[1]["stored"]).read_bytes(), PDF_B)
        self.assertEqual(sources[0]["stored"], "source.pdf")
        self.assertEqual(sources[1]["stored"], "source_1.pdf")

        # queue it so claim works (form leaves it awaiting_payment when points mode is off)
        if job["status"] in ("awaiting_payment", "awaiting_choice", "payment_rejected"):
            job = self.store.mark_job_points_paid(jid)
        self.assertEqual(job["status"], "queued")

        cr = self.client.post(f"/api/worker/{jid}/claim", headers=self._auth())
        self.assertEqual(cr.status_code, 200, cr.get_data(as_text=True)[:500])
        body = cr.get_json()
        wjob = body["job"]
        self.assertIn("source", wjob["urls"])
        self.assertIn("source_1", wjob["urls"])
        self.assertEqual(len(wjob["files"]["sources"]), 2)

        f0 = self.client.get(f"/api/worker/{jid}/file/source", headers=self._auth())
        f1 = self.client.get(f"/api/worker/{jid}/file/source_1", headers=self._auth())
        self.assertEqual(f0.status_code, 200)
        self.assertEqual(f1.status_code, 200)
        self.assertEqual(f0.data, PDF_A)
        self.assertEqual(f1.data, PDF_B)

        # remote_worker.download_inputs should place both files in the job folder
        # Patch request() to serve via the Flask test client (no real HTTP server).
        rw = self.remote_worker
        client = self.client
        auth = self._auth()

        def fake_request(method, path_or_url, data=None, headers=None, raw=False, retries=3, soft404=False):
            path = path_or_url
            if path.startswith("http://localhost"):
                path = path[len("http://localhost"):]
            elif path.startswith("http://localhost/"):
                path = path[len("http://localhost"):]
            resp = client.open(path, method=method, data=data, headers={**auth, **(headers or {})})
            if resp.status_code == 404 and soft404:
                return None
            if resp.status_code >= 400:
                raise AssertionError(f"fake_request {method} {path} -> {resp.status_code} {resp.get_data()[:200]}")
            if raw:
                return resp.data
            return resp.get_json()

        orig = rw.request
        rw.request = fake_request
        try:
            dest, local = rw.download_inputs(wjob)
        finally:
            rw.request = orig
        self.assertTrue(Path(local["source"]).is_file())
        self.assertEqual(Path(local["source"]).read_bytes(), PDF_A)
        self.assertEqual(len(local["sources"]), 2)
        self.assertEqual(Path(local["sources"][0]["path"]).read_bytes(), PDF_A)
        self.assertEqual(Path(local["sources"][1]["path"]).read_bytes(), PDF_B)
        self.assertEqual(local["sources"][1]["original_name"], "plan-b.pdf")
        # both files landed in the claim job folder
        self.assertTrue((Path(dest) / "source.pdf").is_file())
        self.assertTrue((Path(dest) / "source_1.pdf").is_file())

    def test_submit_rejects_too_many_source_files(self):
        self._login("many@example.com")
        files = [(BytesIO(b"%PDF-1.4 x" + str(i).encode()), f"p{i}.pdf") for i in range(11)]
        data = {
            "instructions": "",
            "template": (BytesIO(DOCX_T), "form.docx"),
            "source": files,
        }
        r = self.client.post("/submit", data=data, content_type="multipart/form-data", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("เลือกได้สูงสุด 10 ไฟล์", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
