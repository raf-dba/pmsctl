"""Ejecución local y remota por SSH.

Este módulo encapsula todos los detalles de ejecución de comandos. El resto de
la herramienta no debe construir llamadas SSH directamente, lo que facilita
cambiar la estrategia en futuras versiones.
"""

import shlex
import subprocess


class CommandResult(object):
    """Resultado simple de una ejecución de sistema operativo."""

    def __init__(self, returncode, stdout, stderr, command):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command

    @property
    def ok(self):
        """Indica si el comando finalizó con código cero."""

        return self.returncode == 0

    def summary(self):
        """Resumen serializable para errores y trazas."""

        return {
            "returncode": self.returncode,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
            "command": self.command,
        }


def is_local_node(node):
    """Determina si un nodo debe ejecutarse localmente."""

    host = str(node.get("host", "")).lower()
    return bool(node.get("local")) or host in ("localhost", "127.0.0.1", "::1", "local")


def _oracle_environment_prefix(node):
    """Construye el prefijo de entorno Oracle para shell remoto."""

    oracle_home = shlex.quote(node.get("oracle_home", ""))
    oracle_sid = shlex.quote(node.get("oracle_sid", ""))
    return (
        "export ORACLE_HOME={home}; "
        "export ORACLE_SID={sid}; "
        "export PATH=\"$ORACLE_HOME/bin:$PATH\"; "
    ).format(home=oracle_home, sid=oracle_sid)


def run(node, command, stdin_text=None, timeout=20):
    """Ejecuta un comando en un nodo local o remoto.

    El comando recibido se ejecuta bajo ``bash -lc`` para que las variables de
    entorno Oracle estén disponibles de forma consistente. En remoto se usa SSH
    con ``BatchMode`` para evitar bloqueos por petición de contraseña.
    """

    prepared = _oracle_environment_prefix(node) + command
    if is_local_node(node):
        argv = ["/bin/bash", "-lc", prepared]
        shown_command = prepared
    else:
        target = "%s@%s" % (node.get("ssh_user"), node.get("host"))
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=%s" % int(timeout),
            target,
            prepared,
        ]
        shown_command = "ssh %s %s" % (target, prepared)

    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    try:
        stdout, stderr = process.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return CommandResult(124, stdout, stderr + "\nTimeout de ejecución", shown_command)
    return CommandResult(process.returncode, stdout, stderr, shown_command)
