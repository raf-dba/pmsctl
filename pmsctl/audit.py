"""Registro de operaciones y eventos.

El histórico es parte del comportamiento funcional del piloto. Se guarda una
línea JSON por evento para facilitar automatización y un log de texto para
lectura rápida por operadores.
"""

import datetime
import getpass
import json
import os

from pmsctl import paths

"""Devuelve la fecha actual en UTC con un formato estable."""
def utc_now():
    
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

"""Registra una operación administrativa."""
def log_event(configuration, command, result, message="", details=None):
    
    """Validamos/intentamos crear los directorios en los que almacenar la información."""
    paths.ensure_runtime_dirs()

    """Preparamos el registro a almacenar."""
    event = {
        "timestamp": utc_now(),
        "user": getpass.getuser(),
        "configuration": configuration,
        "command": command,
        "result": result,
        "message": message,
        "details": details or {},
    }
    """Abrimos los dos ficheros de log."""
    with open(paths.events_file(), "a") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")

    with open(paths.human_log_file(), "a") as handle:
        handle.write(
            "{timestamp} {result} config={configuration} command={command} message={message}\n".format(
                **event
            )
        )
    return event

"""Lee el histórico estructurado filtrando por configuración si se indica."""
def read_history(configuration=None, limit=20):
    

    path = paths.events_file()
    if not os.path.exists(path):
        return []

    events = []
    with open(path, "r") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if configuration and event.get("configuration") != configuration:
                continue
            events.append(event)
    if limit:
        return events[-limit:]
    return events
