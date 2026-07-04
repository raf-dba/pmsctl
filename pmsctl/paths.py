"""Rutas utilizadas por pmsctl.

El piloto almacena configuración, estado y logs en ficheros locales. La ruta
base puede cambiarse con la variable de entorno ``PMSCTL_HOME`` para facilitar
pruebas o despliegues sin tocar el código.

En futuras versiones se puede plantear el uso de alguna base de datos especializada
"""

import os


def project_root():
    """Devuelve la raíz del proyecto donde está instalado este paquete."""

    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def home_dir():
    """Devuelve el directorio operativo de pmsctl.

    Por defecto coincide con la raíz del proyecto. En pruebas o instalaciones
    empaquetadas se puede definir ``PMSCTL_HOME``.
    """

    return os.path.abspath(os.environ.get("PMSCTL_HOME", project_root()))


def var_dir():
    """Directorio base de datos variables generados por la herramienta."""

    return os.path.join(home_dir(), "var")


def configs_dir():
    """Directorio donde se guardan las configuraciones importadas."""

    return os.path.join(var_dir(), "configs")


def state_dir():
    """Directorio donde se guarda el último estado conocido."""

    return os.path.join(var_dir(), "state")


def logs_dir():
    """Directorio donde se guarda el histórico de operaciones."""

    return os.path.join(var_dir(), "logs")


def ensure_runtime_dirs():
    """Crea los directorios variables necesarios si todavía no existen."""

    for path in (configs_dir(), state_dir(), logs_dir()):
        if not os.path.isdir(path):
            os.makedirs(path)


def config_file(name):
    """Ruta del fichero JSON de una configuración concreta."""

    return os.path.join(configs_dir(), "%s.json" % name)


def state_file(name):
    """Ruta del fichero JSON de estado de una configuración concreta."""

    return os.path.join(state_dir(), "%s.json" % name)


def events_file():
    """Ruta del histórico estructurado en formato JSONL."""

    return os.path.join(logs_dir(), "events.jsonl")


def human_log_file():
    """Ruta del log legible por humanos."""

    return os.path.join(logs_dir(), "pmsctl.log")
