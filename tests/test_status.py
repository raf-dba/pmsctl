import unittest
from unittest import mock

from pmsctl import cli, commands, oracle, remote


class StatusTest(unittest.TestCase):
    @mock.patch("pmsctl.oracle.run_sqlplus")
    def test_database_status_basico_no_consulta_datafiles(self, run_sqlplus):
        run_sqlplus.return_value = remote.CommandResult(
            0,
            "CURRENT_SCN=0",
            "",
            "sqlplus -s / as sysdba",
        )

        oracle.database_status({"host": "local"})

        sql = run_sqlplus.call_args.args[1]
        self.assertNotIn("v$datafile_header", sql)

    @mock.patch("pmsctl.oracle.run_sqlplus")
    def test_database_status_incluye_identidad_y_estado_de_recuperacion(self, run_sqlplus):
        run_sqlplus.return_value = remote.CommandResult(
            0,
            "\n".join(
                [
                    "DB_UNIQUE_NAME=PROD",
                    "RECOVERY_STATUS=IDLE",
                ]
            ),
            "",
            "sqlplus -s / as sysdba",
        )

        status = oracle.database_status({"host": "local"})

        self.assertEqual(status["db_unique_name"], "PROD")
        self.assertEqual(status["recovery_status"], "IDLE")
        sql = run_sqlplus.call_args.args[1]
        self.assertIn("db_unique_name", sql)
        self.assertIn("v$session", sql)
        self.assertNotIn("v$datafile_header", sql)

    @mock.patch("pmsctl.oracle.run_sqlplus")
    def test_redo_summary_primaria_consulta_ultimo_archived_redo(self, run_sqlplus):
        run_sqlplus.return_value = remote.CommandResult(
            0,
            "\n".join(
                [
                    "LAST_REDO_THREAD=1",
                    "LAST_REDO_SEQUENCE=20",
                    "LAST_REDO_NEXT_CHANGE=200",
                ]
            ),
            "",
            "sqlplus -s / as sysdba",
        )

        summary = oracle.redo_summary({"host": "local"})

        self.assertEqual(summary["last_redo_sequence"], "20")
        sql = run_sqlplus.call_args.args[1]
        self.assertIn("archived = 'YES'", sql)
        self.assertNotIn("next_change# <= (", sql)

    @mock.patch("pmsctl.oracle.run_sqlplus")
    def test_redo_summary_standby_limita_redo_al_checkpoint_minimo(self, run_sqlplus):
        run_sqlplus.return_value = remote.CommandResult(
            0,
            "\n".join(
                [
                    "LAST_REDO_THREAD=1",
                    "LAST_REDO_SEQUENCE=18",
                    "LAST_REDO_NEXT_CHANGE=180",
                    "LAST_REDO_TIME=2026-05-10 10:30:02",
                ]
            ),
            "",
            "sqlplus -s / as sysdba",
        )

        summary = oracle.redo_summary(
            {"host": "standby.example"},
            applied_through_datafiles=True,
        )

        self.assertEqual(summary["last_redo_sequence"], "18")
        self.assertEqual(summary["last_redo_time"], "2026-05-10 10:30:02")
        sql = run_sqlplus.call_args.args[1]
        self.assertIn("next_change# <= (", sql)
        self.assertIn("min(checkpoint_change#)", sql)
        self.assertIn("max(completion_time) keep", sql)

    @mock.patch("pmsctl.commands.oracle.database_status")
    @mock.patch("pmsctl.commands.oracle.redo_summary")
    def test_status_diferencia_redo_transferido_y_aplicado(self, redo_summary, database_status):
        database_status.return_value = {
            "reachable": "YES",
            "db_unique_name": "PROD_DR",
            "database_role": "PHYSICAL STANDBY",
            "open_mode": "MOUNTED",
            "recovery_status": "IDLE",
        }
        redo_summary.side_effect = [
            {
                "reachable": "YES",
                "last_redo_sequence": "10",
                "last_redo_time": "2026-05-10 10:36:41",
            },
            {
                "reachable": "YES",
                "last_redo_sequence": "9",
                "last_redo_time": "2026-05-10 10:30:02",
            },
        ]

        status = commands._status_from_node(
            "REPLICA",
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
        )

        self.assertEqual(status["last_transferred_redo"], "10")
        self.assertEqual(status["last_applied_redo"], "9")
        redo_summary.assert_has_calls(
            [
                mock.call(
                    {"host": "standby.example", "oracle_sid": "TEST"},
                    timeout=20,
                ),
                mock.call(
                    {"host": "standby.example", "oracle_sid": "TEST"},
                    applied_through_datafiles=True,
                    timeout=20,
                ),
            ]
        )

    @mock.patch("pmsctl.commands.oracle.database_status")
    @mock.patch("pmsctl.commands.oracle.redo_summary")
    def test_status_no_repite_consultas_si_nodo_no_esta_disponible(self, redo_summary, database_status):
        database_status.return_value = {
            "reachable": "NO",
            "error": "SSH connection failed",
        }

        status = commands._status_from_node(
            "REPLICA",
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
        )

        self.assertEqual(status["status"], "UNKNOWN")
        self.assertEqual(status["error"], "SSH connection failed")
        database_status.assert_called_once_with(
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
        )
        redo_summary.assert_not_called()

    def test_ultimo_estado_valido_se_muestra_si_falla_consulta_actual(self):
        current = {"status": "UNKNOWN"}
        previous = {"open_mode": "MOUNTED", "last_applied_redo": "9"}

        commands._add_last_known_data(current, previous, "2026-05-10T10:30:02Z")

        self.assertEqual(current["last_known_status"], "MOUNTED")
        self.assertEqual(current["last_known_applied_redo"], "9")
        self.assertEqual(current["last_successful_check"], "2026-05-10T10:30:02Z")

    @mock.patch("pmsctl.commands.audit.log_event")
    @mock.patch("pmsctl.commands.audit.utc_now", return_value="2026-05-10T10:42:30Z")
    @mock.patch("pmsctl.commands.storage.save_state")
    @mock.patch("pmsctl.commands.storage.load_state")
    @mock.patch("pmsctl.commands.storage.load_config")
    @mock.patch("pmsctl.commands._status_from_node")
    def test_status_reutiliza_estado_valido_de_version_anterior(
        self,
        status_from_node,
        load_config,
        load_state,
        save_state,
        utc_now,
        log_event,
    ):
        load_config.return_value = {
            "primary": {"host": "primary"},
            "standby": {"host": "replica"},
            "settings": {},
        }
        load_state.return_value = {
            "last_status": {
                "primary": {"reachable": "YES", "open_mode": "READ WRITE"},
                "standby": {
                    "reachable": "YES",
                    "open_mode": "MOUNTED",
                    "last_applied_redo_sequence": "9",
                },
            }
        }
        status_from_node.side_effect = [
            {"status": "ONLINE"},
            {"status": "UNKNOWN", "error": "SSH connection failed"},
        ]

        result = commands.status("prod_to_dr")

        self.assertEqual(result["replica"]["last_known_status"], "MOUNTED")
        self.assertEqual(result["replica"]["last_known_applied_redo"], "9")
        self.assertEqual(result["result"], "ERROR")
        save_state.assert_called_once()

    def test_cli_status_ya_no_acepta_detail(self):
        parser = cli.build_parser()

        self.assertFalse(hasattr(parser.parse_args(["status", "test"]), "detail"))
        with self.assertRaises(SystemExit):
            parser.parse_args(["status", "test", "--detail"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["status", "test", "-d"])


if __name__ == "__main__":
    unittest.main()
