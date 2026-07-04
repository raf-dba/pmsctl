"""Interfaz de línea de comandos de pmsctl."""


"""Usaremos la libreria argparse para gestionar los parámetros."""
import argparse
import sys

from pmsctl import __version__, commands, output
from pmsctl.errors import PmsctlError

"""Construye el parser de argumentos de la CLI."""
def build_parser():
    
    """Definimos el parseador indicando programa y dos argumentos válidos que mostrará la ayuda."""
    parser = argparse.ArgumentParser(
        prog="pmsctl",
        description="Poor Man Standby Control para Oracle SE2.",
    )
    """Definimos parametros globales."""
    parser.add_argument("--json", action="store_true", help="Muestra la salida en formato JSON.")
    parser.add_argument("--version", action="version", version="pmsctl %s" % __version__)

    """Definimos un grupo de subcomandos."""
    subparsers = parser.add_subparsers(dest="command")

    """Definimos los diferentes subcomandos."""
    """Definimos el comando config."""
    config = subparsers.add_parser("config", help="Gestiona configuraciones locales.")

    """Que a su vez tendrá otros subcomandos."""
    config_sub = config.add_subparsers(dest="config_command")
    
    """Definimos el primer subcomando de config, import con el argumento file."""
    config_import = config_sub.add_parser("import", help="Importa una configuración desde JSON.")
    config_import.add_argument("file", help="Fichero JSON de configuración.")
    
    """Definimos el segundo subcomando de config, list."""
    config_sub.add_parser("list", help="Lista configuraciones registradas.")

    """Definimos el tercer subcomando de config, show con el argumento name."""
    config_show = config_sub.add_parser("show", help="Muestra una configuración.")
    config_show.add_argument("name", help="Nombre lógico de configuración.")

    """Definimos el comando validate, con el argumento name"""
    validate = subparsers.add_parser("validate", help="Valida conectividad y entorno Oracle.")
    validate.add_argument("name", help="Nombre lógico de configuración.")

    """Definimos el comando status, con el argumento name"""
    status = subparsers.add_parser("status", help="Consulta el estado de primaria y standby.")
    status.add_argument("name", help="Nombre lógico de configuración.")

    """Definimos el comando lag, con el argumento name"""
    lag = subparsers.add_parser("lag", help="Consulta el lag estimado de réplica.")
    lag.add_argument("name", help="Nombre lógico de configuración.")

    """Definimos el comando history, con los argumento name y limit"""
    history = subparsers.add_parser("history", help="Consulta el histórico de operaciones.")
    history.add_argument("name", help="Nombre lógico de configuración.")
    history.add_argument("--limit", type=int, default=20, help="Número máximo de eventos a mostrar.")

    return parser


def dispatch(args):
    """En función del comando solicitado ejecuta la llamada correspondiente y devuelve su resultado."""

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


"""Función principal usada por el ejecutable."""
def main(argv=None):


    """Creo el parseador y recupero lista de argumentos."""
    parser = build_parser()
    args = parser.parse_args(argv)
    """Si los argumentos no existen muestro la ayuda."""
    if not args.command:
        parser.print_help()
        return 2

    try:
        """Recuperamos el resultado de la operacion y lo mostramos."""
        result = dispatch(args)
        output.emit(result, json_mode=args.json)
        return 0 if result.get("result") in ("OK", "SUCCESS", None) else 1
    except PmsctlError as exc:
        output.emit(exc.to_dict(), json_mode=args.json)
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("Operación interrumpida por el usuario.\n")
        return 130
