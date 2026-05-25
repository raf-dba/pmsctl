"""Persistencia local de configuraciones y estados.

Se usan ficheros JSON para mantener el piloto simple, auditable y compatible con
Python 3.6 sin dependencias externas. Cada configuración vive en un fichero
independiente para permitir varias réplicas gestionadas por el mismo nodo.
En un futuro se puede plantear usar una BBDD SQLite o MySQL
"""

import json
import os
import re

from pmsctl import paths
from pmsctl.errors import PmsctlError


NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _read_json(path):
    """Lee un fichero JSON y devuelve su contenido como diccionario."""

    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except ValueError as exc:
        raise PmsctlError(
            "INVALID_JSON",
            "El fichero JSON no tiene un formato válido.",
            "Revise la sintaxis del fichero y vuelva a importar la configuración.",
            {"path": path, "error": str(exc)},
        )


def _write_json(path, data):
    """Escribe JSON de forma legible y estable."""

    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    tmp_path = "%s.tmp" % path
    with open(tmp_path, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.rename(tmp_path, path)


def _reject_secret_fields(data, prefix=""):
    """Evita que se guarden contraseñas en la configuración.

    La herramienta debe operar con SSH por clave y autenticación local Oracle
    ``/ as sysdba``. Guardar contraseñas iría contra el diseño del TFG.
    """

    forbidden = ("password", "passwd", "pwd", "secret")
    if isinstance(data, dict):
        for key, value in data.items():
            lower = key.lower()
            if any(token in lower for token in forbidden):
                raise PmsctlError(
                    "SECRET_IN_CONFIG",
                    "La configuración contiene un campo que parece una contraseña.",
                    "Elimine contraseñas o secretos del JSON y use autenticación SSH por clave.",
                    {"field": "%s.%s" % (prefix, key) if prefix else key},
                )
            _reject_secret_fields(value, "%s.%s" % (prefix, key) if prefix else key)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            _reject_secret_fields(value, "%s[%s]" % (prefix, index))


def validate_config_data(data):
    """Valida la estructura mínima de una configuración importada."""

    if not isinstance(data, dict):
        raise PmsctlError("INVALID_CONFIG", "La configuración debe ser un objeto JSON.")

    name = data.get("name")
    if not name or not isinstance(name, str) or not NAME_RE.match(name):
        raise PmsctlError(
            "INVALID_CONFIG_NAME",
            "El nombre de configuración es obligatorio y solo puede contener letras, números, punto, guion y guion bajo.",
            "Corrija el campo 'name' del JSON.",
        )

    for section in ("primary", "standby"):
        if section not in data or not isinstance(data[section], dict):
            raise PmsctlError(
                "INVALID_CONFIG",
                "Falta la sección obligatoria '%s'." % section,
                "Añada la sección '%s' al JSON de configuración." % section,
            )
        node = data[section]
        for field in ("host", "ssh_user", "oracle_home", "oracle_sid", "archive_dest"):
            if not node.get(field):
                raise PmsctlError(
                    "INVALID_CONFIG",
                    "Falta el campo obligatorio '%s.%s'." % (section, field),
                    "Complete todos los campos mínimos antes de importar la configuración.",
                )

    if "settings" not in data:
        data["settings"] = {}
    data["settings"].setdefault("ssh_timeout", 20)
    data["settings"].setdefault("lag_warning_minutes", 30)
    data["settings"].setdefault("lag_critical_minutes", 60)

    _reject_secret_fields(data)
    return data


def import_config(source_path, overwrite=False):
    """Importa una configuración desde un fichero JSON externo."""

    paths.ensure_runtime_dirs()
    data = validate_config_data(_read_json(source_path))
    target = paths.config_file(data["name"])
    if os.path.exists(target) and not overwrite:
        raise PmsctlError(
            "CONFIG_EXISTS",
            "Ya existe una configuración con el nombre '%s'." % data["name"],
            "Use otro nombre o elimine la configuración existente manualmente si procede.",
        )
    _write_json(target, data)
    if not os.path.exists(paths.state_file(data["name"])):
        save_state(data["name"], {"state": "REGISTERED", "last_status": None})
    return data


def list_configs():
    """Lista los nombres de configuraciones registradas."""

    paths.ensure_runtime_dirs()
    result = []
    for filename in sorted(os.listdir(paths.configs_dir())):
        if filename.endswith(".json"):
            result.append(filename[:-5])
    return result


def load_config(name):
    """Carga una configuración por nombre lógico."""

    if not NAME_RE.match(name or ""):
        raise PmsctlError("INVALID_CONFIG_NAME", "Nombre de configuración no válido.")
    path = paths.config_file(name)
    if not os.path.exists(path):
        raise PmsctlError(
            "CONFIG_NOT_FOUND",
            "No existe la configuración '%s'." % name,
            "Importe primero la configuración con 'pmsctl config import'.",
        )
    return validate_config_data(_read_json(path))


def load_state(name):
    """Carga el último estado conocido de una configuración."""

    path = paths.state_file(name)
    if not os.path.exists(path):
        return {"state": "UNKNOWN", "last_status": None}
    return _read_json(path)


def save_state(name, state):
    """Guarda el último estado conocido de una configuración."""

    paths.ensure_runtime_dirs()
    _write_json(paths.state_file(name), state)
