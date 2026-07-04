# Piloto minimo pmsctl

Este piloto implementa una parte acotada de la herramienta descrita en el TFG:
configuracion, validacion, estado, lag e historico. No crea, borra, restaura ni
recupera bases de datos. Todas las operaciones contra las bases de datos Oracle son consultas o
comprobaciones no destructivas.

## Requisitos

- Python 3.6.
- Linux en el nodo central y en los nodos Oracle.
- Oracle Database 19c SE2 o superior con `sqlplus` disponible.
- Usuario de sistema operativo con permisos para ejecutar `sqlplus / as sysdba`.
- SSH por clave desde el nodo central hacia la standby.
- Base de datos primaria en modo `ARCHIVELOG`.

## Instalacion basica

Desde la raiz del proyecto:

```bash
chmod +x bin/pmsctl
export PATH="$PWD/bin:$PATH"
```

Opcionalmente puede definirse `PMSCTL_HOME` para guardar configuracion, estado y
logs fuera de la raiz del proyecto.

## Configuracion

Copiar `conf/examples/prod_to_dr.json`, ajustar hosts, usuarios, `ORACLE_HOME`,
`ORACLE_SID` y rutas de archived redo, e importar:

```bash
pmsctl config import mi_config.json
pmsctl config list
pmsctl config show prod_to_dr
```

No se deben incluir contrasenas en el JSON. 

Los ajustes `max_transfer_lag_minutes` y `max_apply_lag_minutes` permiten
definir por separado los umbrales que utiliza el comando `lag`. Si no existen,
se utiliza `lag_warning_minutes`. 

## Comandos principales

```bash
pmsctl validate prod_to_dr
pmsctl status prod_to_dr
pmsctl lag prod_to_dr
pmsctl history prod_to_dr
```

Todos los comandos aceptan salida estructurada:

```bash
pmsctl --json status prod_to_dr
```

## Interpretacion

- `validate` comprueba SSH, rutas, `ORACLE_HOME`, `sqlplus`, consulta basica y
  modo `ARCHIVELOG` en primaria.
- `status` muestra el estado operativo de primaria y replica, el ultimo redo
  archivado, transferido y aplicado, y el ultimo estado valido conocido si un
  nodo no esta disponible.
- `lag` diferencia el retraso de transferencia del retraso de aplicacion. En la
  replica considera aplicado el ultimo archived redo cuyo `NEXT_CHANGE#` esta
  cubierto por el checkpoint minimo de los datafiles.
- `history` muestra eventos registrados en `var/logs/events.jsonl`.

Si Oracle no puede proporcionar un dato, el piloto devuelve `UNKNOWN` en lugar de
inventar un valor.
