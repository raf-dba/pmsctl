"""Formato de salida de la CLI."""

import json
import sys


TITLE_OVERRIDES = {
    "database_role": "ORACLE DATABASE ROLE",
    "role": "PMS ROLE",
}


def emit(data, json_mode=False):
    """Imprime una respuesta en modo humano o JSON."""

    if json_mode:
        sys.stdout.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(format_human(data) + "\n")


def _title(key):
    """Convierte una clave interna en etiqueta de salida."""

    if key in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[key]
    return key.upper().replace("_", " ")


def format_human(data, indent=0):
    """Convierte diccionarios y listas en una salida textual sencilla."""

    lines = []
    prefix = " " * indent
    if isinstance(data, dict):
        for key in sorted(data.keys()):
            value = data[key]
            if isinstance(value, dict):
                lines.append("%s%s:" % (prefix, _title(key)))
                lines.append(format_human(value, indent + 2))
            elif isinstance(value, list):
                lines.append("%s%s:" % (prefix, _title(key)))
                for item in value:
                    if isinstance(item, (dict, list)):
                        lines.append(format_human(item, indent + 2))
                    else:
                        lines.append("%s- %s" % (" " * (indent + 2), item))
            else:
                lines.append("%s%s: %s" % (prefix, _title(key), value))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(format_human(item, indent))
            else:
                lines.append("%s- %s" % (prefix, item))
    else:
        lines.append("%s%s" % (prefix, data))
    return "\n".join(lines)
