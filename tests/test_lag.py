import unittest
from unittest import mock

from pmsctl import commands


class LagHelpersTest(unittest.TestCase):
    def test_convierte_secuencia_a_entero(self):
        self.assertEqual(commands._to_int("10"), 10)
        self.assertIsNone(commands._to_int("UNKNOWN"))

    def test_calcula_lag_temporal_y_no_devuelve_valores_negativos(self):
        self.assertEqual(
            commands._lag_minutes("2026-05-10 10:42:18", "2026-05-10 10:30:02"),
            12,
        )
        self.assertEqual(
            commands._lag_minutes("2026-05-10 10:30:02", "2026-05-10 10:42:18"),
            0,
        )
        self.assertIsNone(commands._lag_minutes("UNKNOWN", "2026-05-10 10:42:18"))

    @mock.patch("pmsctl.commands.audit.log_event")
    @mock.patch("pmsctl.commands.audit.utc_now", return_value="2026-05-10T10:42:30Z")
    @mock.patch("pmsctl.commands.oracle.redo_summary")
    @mock.patch("pmsctl.commands.storage.load_config")
    def test_lag_diferencia_transferencia_aplicacion_y_alerta(
        self,
        load_config,
        redo_summary,
        utc_now,
        log_event,
    ):
        load_config.return_value = {
            "primary": {"host": "primary"},
            "standby": {"host": "replica"},
            "settings": {
                "ssh_timeout": 20,
                "max_transfer_lag_minutes": 10,
                "max_apply_lag_minutes": 10,
            },
        }
        redo_summary.side_effect = [
            {
                "reachable": "YES",
                "last_redo_sequence": "14582",
                "last_redo_time": "2026-05-10 10:42:18",
            },
            {
                "reachable": "YES",
                "last_redo_sequence": "14580",
                "last_redo_time": "2026-05-10 10:36:41",
            },
            {
                "reachable": "YES",
                "last_redo_sequence": "14579",
                "last_redo_time": "2026-05-10 10:30:02",
            },
        ]

        result = commands.lag("prod_to_dr")

        self.assertEqual(result["transfer"]["transfer_lag"], "5 minutes")
        self.assertEqual(result["apply"]["apply_lag"], "12 minutes")
        self.assertEqual(result["result"], "WARNING")
        self.assertEqual(result["message"], "Apply lag exceeds configured threshold.")
        self.assertEqual(result["calculated_at"], "2026-05-10T10:42:30Z")
        redo_summary.assert_has_calls(
            [
                mock.call({"host": "primary"}, timeout=20),
                mock.call({"host": "replica"}, timeout=20),
                mock.call({"host": "replica"}, applied_through_datafiles=True, timeout=20),
            ]
        )

    @mock.patch("pmsctl.commands.audit.log_event")
    @mock.patch("pmsctl.commands.oracle.redo_summary")
    @mock.patch("pmsctl.commands.storage.load_config")
    def test_lag_informa_error_si_primaria_no_esta_disponible(
        self,
        load_config,
        redo_summary,
        log_event,
    ):
        load_config.return_value = {
            "primary": {"host": "primary"},
            "standby": {"host": "replica"},
            "settings": {},
        }
        redo_summary.side_effect = [
            {"reachable": "NO", "last_redo_sequence": "UNKNOWN", "last_redo_time": "UNKNOWN"},
            {"reachable": "YES", "last_redo_sequence": "10", "last_redo_time": "2026-05-10 10:10:00"},
            {"reachable": "YES", "last_redo_sequence": "9", "last_redo_time": "2026-05-10 10:00:00"},
        ]

        result = commands.lag("prod_to_dr")

        self.assertEqual(result["result"], "ERROR")
        self.assertEqual(result["transfer"]["transfer_lag"], "UNKNOWN")
        self.assertIn("primary database is not accessible", result["message"])
        self.assertIn("recommended_action", result)


if __name__ == "__main__":
    unittest.main()
