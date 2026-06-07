"""Implementación de comandos de alto nivel de pmsctl."""

from pmsctl import audit, oracle, storage


def _status_from_node(label, node, timeout):
    """Obtiene estado de un nodo y lo etiqueta como primaria o standby."""

    data = oracle.database_status(node, timeout=timeout)
    redo = oracle.redo_summary(
        node,
        applied_through_datafiles=label == "STANDBY",
        timeout=timeout,
    )
    status = {
        "role": label,
        "host": node.get("host"),
        "oracle_sid": node.get("oracle_sid"),
        "reachable": data.get("reachable", "NO"),
        "instance_status": data.get("instance_status", "UNKNOWN"),
        "database_status": data.get("database_status", "UNKNOWN"),
        "database_role": data.get("database_role", "UNKNOWN"),
        "open_mode": data.get("open_mode", "UNKNOWN"),
        "log_mode": data.get("log_mode", "UNKNOWN"),
        "current_scn": data.get("current_scn", "UNKNOWN"),
        "datafile_checkpoint_scn_min": data.get("datafile_checkpoint_scn_min", "UNKNOWN"),
        "datafile_checkpoint_scn_max": data.get("datafile_checkpoint_scn_max", "UNKNOWN"),
        "error": data.get("error"),
    }
    if label == "STANDBY":
        status["last_applied_redo_thread"] = redo.get("last_redo_thread", "UNKNOWN")
        status["last_applied_redo_sequence"] = redo.get("last_redo_sequence", "UNKNOWN")
        status["last_applied_redo_next_change"] = redo.get("last_redo_next_change", "UNKNOWN")
    else:
        status["last_archived_redo_thread"] = redo.get("last_redo_thread", "UNKNOWN")
        status["last_archived_redo_sequence"] = redo.get("last_redo_sequence", "UNKNOWN")
        status["last_archived_redo_next_change"] = redo.get("last_redo_next_change", "UNKNOWN")
    if redo.get("reachable") != "YES":
        status["redo_error"] = redo.get("error")
    return status


def import_config(path):
    """Comando ``config import``."""

    config = storage.import_config(path)
    audit.log_event(config["name"], "config import", "OK", "Configuración importada.")
    return {
        "result": "OK",
        "configuration": config["name"],
        "state": "REGISTERED",
        "message": "Configuración importada correctamente.",
    }


def list_configs():
    """Comando ``config list``."""

    names = storage.list_configs()
    audit.log_event(None, "config list", "OK", "Listado de configuraciones.")
    return {"result": "OK", "configurations": names, "count": len(names)}


def show_config(name):
    """Comando ``config show``."""

    config = storage.load_config(name)
    state = storage.load_state(name)
    audit.log_event(name, "config show", "OK", "Consulta de configuración.")
    return {"result": "OK", "configuration": config, "state": state}


def validate(name):
    """Comando ``validate``."""

    config = storage.load_config(name)
    result = __import__("pmsctl.validators", fromlist=["validate_environment"]).validate_environment(config)
    audit.log_event(name, "validate", result["result"], "Validación de entorno ejecutada.", result)
    return {"configuration": name, "action": "VALIDATE", **result}


def status(name):
    """Comando ``status``."""

    config = storage.load_config(name)
    timeout = int(config.get("settings", {}).get("ssh_timeout", 20))
    primary = _status_from_node("PRIMARY", config["primary"], timeout)
    standby = _status_from_node("STANDBY", config["standby"], timeout)
    result = "OK" if primary["reachable"] == "YES" and standby["reachable"] == "YES" else "WARNING"
    state = storage.load_state(name)
    state["state"] = "STATUS_CHECKED"
    state["last_status"] = {"primary": primary, "standby": standby}
    storage.save_state(name, state)
    payload = {
        "result": result,
        "configuration": name,
        "primary": primary,
        "standby": standby,
        "last_known_state": state.get("state"),
    }
    audit.log_event(name, "status", result, "Consulta de estado ejecutada.", payload)
    return payload


def _to_int(value):
    """Convierte una secuencia a entero cuando sea posible."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def lag(name):
    """Comando ``lag``."""

    config = storage.load_config(name)
    timeout = int(config.get("settings", {}).get("ssh_timeout", 20))
    primary = oracle.archive_summary(config["primary"], applied_filter=False, timeout=timeout)
    standby = oracle.archive_summary(config["standby"], applied_filter=True, timeout=timeout)

    primary_seq = _to_int(primary.get("last_sequence"))
    standby_seq = _to_int(standby.get("last_sequence"))
    sequence_lag = "UNKNOWN"
    if primary_seq is not None and standby_seq is not None:
        sequence_lag = max(primary_seq - standby_seq, 0)

    primary_time = oracle.parse_oracle_time(primary.get("last_time"))
    standby_time = oracle.parse_oracle_time(standby.get("last_time"))
    lag_minutes = "UNKNOWN"
    if primary_time and standby_time:
        lag_minutes = int(max((primary_time - standby_time).total_seconds(), 0) / 60)

    warning = int(config.get("settings", {}).get("lag_warning_minutes", 30))
    critical = int(config.get("settings", {}).get("lag_critical_minutes", 60))
    alert = "UNKNOWN"
    if isinstance(lag_minutes, int):
        if lag_minutes >= critical:
            alert = "CRITICAL"
        elif lag_minutes >= warning:
            alert = "WARNING"
        else:
            alert = "OK"

    result = "OK" if primary.get("reachable") == "YES" and standby.get("reachable") == "YES" else "WARNING"
    payload = {
        "result": result,
        "configuration": name,
        "primary": {
            "last_archived_sequence": primary.get("last_sequence", "UNKNOWN"),
            "last_archived_time": primary.get("last_time", "UNKNOWN"),
            "source": "v$archived_log",
            "reachable": primary.get("reachable", "NO"),
            "error": primary.get("error"),
        },
        "standby": {
            "last_applied_sequence": standby.get("last_sequence", "UNKNOWN"),
            "last_applied_time": standby.get("last_time", "UNKNOWN"),
            "source": "v$archived_log",
            "reachable": standby.get("reachable", "NO"),
            "error": standby.get("error"),
        },
        "sequence_lag": sequence_lag,
        "estimated_lag_minutes": lag_minutes,
        "alert": alert,
    }
    audit.log_event(name, "lag", result, "Consulta de lag ejecutada.", payload)
    return payload


def history(name, limit=20):
    """Comando ``history``."""

    storage.load_config(name)
    events = audit.read_history(configuration=name, limit=limit)
    audit.log_event(name, "history", "OK", "Consulta de histórico.")
    return {"result": "OK", "configuration": name, "events": events, "count": len(events)}
