import unittest
from unittest import mock

from pmsctl import commands, validators


class ValidatorsTest(unittest.TestCase):
    def test_no_muestra_accion_recomendada_en_checks_ok(self):
        check = validators._check("TEST", True, "Correcto.", "No deberia aparecer.")

        self.assertEqual(check["status"], "OK")
        self.assertNotIn("recommended_action", check)

    def test_muestra_accion_recomendada_en_checks_error(self):
        check = validators._check("TEST", False, "Error.", "Corrija el problema.")

        self.assertEqual(check["status"], "ERROR")
        self.assertEqual(check["recommended_action"], "Corrija el problema.")

    @mock.patch("pmsctl.commands.audit.log_event")
    @mock.patch("pmsctl.validators.validate_environment")
    @mock.patch("pmsctl.commands.storage.load_config")
    def test_validate_incluye_mensaje_resumen(self, load_config, validate_environment, log_event):
        load_config.return_value = {"name": "prod_to_dr"}
        validate_environment.return_value = {"result": "OK", "checks": []}

        result = commands.validate("prod_to_dr")

        self.assertEqual(result["configuration"], "prod_to_dr")
        self.assertEqual(result["action"], "VALIDATE")
        self.assertIn("message", result)


if __name__ == "__main__":
    unittest.main()
