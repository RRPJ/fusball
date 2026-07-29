from __future__ import annotations

import unittest

from app.services.auth import AuthActor, ClerkRequestAuthenticator


class AuthActorTests(unittest.TestCase):
    def test_role_permission_hierarchy(self) -> None:
        reader = AuthActor("user_reader", "Reader", "reader")
        operator = AuthActor("user_operator", "Operator", "operator")
        admin = AuthActor("user_admin", "Admin", "admin")

        self.assertTrue(reader.can("read"))
        self.assertFalse(reader.can("write"))
        self.assertFalse(reader.can("admin"))

        self.assertTrue(operator.can("read"))
        self.assertTrue(operator.can("write"))
        self.assertFalse(operator.can("admin"))

        self.assertTrue(admin.can("read"))
        self.assertTrue(admin.can("write"))
        self.assertTrue(admin.can("admin"))

    def test_clerk_authenticator_requires_authorized_parties(self) -> None:
        class StubRoleStore:
            def resolve_actor(self, subject: str):
                return None

        with self.assertRaisesRegex(ValueError, "authorized party"):
            ClerkRequestAuthenticator("sk_test_example", [], StubRoleStore())


if __name__ == "__main__":
    unittest.main()
