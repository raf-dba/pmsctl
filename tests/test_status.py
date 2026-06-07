import unittest
from unittest import mock

from pmsctl import commands, oracle, remote


class StatusTest(unittest.TestCase):
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

        status = oracle.database_status({"host": "local"})

        self.assertEqual(status["current_scn"], "0")
        self.assertEqual(status["datafile_checkpoint_scn_min"], "100")
        self.assertEqual(status["datafile_checkpoint_scn_max"], "120")
        sql = run_sqlplus.call_args.args[1]
        self.assertIn("v$datafile_header", sql)
        self.assertIn("where con_id <> 2", sql)

    @mock.patch("pmsctl.commands.oracle.database_status")
    def test_status_propaga_checkpoints_retornados_por_oracle(self, database_status):
        database_status.return_value = {
            "reachable": "YES",
            "current_scn": "0",
            "datafile_checkpoint_scn_min": "100",
            "datafile_checkpoint_scn_max": "120",
        }

        status = commands._status_from_node(
            "STANDBY",
            {"host": "standby.example", "oracle_sid": "TEST"},
            timeout=20,
        )

        self.assertEqual(status["datafile_checkpoint_scn_min"], "100")
        self.assertEqual(status["datafile_checkpoint_scn_max"], "120")


if __name__ == "__main__":
    unittest.main()
