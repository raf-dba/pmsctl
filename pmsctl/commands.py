"""Implementación de comandos de alto nivel de pmsctl."""

from pmsctl import audit, oracle, storage


def _oracle_status_label(data):
    """Traduce la conectividad Oracle a la etiqueta operativa del TFG."""

    return "ONLINE" if data.get("reachable") == "YES" else "UNKNOWN"


def _archivelog_label(log_mode):
    """Convierte el modo Oracle en una indicación sencilla para el operador."""

    if log_mode == "ARCHIVELOG":
        return "ENABLED"
    if log_mode in (None, "UNKNOWN"):
        return "UNKNOWN"
    return "DISABLED"


def _status_from_node(label, node, timeout):
    """Construye la sección de estado de una primaria o una réplica.

    Primero se consulta el estado básico. Si el nodo no está disponible no se
    lanzan consultas adicionales, porque solo añadirían esperas y errores
    repetidos. En una réplica se distinguen expresamente los redo transferidos
    de los aplicados: los primeros existen en ``v$archived_log`` y los segundos
    están cubiertos por el checkpoint mínimo de los datafiles.
    """

    data = oracle.database_status(node, timeout=timeout)
    status = {
        "host": node.get("host"),
        "db_unique_name": data.get("db_unique_name", node.get("oracle_sid", "UNKNOWN")),
        "status": _oracle_status_label(data),
        "database_role": data.get("database_role", "UNKNOWN"),
        "open_mode": data.get("open_mode", "UNKNOWN"),
    }

    if label == "PRIMARY":
        status["archivelog_mode"] = _archivelog_label(data.get("log_mode"))
    else:
        status["recovery_status"] = data.get("recovery_status", "UNKNOWN")

    if data.get("reachable") != "YES":
        status["error"] = data.get("error") or "No se ha podido consultar la base de datos."
        return status

    if label == "PRIMARY":
        archived = oracle.redo_summary(node, timeout=timeout)
        status["last_archived_redo"] = archived.get("last_redo_sequence", "UNKNOWN")
        status["last_archived_time"] = archived.get("last_redo_time", "UNKNOWN")
        if archived.get("reachable") != "YES":
            status["redo_error"] = archived.get("error")
        return status

    transferred = oracle.redo_summary(node, timeout=timeout)
    applied = oracle.redo_summary(node, applied_through_datafiles=True, timeout=timeout)
    status["last_transferred_redo"] = transferred.get("last_redo_sequence", "UNKNOWN")
    status["last_transferred_time"] = transferred.get("last_redo_time", "UNKNOWN")
    status["last_applied_redo"] = applied.get("last_redo_sequence", "UNKNOWN")
    status["last_applied_time"] = applied.get("last_redo_time", "UNKNOWN")
    if transferred.get("reachable") != "YES" or applied.get("reachable") != "YES":
        status["redo_error"] = transferred.get("error") or applied.get("error")
    return status


def _add_last_known_data(current, previous, checked_at):
    """Añade el último estado válido cuando no puede consultarse un nodo.

    El Word exige diferenciar el estado actual de la última información válida.
    Solo se añaden datos históricos cuando el estado actual es desconocido, de
    modo que una consulta correcta no mezcle valores actuales y antiguos.
    """

    if current.get("status") == "ONLINE" or not previous:
        return
    current["last_known_status"] = previous.get("open_mode", previous.get("status", "UNKNOWN"))
    last_applied_redo = previous.get(
        "last_applied_redo",
        previous.get("last_applied_redo_sequence"),
    )
    if last_applied_redo is not None:
        current["last_known_applied_redo"] = last_applied_redo
    if checked_at:
        current["last_successful_check"] = checked_at


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
    """Lista configuraciones y muestra un resumen de su último estado.

    Se conserva la lista simple de nombres utilizada por versiones anteriores y
    se añade ``configuration_states`` para ofrecer la visión global resumida
    solicitada en RF16 sin ejecutar consultas remotas ni modificar estados.
    """

    names = storage.list_configs()
    configuration_states = {}
    for name in names:
        configuration_states[name] = storage.load_state(name).get("state", "UNKNOWN")
    audit.log_event(None, "config list", "OK", "Listado de configuraciones.")
    return {
        "result": "OK",
        "configurations": names,
        "configuration_states": configuration_states,
        "count": len(names),
        "message": "Configuraciones registradas consultadas correctamente.",
    }


def show_config(name):
    """Comando ``config show``."""

    config = storage.load_config(name)
    state = storage.load_state(name)
    audit.log_event(name, "config show", "OK", "Consulta de configuración.")
    return {"result": "OK", "configuration": config, "state": state}


