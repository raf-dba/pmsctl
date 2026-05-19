import unittest

from pmsctl import validators


class ValidatorsTest(unittest.TestCase):
    def test_no_muestra_accion_recomendada_en_checks_ok(self):
        check = validators._check("TEST", True, "Correcto.", "No deberia aparecer.")

        self.assertEqual(check["status"], "OK")
        self.assertNotIn("recommended_action", check)

    def test_muestra_accion_recomendada_en_checks_error(self):
        check = validators._check("TEST", False, "Error.", "Corrija el problema.")

        self.assertEqual(check["status"], "ERROR")
        self.assertEqual(check["recommended_action"], "Corrija el problema.")


if __name__ == "__main__":
    unittest.main()
