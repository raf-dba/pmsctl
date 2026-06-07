# Piloto minimo pmsctl

Este piloto implementa una parte acotada de la herramienta descrita en el TFG:
configuracion, validacion, estado, lag e historico. No crea, borra, restaura ni
recupera bases de datos. Todas las operaciones contra Oracle son consultas o
comprobaciones no destructivas.

## Requisitos

- Python 3.6.
- Linux en el nodo central y en los nodos Oracle.
- Oracle Database 19c SE2 con `sqlplus` disponible.
- Usuario de sistema operativo con permisos para ejecutar `sqlplus / as sysdba`.
- SSH por clave desde el nodo central hacia la standby.
- Primaria en modo `ARCHIVELOG` para que el lag tenga sentido operativo.

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

No se deben incluir contrasenas en el JSON. El piloto rechaza campos cuyo nombre
parezca contener secretos.

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
- `status` consulta `v$instance`, `v$database` y `v$datafile_header` en primaria
  y standby. `CURRENT SCN` procede de `v$database` y puede ser cero con la base
  montada. `DATAFILE CHECKPOINT SCN MIN` y `DATAFILE CHECKPOINT SCN MAX`
  muestran el intervalo de checkpoints de los datafiles, excluyendo `PDB$SEED`.
- `lag` consulta `v$archived_log` para comparar ultima secuencia archivada en
  primaria y ultima secuencia aplicada en standby.
- `history` muestra eventos registrados en `var/logs/events.jsonl`.

Si Oracle no puede proporcionar un dato, el piloto devuelve `UNKNOWN` en lugar de
inventar un valor.