def validate(name):
    """Valida el entorno y añade un resumen comprensible del resultado."""

    config = storage.load_config(name)
    result = __import__("pmsctl.validators", fromlist=["validate_environment"]).validate_environment(config)
    audit.log_event(name, "validate", result["result"], "Validación de entorno ejecutada.", result)
    message = (
        "Configuration environment validated successfully."
        if result["result"] == "OK"
        else "Configuration environment validation found errors."
    )
    return {"configuration": name, "action": "VALIDATE", "message": message, **result}


def status(name):
    """Consulta y presenta el estado operativo definido en RF8.

    La función conserva dos fotografías en el estado local: ``last_status`` es
    siempre el resultado más reciente, incluso si contiene errores, mientras
    que ``last_valid_status`` solo se reemplaza cuando ambos nodos responden.
    Esta separación permite mostrar información histórica sin presentarla como
    si fuera una lectura actual.
    """

    config = storage.load_config(name)
    timeout = int(config.get("settings", {}).get("ssh_timeout", 20))
    previous_state = storage.load_state(name)
    previous_valid = previous_state.get("last_valid_status") or {}
    if not previous_valid:
        # Las versiones anteriores solo guardaban ``last_status`` y llamaban
        # ``standby`` a la réplica. Se reutiliza esa fotografía únicamente si
        # ambos nodos constaban como accesibles, porque de otro modo no puede
        # considerarse un último estado válido.
        legacy_status = previous_state.get("last_status") or {}
        legacy_primary = legacy_status.get("primary") or {}
        legacy_replica = legacy_status.get("standby") or {}
        if (
            legacy_primary.get("reachable") == "YES"
            and legacy_replica.get("reachable") == "YES"
        ):
            previous_valid = {"primary": legacy_primary, "replica": legacy_replica}
    previous_check = previous_state.get("last_successful_check")

    primary = _status_from_node("PRIMARY", config["primary"], timeout)
    replica = _status_from_node("REPLICA", config["standby"], timeout)
    _add_last_known_data(primary, previous_valid.get("primary"), previous_check)
    _add_last_known_data(replica, previous_valid.get("replica"), previous_check)

    checked_at = audit.utc_now()
    both_online = primary.get("status") == "ONLINE" and replica.get("status") == "ONLINE"
    complete_status = both_online and "redo_error" not in primary and "redo_error" not in replica
    result = "SUCCESS" if complete_status else "ERROR"
    if complete_status:
        message = "Database status obtained successfully."
    else:
        message = "Unable to determine the current status of every database."

    # Se guarda el estado después de construir la salida para que una lectura
    # fallida nunca sustituya la última fotografía válida usada como respaldo.
    current_status = {"primary": primary, "replica": replica, "checked_at": checked_at}
    state = dict(previous_state)
    state["state"] = "STATUS_CHECKED"
    state["last_status"] = current_status
    if complete_status:
        state["last_valid_status"] = current_status
        state["last_successful_check"] = checked_at
    storage.save_state(name, state)

    payload = {"configuration": name}
    if config.get("description"):
        payload["description"] = config["description"]
    payload["primary"] = primary
    payload["replica"] = replica
    payload["result"] = result
    payload["message"] = message
    if not complete_status:
        payload["recommended_action"] = "Check database availability, network connectivity and SSH authentication."
    audit.log_event(name, "status", result, "Consulta de estado ejecutada.", payload)
    return payload


