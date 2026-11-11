"""Free-trial mode + points costs: defaults, gating, charge flow, promo packages."""
import os
import tempfile
import unittest
from pathlib import Path
from io import BytesIO


def _docx_bytes():
    # Minimal valid-enough zip is not needed — plan create accepts empty with instructions.
    return b"%PDF-1.4 fake"


class FreeTrialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        data = Path(cls._tmpdir.name) / "data"
        data.mkdir()
        cls._old_env = {
            k: os.environ.get(k)
            for k in (
                "SECRET_KEY", "LP_COOKIE_SECURE", "ADMIN_PASSWORD", "WORKER_TOKEN",
                "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "LP_TEST_LOGIN", "LP_DATA_DIR",
            )
        }
        os.environ.update({
            "SECRET_KEY": "test-secret-key-32chars-minimum!!",
            "LP_COOKIE_SECURE": "0",
            "ADMIN_PASSWORD": "",
            "WORKER_TOKEN": "",
            "GOOGLE_CLIENT_ID": "",
            "GOOGLE_CLIENT_SECRET": "",
            "LP_TEST_LOGIN": "1",
            "LP_DATA_DIR": str(data),
        })
        import importlib, sys
        for mod in ("app", "store", "users", "brand", "catalog"):
            sys.modules.pop(mod, None)
        import app as app_mod
        import store, users, catalog
        store.DATA_DIR = str(data)
        store.JOBS_DIR = str(data / "jobs")
        store.SETTINGS_PATH = str(data / "settings.json")
        store.USERS_DIR = str(data / "users") if hasattr(store, "USERS_DIR") else store.JOBS_DIR
        # users module path
        if hasattr(users, "USERS_DIR"):
            users.USERS_DIR = str(data / "users")
            Path(users.USERS_DIR).mkdir(parents=True, exist_ok=True)
        Path(store.JOBS_DIR).mkdir(parents=True, exist_ok=True)
        cls.app = app_mod.app
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.store = store
        cls.users = users
        cls.catalog = catalog

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls._tmpdir.cleanup()

    def setUp(self):
        # reset settings each test
        self.store.save_settings({
            "free_trial_mode": False,
            "points_topup_enabled": False,
            "points_packages": list(self.store.DEFAULT_POINTS_PACKAGES),
        })

    def _login(self, email="t1@example.com"):
        r = self.client.get(f"/auth/test-login?email={email}&name=Teacher")
        self.assertIn(r.status_code, (302, 200))
        return self.users.upsert_google_user(sub="test_" + email, email=email, name="Teacher", picture="")

    def test_catalog_defaults_nonzero(self):
        for s in self.catalog.DEFAULT_SERVICES:
            self.assertGreater(int(s["points_cost"]), 0, s["id"])
        # cheap PDF tools
        for sid in ("pdf_merge", "pdf_split", "pdf_compress"):
            self.assertLessEqual(self.catalog.get_service(sid)["points_cost"], 2)
        # big docs
        self.assertGreaterEqual(self.catalog.get_service("research")["points_cost"], 15)
        self.assertLessEqual(self.catalog.get_service("research")["points_cost"], 30)

    def test_lesson_plan_scaling(self):
        fn = self.catalog.lesson_plan_points_cost
        svc = {"points_cost": 8}
        self.assertEqual(fn(svc, 1, [], []), 5)
        self.assertEqual(fn(svc, 1, ["แก้คำผิดและเนื้อหาที่ผิด"], []), 8)
        self.assertEqual(fn(svc, 1, ["ทำภาพประกอบเพิ่ม"], []), 12)
        self.assertEqual(fn(svc, 2, [], []), 10)  # 5×2
        self.assertEqual(fn(svc, 2, [], ["addon_slides"]), 8 * 2 + 10)

    def test_points_price_label_range_vs_single(self):
        lp = self.catalog.get_service("lesson_plan")
        self.assertEqual(self.catalog.points_range(lp), (5, 12))
        self.assertEqual(self.catalog.points_price_label(lp), "ราคาเริ่มต้น 5 ถึง 12 พ้อยท์ ต่อแผน")
        pdf = self.catalog.get_service("pdf_merge")
        self.assertIsNone(self.catalog.points_range(pdf))
        self.assertEqual(self.catalog.points_price_label(pdf), "1 พ้อยท์")
        # optional explicit range on a generic service
        other = {"id": "custom", "points_cost": 9, "points_min": 3, "points_max": 15}
        self.assertEqual(self.catalog.points_price_label(other), "ราคาเริ่มต้น 3 ถึง 15 พ้อยท์")

    def test_mode_off_home_shows_free_not_points(self):
        r = self.client.get("/")
        body = r.get_data(as_text=True)
        self.assertIn("ทดลองใช้ฟรี", body)
        self.assertNotIn("พ้อยท์ / แผน", body)
        # service list should not show pts badge
        r2 = self.client.get("/services")
        body2 = r2.get_data(as_text=True)
        self.assertNotIn("พ้อยท์", body2)  # no cost badges when OFF

    def test_mode_on_shows_points_hides_free_pill(self):
        self.store.save_settings({"free_trial_mode": True, "points_topup_enabled": True})
        r = self.client.get("/")
        body = r.get_data(as_text=True)
        self.assertNotIn("free-pill", body)
        r2 = self.client.get("/services")
        body2 = r2.get_data(as_text=True)
        self.assertIn("พ้อยท์", body2)
        self.assertIn("ราคาเริ่มต้น 5 ถึง 12 พ้อยท์ ต่อแผน", body2)  # lesson_plan range, not mid price
        self.assertNotIn("8 พ้อยท์ / แผน", body2)
        self.assertIn("1 พ้อยท์", body2)  # pdf merge etc. (single price)
        r3 = self.client.get("/group/แผนการสอน")
        self.assertEqual(r3.status_code, 200)
        self.assertIn("ราคาเริ่มต้น 5 ถึง 12 พ้อยท์ ต่อแผน", r3.get_data(as_text=True))
        r4 = self.client.get("/plan")
        body4 = r4.get_data(as_text=True)
        self.assertIn("ราคาเริ่มต้น 5 ถึง 12 พ้อยท์ ต่อแผน", body4)
        self.assertNotIn(">8 พ้อยท์ / แผน", body4)

    def test_charge_mode_off_never_deducts(self):
        u = self._login("off@example.com")
        before = int(u.get("points") or 0)
        ch = self.users.charge_for_service(u["id"], 99, reason="x", free_trial_mode=False)
        self.assertTrue(ch["ok"])
        self.assertEqual(ch["points_spent"], 0)
        u2 = self.users.load_user(u["id"])
        self.assertEqual(int(u2.get("points") or 0), before)

    def test_free_use_then_points(self):
        u = self._login("free@example.com")
        self.assertEqual(self.users.free_uses_left(u), 1)
        ch1 = self.users.charge_for_service(u["id"], 8, reason="svc1", free_trial_mode=True)
        self.assertTrue(ch1["ok"])
        self.assertTrue(ch1["used_free"])
        self.assertTrue(ch1["show_promo"])
        self.assertEqual(ch1["points_spent"], 0)
        u = self.users.load_user(u["id"])
        self.assertEqual(self.users.free_uses_left(u), 0)
        # no points → blocked + promo
        ch2 = self.users.charge_for_service(u["id"], 8, reason="svc2", free_trial_mode=True)
        self.assertFalse(ch2["ok"])
        self.assertTrue(ch2["show_promo"])
        # top up points and succeed
        self.users.adjust_points(u["id"], 20, reason="test topup", typ="admin")
        ch3 = self.users.charge_for_service(u["id"], 8, reason="svc3", free_trial_mode=True)
        self.assertTrue(ch3["ok"])
        self.assertEqual(ch3["points_spent"], 8)
        u = self.users.load_user(u["id"])
        self.assertEqual(int(u.get("points") or 0), 12)

    def test_default_packages_100_and_220(self):
        pkgs = self.store.DEFAULT_POINTS_PACKAGES
        by_id = {p["id"]: p for p in pkgs}
        self.assertEqual(by_id["p100"]["baht"], 100)
        self.assertEqual(by_id["p100"]["points"], 100)
        self.assertEqual(by_id["p200"]["baht"], 200)
        self.assertEqual(by_id["p200"]["points"], 220)

    def test_topup_preparing_message(self):
        self.store.save_settings({
            "free_trial_mode": True,
            "points_topup_enabled": True,
            "promptpay_id": "",
            "qr_image": None,
        })
        self._login("pay@example.com")
        r = self.client.get("/points/topup")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("ระบบชำระเงินกำลังเตรียม", body)
        self.assertIn("100", body)
        self.assertIn("220", body)

    def test_service_form_points_gated(self):
        # OFF
        r = self.client.get("/services/pdf_merge")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("พ้อยท์", r.get_data(as_text=True))
        # ON
        self.store.save_settings({"free_trial_mode": True})
        r = self.client.get("/services/pdf_merge")
        self.assertIn("1 พ้อยท์", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
