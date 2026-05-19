import unittest

from pmsctl import output


class OutputTest(unittest.TestCase):
    def test_formato_humano_diccionario_anidado(self):
        text = output.format_human({"result": "OK", "primary": {"reachable": "YES"}})
        self.assertIn("RESULT: OK", text)
        self.assertIn("PRIMARY:", text)
        self.assertIn("REACHABLE: YES", text)

    def test_formato_humano_roles_con_etiquetas_claras(self):
        text = output.format_human(
            {"role": "STANDBY", "database_role": "PRIMARY"}
        )

        self.assertIn("PMS ROLE: STANDBY", text)
        self.assertIn("ORACLE DATABASE ROLE: PRIMARY", text)


if __name__ == "__main__":
    unittest.main()