def _to_int(value):
    """Convierte una secuencia a entero cuando sea posible."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _lag_minutes(reference_time, progress_time):
    """Calcula minutos completos de retraso entre dos marcas Oracle.

    Las marcas proceden del redo archivado y representan una estimación del
    punto temporal alcanzado. Se limita el resultado inferior a cero para no
    publicar retardos negativos ante pequeñas diferencias de reloj o metadatos.
    """

    reference = oracle.parse_oracle_time(reference_time)
    progress = oracle.parse_oracle_time(progress_time)
    if not reference or not progress:
        return None
    return int(max((reference - progress).total_seconds(), 0) / 60)


def _display_minutes(value):
    """Da formato comprensible al lag sin ocultar la ausencia de datos."""

    if value is None:
        return "UNKNOWN"
    return "%s minutes" % value


def _lag_threshold(settings, specific_key):
    """Obtiene un umbral específico manteniendo compatibilidad de configuración.

    Las configuraciones anteriores solo disponen de ``lag_warning_minutes``.
    Ese valor se utiliza como respaldo hasta que se definan los umbrales
    separados ``max_transfer_lag_minutes`` y ``max_apply_lag_minutes``.
    """

    return int(settings.get(specific_key, settings.get("lag_warning_minutes", 30)))


def lag(name):
    """Estima por separado el lag de transferencia y de aplicación de redo.

    El último redo transferido es el último archivado visible en la réplica. El
    último aplicado es el redo cuyo ``next_change#`` ya está cubierto por todos
    los datafiles, usando su checkpoint mínimo. Este criterio evita considerar
    aplicado un fichero por el mero hecho de haber sido recibido.
    """

    config = storage.load_config(name)
    timeout = int(config.get("settings", {}).get("ssh_timeout", 20))
    settings = config.get("settings", {})
    primary_redo = oracle.redo_summary(config["primary"], timeout=timeout)
    transferred_redo = oracle.redo_summary(config["standby"], timeout=timeout)
    applied_redo = oracle.redo_summary(
        config["standby"],
        applied_through_datafiles=True,
        timeout=timeout,
    )

    transfer_lag = _lag_minutes(
        primary_redo.get("last_redo_time"),
        transferred_redo.get("last_redo_time"),
    )
    apply_lag = _lag_minutes(
        primary_redo.get("last_redo_time"),
        applied_redo.get("last_redo_time"),
    )
    max_transfer_lag = _lag_threshold(settings, "max_transfer_lag_minutes")
    max_apply_lag = _lag_threshold(settings, "max_apply_lag_minutes")

    primary = {
        "last_archived_redo": primary_redo.get("last_redo_sequence", "UNKNOWN"),
        "last_archived_time": primary_redo.get("last_redo_time", "UNKNOWN"),
        "source": "v$archived_log on primary",
    }
    transfer = {
        "last_transferred_redo": transferred_redo.get("last_redo_sequence", "UNKNOWN"),
        "last_transferred_time": transferred_redo.get("last_redo_time", "UNKNOWN"),
        "transfer_lag": _display_minutes(transfer_lag),
        "source": "v$archived_log on replica",
    }
    apply = {
        "last_applied_redo": applied_redo.get("last_redo_sequence", "UNKNOWN"),
        "last_applied_time": applied_redo.get("last_redo_time", "UNKNOWN"),
        "apply_lag": _display_minutes(apply_lag),
        "source": "v$archived_log limited by minimum datafile checkpoint",
    }
    thresholds = {
        "max_transfer_lag": _display_minutes(max_transfer_lag),
        "max_apply_lag": _display_minutes(max_apply_lag),
    }

    primary_available = primary_redo.get("reachable") == "YES"
    replica_available = (
        transferred_redo.get("reachable") == "YES" and applied_redo.get("reachable") == "YES"
    )
    recommended_action = None
    if not primary_available:
        result = "ERROR"
        message = "Lag cannot be calculated because the primary database is not accessible."
        recommended_action = "Check primary database availability and SSH connectivity."
    elif not replica_available:
        result = "ERROR"
        message = "Lag cannot be calculated because the replica database is not accessible."
        recommended_action = "Check replica database availability and SSH connectivity."
    elif transfer_lag is None or apply_lag is None:
        result = "WARNING"
        message = "Lag cannot be calculated with the available redo timestamps."
        recommended_action = "Check archived redo availability on primary and replica."
    elif transfer_lag > max_transfer_lag and apply_lag > max_apply_lag:
        result = "WARNING"
        message = "Transfer and apply lag exceed configured thresholds."
    elif transfer_lag > max_transfer_lag:
        result = "WARNING"
        message = "Transfer lag exceeds configured threshold."
    elif apply_lag > max_apply_lag:
        result = "WARNING"
        message = "Apply lag exceeds configured threshold."
    else:
        result = "SUCCESS"
        message = "Replica lag is within configured thresholds."

    payload = {
        "configuration": name,
        "calculated_at": audit.utc_now(),
        "primary": primary,
        "transfer": transfer,
        "apply": apply,
        "thresholds": thresholds,
        "result": result,
        "message": message,
    }
    if recommended_action:
        payload["recommended_action"] = recommended_action
    audit.log_event(name, "lag", result, "Consulta de lag ejecutada.", payload)
    return payload


def history(name, limit=20):
    """Consulta el histórico e indica expresamente si existen eventos."""

    storage.load_config(name)
    events = audit.read_history(configuration=name, limit=limit)
    audit.log_event(name, "history", "OK", "Consulta de histórico.")
    message = (
        "Historical events retrieved successfully."
        if events
        else "No historical events are available for this configuration."
    )
    return {
        "result": "OK",
        "configuration": name,
        "events": events,
        "count": len(events),
        "message": message,
    }
