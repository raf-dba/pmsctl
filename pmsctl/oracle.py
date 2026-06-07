"""Consultas Oracle usadas por el piloto.

Solo se utilizan SQL*Plus y vistas dinámicas disponibles en Oracle Database SE2.
No se usa Data Guard, Broker, Active Data Guard ni funcionalidades Enterprise.
"""

import datetime

from pmsctl import remote


SQLPLUS_PREAMBLE = """
set heading off
set feedback off
set verify off
set echo off
set pagesize 0
set linesize 32767
whenever sqlerror exit sql.sqlcode
"""


def run_sqlplus(node, sql, timeout=30):
    """Ejecuta SQL*Plus localmente en el nodo indicado.

    La conexión es ``/ as sysdba`` para evitar almacenar contraseñas
    de base de datos. El usuario del sistema operativo debe pertenecer a los
    grupos Oracle adecuados.
    """

    script = SQLPLUS_PREAMBLE + "\n" + sql.strip() + "\nexit\n"
    return remote.run(node, "sqlplus -s / as sysdba", stdin_text=script, timeout=timeout)


def parse_key_values(output):
    """Convierte líneas ``CLAVE=valor`` en un diccionario."""

    data = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip().lower()] = value.strip()
    return data


def database_status(node, timeout=30):
    """Obtiene un estado básico de instancia, base de datos y datafiles.

    ``v$database.current_scn`` puede devolver cero cuando la base de datos está
    montada. Los checkpoints de ``v$datafile_header`` permiten conocer el SCN
    alcanzado por los datafiles después de una recuperación. Se excluye
    ``PDB$SEED`` (CON_ID=2) porque es de solo lectura y su checkpoint no avanza
    con la actividad normal de la base de datos.
    """

    sql = """
select 'INSTANCE_STATUS=' || status from v$instance;
select 'DATABASE_STATUS=' || database_status from v$instance;
select 'DATABASE_ROLE=' || database_role from v$database;
select 'OPEN_MODE=' || open_mode from v$database;
select 'LOG_MODE=' || log_mode from v$database;
select 'CURRENT_SCN=' || current_scn from v$database;
select 'DATAFILE_CHECKPOINT_SCN_MIN=' || nvl(to_char(min(checkpoint_change#)), 'UNKNOWN')
  from v$datafile_header
 where con_id <> 2;
select 'DATAFILE_CHECKPOINT_SCN_MAX=' || nvl(to_char(max(checkpoint_change#)), 'UNKNOWN')
  from v$datafile_header
 where con_id <> 2;
"""
    result = run_sqlplus(node, sql, timeout=timeout)
    if not result.ok:
        return {
            "reachable": "NO",
            "error": result.stderr.strip() or result.stdout.strip(),
            "raw": result.summary(),
        }
    values = parse_key_values(result.stdout)
    values["reachable"] = "YES"
    return values


def archive_summary(node, applied_filter=False, timeout=30):
    """Consulta la última secuencia archived o aplicada.

    ``applied_filter`` se usa en standby para intentar conocer el último redo
    aplicado. Si la vista no contiene información suficiente, el llamador deberá
    mostrar ``UNKNOWN``.
    """

    where = "where applied = 'YES'" if applied_filter else "where archived = 'YES'"
    sql = """
select 'LAST_SEQUENCE=' || nvl(to_char(max(sequence#)), 'UNKNOWN') from v$archived_log {where};
select 'LAST_TIME=' || nvl(to_char(max(completion_time), 'YYYY-MM-DD HH24:MI:SS'), 'UNKNOWN') from v$archived_log {where};
""".format(
        where=where
    )
    result = run_sqlplus(node, sql, timeout=timeout)
    if not result.ok:
        return {
            "reachable": "NO",
            "last_sequence": "UNKNOWN",
            "last_time": "UNKNOWN",
            "error": result.stderr.strip() or result.stdout.strip(),
            "raw": result.summary(),
        }
    values = parse_key_values(result.stdout)
    values["reachable"] = "YES"
    values.setdefault("last_sequence", "UNKNOWN")
    values.setdefault("last_time", "UNKNOWN")
    return values


def parse_oracle_time(value):
    """Convierte una fecha Oracle del piloto a ``datetime``."""

    if not value or value == "UNKNOWN":
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
