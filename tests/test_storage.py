import json
import os
import shutil
import tempfile
import unittest

from pmsctl import storage
from pmsctl.errors import PmsctlError


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_home = os.environ.get("PMSCTL_HOME")
        os.environ["PMSCTL_HOME"] = self.tmpdir

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop("PMSCTL_HOME", None)
        else:
            os.environ["PMSCTL_HOME"] = self.old_home
        shutil.rmtree(self.tmpdir)

    def _write_config(self, data):
        path = os.path.join(self.tmpdir, "config.json")
        with open(path, "w") as handle:
            json.dump(data, handle)
        return path

    def _valid_config(self):
        return {
            "name": "prod_to_dr",
            "primary": {
                "host": "local",
                "ssh_user": "oracle",
                "oracle_home": "/oracle/home",
                "oracle_sid": "PROD",
                "archive_dest": "/arch",
            },
            "standby": {
                "host": "dr",
                "ssh_user": "oracle",
                "oracle_home": "/oracle/home",
                "oracle_sid": "PRODDR",
                "archive_dest": "/arch",
            },
        }

    def test_importa_configuracion_valida(self):
        path = self._write_config(self._valid_config())
        config = storage.import_config(path)
        self.assertEqual(config["name"], "prod_to_dr")
        self.assertEqual(storage.list_configs(), ["prod_to_dr"])
        self.assertEqual(storage.load_state("prod_to_dr")["state"], "REGISTERED")

    def test_rechaza_configuracion_duplicada(self):
        path = self._write_config(self._valid_config())
        storage.import_config(path)
        with self.assertRaises(PmsctlError):
            storage.import_config(path)

    def test_rechaza_password_en_configuracion(self):
        data = self._valid_config()
        data["primary"]["password"] = "no_debe_guardarse"
        path = self._write_config(data)
        with self.assertRaises(PmsctlError):
            storage.import_config(path)


if __name__ == "__main__":
    unittest.main()
