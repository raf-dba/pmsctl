"""Interfaz de línea de comandos de pmsctl."""

import argparse
import sys

from pmsctl import __version__, commands, output
from pmsctl.errors import PmsctlError


def build_parser():
    """Construye el parser de argumentos de la CLI."""

    parser = argparse.ArgumentParser(
        prog="pmsctl",
        description="Piloto mínimo de Poor Man Standby Control para Oracle SE2.",
    )
    parser.add_argument("--json", action="store_true", help="Muestra la salida en formato JSON.")
    parser.add_argument("--version", action="version", version="pmsctl %s" % __version__)

    subparsers = parser.add_subparsers(dest="command")

    config = subparsers.add_parser("config", help="Gestiona configuraciones locales.")
    config_sub = config.add_subparsers(dest="config_command")
    config_import = config_sub.add_parser("import", help="Importa una configuración desde JSON.")
    config_import.add_argument("file", help="Fichero JSON de configuración.")
    config_sub.add_parser("list", help="Lista configuraciones registradas.")
    config_show = config_sub.add_parser("show", help="Muestra una configuración.")
    config_show.add_argument("name", help="Nombre lógico de configuración.")

    validate = subparsers.add_parser("validate", help="Valida conectividad y entorno Oracle.")
    validate.add_argument("name", help="Nombre lógico de configuración.")

    status = subparsers.add_parser("status", help="Consulta el estado de primaria y standby.")
    status.add_argument("name", help="Nombre lógico de configuración.")

    lag = subparsers.add_parser("lag", help="Consulta el lag estimado de réplica.")
    lag.add_argument("name", help="Nombre lógico de configuración.")

    history = subparsers.add_parser("history", help="Consulta el histórico de operaciones.")
    history.add_argument("name", help="Nombre lógico de configuración.")
    history.add_argument("--limit", type=int, default=20, help="Número máximo de eventos a mostrar.")

    return parser


def dispatch(args):
    """Ejecuta el comando solicitado y devuelve su respuesta."""

    if args.command == "config":
        if args.config_command == "import":
            return commands.import_config(args.file)
        if args.config_command == "list":
            return commands.list_configs()
        if args.config_command == "show":
            return commands.show_config(args.name)
    elif args.command == "validate":
        return commands.validate(args.name)
    elif args.command == "status":
        return commands.status(args.name)
    elif args.command == "lag":
        return commands.lag(args.name)
    elif args.command == "history":
        return commands.history(args.name, limit=args.limit)
    raise PmsctlError("INVALID_COMMAND", "Comando no reconocido.", "Ejecute 'pmsctl --help'.")


def main(argv=None):
    """Función principal usada por el ejecutable y por las pruebas."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    try:
        result = dispatch(args)
        output.emit(result, json_mode=args.json)
        return 0 if result.get("result") in ("OK", None) else 1
    except PmsctlError as exc:
        output.emit(exc.to_dict(), json_mode=args.json)
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("Operación interrumpida por el usuario.\n")
        return 130
