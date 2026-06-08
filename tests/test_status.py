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
    def test_database_status_incluye_checkpoints_de_datafiles(self, run_sqlplus):
        run_sqlplus.return_value = remote.CommandResult(
            0,
            "\n".join(
                [
                    "CURRENT_SCN=0",
                    "DATAFILE_CHECKPOINT_SCN_MIN=100",
                    "DATAFILE_CHECKPOINT_SCN_MAX=120",
                ]
            ),
            "",
            "sqlplus -s / as sysdba",
        )

        status = oracle.database_status({"host": "local"}, detail=True)

        self.assertEqual(status["current_scn"], "0")
        self.assertEqual(status["datafile_checkpoint_scn_min"], "100")
        self.assertEqual(status["datafile_checkpoint_scn_max"], "120")
        sql = run_sqlplus.call_args.args[1]
        self.assertIn("v$datafile_header", sql)
        self.assertIn("where con_id <> 2", sql)

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
        sql = run_sqlplus.call_args.args[1]
        self.assertIn("next_change# <= (", sql)
        self.assertIn("min(checkpoint_change#)", sql)

    @mock.patch("pmsctl.commands.oracle.database_status")
    @mock.patch("pmsctl.commands.oracle.redo_summary")
    def test_status_propaga_checkpoints_y_redo_de_standby(self, redo_summary, database_status):
        database_status.return_value = {
            "reachable": "YES",
            "current_scn": "0",
            "datafile_checkpoint_scn_min": "100",
            "datafile_checkpoint_scn_max": "120",
        }
        redo_summary.return_value = {
            "reachable": "YES",
            "last_redo_thread": "1",
            "last_redo_sequence": "10",
            "last_redo_next_change": "100",
        }

        status = commands._status_from_node(
            "STANDBY",
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
            detail=True,
        )

        self.assertEqual(status["datafile_checkpoint_scn_min"], "100")
        self.assertEqual(status["datafile_checkpoint_scn_max"], "120")
        self.assertEqual(status["last_applied_redo_sequence"], "10")
        self.assertNotIn("last_archived_redo_sequence", status)
        redo_summary.assert_called_once_with(
            {"host": "standby.example", "oracle_sid": "TEST"},
            applied_through_datafiles=True,
            timeout=20,
        )

    @mock.patch("pmsctl.commands.oracle.database_status")
    @mock.patch("pmsctl.commands.oracle.redo_summary")
    def test_status_basico_no_consulta_ni_muestra_detalle(self, redo_summary, database_status):
        database_status.return_value = {
            "reachable": "YES",
            "current_scn": "0",
            "datafile_checkpoint_scn_min": "100",
        }

        status = commands._status_from_node(
            "STANDBY",
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
        )

        self.assertEqual(status["current_scn"], "0")
        self.assertNotIn("datafile_checkpoint_scn_min", status)
        self.assertNotIn("last_applied_redo_sequence", status)
        database_status.assert_called_once_with(
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
            detail=False,
        )
        redo_summary.assert_not_called()

    def test_cli_status_acepta_detail_y_alias_corto(self):
        parser = cli.build_parser()

        self.assertFalse(parser.parse_args(["status", "test"]).detail)
        self.assertTrue(parser.parse_args(["status", "test", "--detail"]).detail)
        self.assertTrue(parser.parse_args(["status", "test", "-d"]).detail)


if __name__ == "__main__":
    unittest.main()
