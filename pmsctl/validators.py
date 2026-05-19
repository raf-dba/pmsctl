"""Validaciones de entorno para una configuración pmsctl."""

import shlex

from pmsctl import oracle, remote


def _check(name, ok, message, recommended_action=None, details=None):
    """Construye una entrada homogénea de validación."""

    data = {
        "check": name,
        "status": "OK" if ok else "ERROR",
        "message": message,
    }
    if recommended_action and not ok:
        data["recommended_action"] = recommended_action
    if details:
        data["details"] = details
    return data


def validate_node(label, node, timeout=20):
    """Valida conectividad, binarios Oracle, rutas y consulta básica SQL."""

    checks = []
    ping = remote.run(node, "printf PMSCTL_OK", timeout=timeout)
    checks.append(
        _check(
            "%s_CONNECTIVITY" % label.upper(),
            ping.ok and "PMSCTL_OK" in ping.stdout,
            "Conectividad disponible con el nodo %s." % label
            if ping.ok
            else "No se puede ejecutar comandos en el nodo %s." % label,
            "Revise SSH por clave, usuario remoto y conectividad de red.",
            ping.summary() if not ping.ok else None,
        )
    )
    if not (ping.ok and "PMSCTL_OK" in ping.stdout):
        checks.append(
            _check(
                "%s_DEPENDENT_CHECKS" % label.upper(),
                False,
                "No se ejecutan más comprobaciones en %s porque no hay conectividad fiable." % label,
                "Corrija primero la conectividad SSH o local y repita 'pmsctl validate'.",
            )
        )
        return checks

    oracle_home_check = remote.run(
        node,
        "test -d \"$ORACLE_HOME\" && test -x \"$ORACLE_HOME/bin/sqlplus\"",
        timeout=timeout,
    )
    checks.append(
        _check(
            "%s_ORACLE_HOME" % label.upper(),
            oracle_home_check.ok,
            "ORACLE_HOME y sqlplus están disponibles en %s." % label
            if oracle_home_check.ok
            else "ORACLE_HOME o sqlplus no están disponibles en %s." % label,
            "Revise oracle_home, permisos y binarios Oracle en la configuración.",
            oracle_home_check.summary() if not oracle_home_check.ok else None,
        )
    )

    archive_dest = shlex.quote(node.get("archive_dest", ""))
    archive_check = remote.run(node, "test -d %s" % archive_dest, timeout=timeout)
    checks.append(
        _check(
            "%s_ARCHIVE_DEST" % label.upper(),
            archive_check.ok,
            "La ruta de archived redo existe en %s." % label
            if archive_check.ok
            else "La ruta de archived redo no existe o no es accesible en %s." % label,
            "Cree la ruta o corrija archive_dest en la configuración.",
            archive_check.summary() if not archive_check.ok else None,
        )
    )

    status = oracle.database_status(node, timeout=timeout)
    checks.append(
        _check(
            "%s_SQLPLUS_STATUS" % label.upper(),
            status.get("reachable") == "YES",
            "SQLPlus puede consultar la base de datos en %s." % label
            if status.get("reachable") == "YES"
            else "SQLPlus no puede consultar la base de datos en %s." % label,
            "Revise ORACLE_SID, estado de la instancia y permisos del usuario del sistema operativo.",
            status if status.get("reachable") != "YES" else None,
        )
    )

    if label == "primary" and status.get("reachable") == "YES":
        checks.append(
            _check(
                "PRIMARY_ARCHIVELOG",
                status.get("log_mode") == "ARCHIVELOG",
                "La primaria está en modo ARCHIVELOG."
                if status.get("log_mode") == "ARCHIVELOG"
                else "La primaria no está en modo ARCHIVELOG.",
                "Active ARCHIVELOG en la primaria antes de usar recuperación por redo archivado.",
                {"log_mode": status.get("log_mode")},
            )
        )

    return checks


def validate_environment(config):
    """Ejecuta todas las validaciones no destructivas de una configuración."""

    timeout = int(config.get("settings", {}).get("ssh_timeout", 20))
    checks = []
    checks.extend(validate_node("primary", config["primary"], timeout=timeout))
    checks.extend(validate_node("standby", config["standby"], timeout=timeout))
    overall = "OK" if all(item["status"] == "OK" for item in checks) else "ERROR"
    return {"result": overall, "checks": checks}
