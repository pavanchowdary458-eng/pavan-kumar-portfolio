"""Run with:  python -m unittest discover -s tests -v   (pytest also works)"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402

GOOD = {"name": "A", "email": "a@b.co", "message": "Hello there friend"}


def make_app(tmp, password="pw"):
    return create_app({"TESTING": True, "DATABASE": os.path.join(tmp, "t.db"),
                       "ADMIN_PASSWORD": password, "SECRET_KEY": "x"})


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = make_app(self._tmp.name)
        self.client = self.app.test_client()

    def csrf(self, path="/admin/login"):
        self.client.get(path)
        with self.client.session_transaction() as s:
            s.setdefault("csrf", "tok")
            return s["csrf"]

    def login(self):
        return self.client.post("/admin/login", data={"password": "pw", "csrf_token": self.csrf()})


class PublicTests(Base):
    def test_home_renders_seeded_content(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Heart Disease Tracking System", html)
        self.assertIn("GPA: 70.63", html)

    def test_api_lists(self):
        self.assertEqual(len(self.client.get("/api/projects").json), 3)
        self.assertEqual(len(self.client.get("/api/skills").json), 6)
        self.assertEqual(len(self.client.get("/api/education").json), 3)
        self.assertEqual(self.client.get("/api/projects/999").status_code, 404)
        self.assertEqual(self.client.get("/api/projects/1").json["tech"], ["Python", "SQL", "PostgreSQL"])

    def test_contact_api_valid_and_invalid(self):
        self.assertEqual(self.client.post("/api/contact", json=GOOD).status_code, 201)
        bad = self.client.post("/api/contact", json={"name": "", "email": "nope", "message": "hi"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(bad.json["errors"]), {"name", "email", "message"})
        self.assertEqual(self.client.post("/api/contact", data="x").status_code, 400)

    def test_contact_form_flash_and_honeypot(self):
        r = self.client.post("/contact", data=GOOD, follow_redirects=True)
        self.assertIn("received", r.get_data(as_text=True))
        self.client.post("/contact", data={"website": "spam", "name": "S", "email": "s@s.co",
                                           "message": "buy buy buy buy"})
        self.login()
        page = self.client.get("/admin").get_data(as_text=True)
        self.assertIn("Hello there friend", page)
        self.assertNotIn("buy buy", page)

    def test_contact_rate_limit(self):
        codes = [self.client.post("/api/contact", json=GOOD).status_code for _ in range(7)]
        self.assertEqual(codes, [201] * 5 + [429, 429])

    def test_xss_is_escaped(self):
        self.client.post("/api/contact", json={**GOOD, "name": "<script>x</script>"})
        self.login()
        self.assertNotIn("<script>x</script>", self.client.get("/admin").get_data(as_text=True))

    def test_404_pages(self):
        self.assertEqual(self.client.get("/nope").status_code, 404)
        self.assertEqual(self.client.get("/api/nope").json, {"error": "Not found"})

    def test_health(self):
        self.assertEqual(self.client.get("/healthz").json, {"status": "ok"})


class AdminTests(Base):
    def test_requires_login_and_csrf(self):
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertEqual(self.client.post("/admin/login", data={"password": "pw"}).status_code, 400)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_wrong_password(self):
        r = self.client.post("/admin/login", data={"password": "bad", "csrf_token": self.csrf()})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Incorrect", r.get_data(as_text=True))

    def test_disabled_without_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = make_app(tmp, password="").test_client()
            self.assertEqual(c.get("/admin").status_code, 404)

    def test_message_actions(self):
        self.client.post("/api/contact", json=GOOD)
        self.login()
        tok = self.csrf("/admin")
        self.client.post("/admin/messages/1/read", data={"csrf_token": tok})
        self.assertIn("0 unread", self.client.get("/admin").get_data(as_text=True))
        self.client.post("/admin/messages/1/delete", data={"csrf_token": tok})
        self.assertIn("No messages yet", self.client.get("/admin").get_data(as_text=True))

    def test_project_crud(self):
        self.login()
        tok = self.csrf("/admin")
        r = self.client.post("/admin/projects/new", data={
            "csrf_token": tok, "title": "New One", "tech": "a, b", "visible": "on",
            "github_url": "https://github.com/x/y"})
        self.assertEqual(r.status_code, 302)
        new = next(p for p in self.client.get("/api/projects").json if p["title"] == "New One")
        self.assertEqual(new["tech"], ["a", "b"])
        # unchecking "visible" hides it from the public API
        self.client.post(f"/admin/projects/{new['id']}/edit", data={"csrf_token": tok, "title": "Renamed"})
        self.assertTrue(all(p["title"] != "Renamed" for p in self.client.get("/api/projects").json))
        bad = self.client.post("/admin/projects/new", data={
            "csrf_token": tok, "title": "X", "live_url": "javascript:alert(1)"})
        self.assertEqual(bad.status_code, 200)
        self.assertIn("must start with http", bad.get_data(as_text=True))
        self.client.post(f"/admin/projects/{new['id']}/delete", data={"csrf_token": tok})
        self.assertEqual(len(self.client.get("/api/projects").json), 3)

    def test_deleted_content_is_not_reseeded(self):
        self.login()
        tok = self.csrf("/admin")
        for i in (1, 2, 3):
            self.client.post(f"/admin/projects/{i}/delete", data={"csrf_token": tok})
        again = make_app(self._tmp.name).test_client()
        self.assertEqual(again.get("/api/projects").json, [])


if __name__ == "__main__":
    unittest.main()
