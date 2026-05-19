import unittest

from pmsctl import commands


class LagHelpersTest(unittest.TestCase):
    def test_convierte_secuencia_a_entero(self):
        self.assertEqual(commands._to_int("10"), 10)
        self.assertIsNone(commands._to_int("UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
