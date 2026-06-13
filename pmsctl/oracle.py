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
    """Obtiene los datos operativos que necesita el comando ``status``.

    La consulta se limita a vistas dinámicas disponibles en Oracle Database
    Standard Edition 2. El estado de recuperación se estima comprobando si hay
    una sesión RMAN activa: en este piloto la recuperación se ejecuta mediante
    RMAN y no mediante los procesos gestionados de Oracle Data Guard.
    """

    sql = """
select 'INSTANCE_STATUS=' || status from v$instance;
select 'DATABASE_STATUS=' || database_status from v$instance;
select 'DB_UNIQUE_NAME=' || db_unique_name from v$database;
select 'DATABASE_ROLE=' || database_role from v$database;
select 'OPEN_MODE=' || open_mode from v$database;
select 'LOG_MODE=' || log_mode from v$database;
select 'CURRENT_SCN=' || current_scn from v$database;
select 'RECOVERY_STATUS=' ||
       case when count(*) > 0 then 'RUNNING' else 'IDLE' end
  from v$session
 where lower(program) like 'rman%'
    or lower(module) like 'rman%';
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


def redo_summary(node, applied_through_datafiles=False, timeout=30):
    """Consulta el último archived redo relevante y su referencia temporal.

    En primaria devuelve el archived redo con mayor ``next_change#`` de la
    encarnación actual. En standby limita la consulta a los archived redo cuyo
    ``next_change#`` está cubierto por el checkpoint mínimo de los datafiles,
    para no confundir un redo recibido con uno aplicado. La fecha se toma del
    mismo redo seleccionado por ``next_change#`` y permite estimar el lag
    temporal respecto al último redo archivado en primaria.
    """

    applied_condition = ""
    if applied_through_datafiles:
        applied_condition = """
   and next_change# <= (
       select min(checkpoint_change#)
         from v$datafile_header
        where con_id <> 2
   )"""

    sql = """
select 'LAST_REDO_THREAD=' ||
       nvl(to_char(max(thread#) keep (dense_rank last order by next_change#)), 'UNKNOWN')
  from v$archived_log
 where archived = 'YES'
   and resetlogs_change# = (select resetlogs_change# from v$database){applied_condition};
select 'LAST_REDO_SEQUENCE=' ||
       nvl(to_char(max(sequence#) keep (dense_rank last order by next_change#)), 'UNKNOWN')
  from v$archived_log
 where archived = 'YES'
   and resetlogs_change# = (select resetlogs_change# from v$database){applied_condition};
select 'LAST_REDO_NEXT_CHANGE=' || nvl(to_char(max(next_change#)), 'UNKNOWN')
  from v$archived_log
 where archived = 'YES'
   and resetlogs_change# = (select resetlogs_change# from v$database){applied_condition};
select 'LAST_REDO_TIME=' ||
       nvl(to_char(
           max(completion_time) keep (dense_rank last order by next_change#),
           'YYYY-MM-DD HH24:MI:SS'
       ), 'UNKNOWN')
  from v$archived_log
 where archived = 'YES'
   and resetlogs_change# = (select resetlogs_change# from v$database){applied_condition};
""".format(
        applied_condition=applied_condition
    )
    result = run_sqlplus(node, sql, timeout=timeout)
    if not result.ok:
        return {
            "reachable": "NO",
            "last_redo_thread": "UNKNOWN",
            "last_redo_sequence": "UNKNOWN",
            "last_redo_next_change": "UNKNOWN",
            "last_redo_time": "UNKNOWN",
            "error": result.stderr.strip() or result.stdout.strip(),
            "raw": result.summary(),
        }
    values = parse_key_values(result.stdout)
    values["reachable"] = "YES"
    values.setdefault("last_redo_thread", "UNKNOWN")
    values.setdefault("last_redo_sequence", "UNKNOWN")
    values.setdefault("last_redo_next_change", "UNKNOWN")
    values.setdefault("last_redo_time", "UNKNOWN")
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
