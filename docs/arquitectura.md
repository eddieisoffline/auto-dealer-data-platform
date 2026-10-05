# Arquitectura y decisiones de diseño

Documento de referencia. La visión general está en el [README](../README.md).

## Flujo de datos

```
API de Kaggle ─► ingesta ─► raw/ ─► simulación + validación ─► curated/ ─► BigQuery ─► Power BI
```

Python se encarga de mover, limpiar y validar. Los KPIs (utilidad bruta, EBITDA,
utilidad neta, cumplimiento) se calculan en BigQuery con SQL: es un enfoque ELT.

### Distribución en el data lake

```
raw/ventas/sale_date=YYYY-MM-DD/ventas.parquet
curated/ventas/sale_date=YYYY-MM-DD/ventas.parquet          # con costo y utilidad_bruta
curated/gastos_mensuales/month=YYYY-MM/gastos.parquet
curated/objetivos/month=YYYY-MM/objetivos.parquet
```

En local cuelgan de `data/`; en la nube, de la raíz del bucket.

## Comandos

| Comando | Qué hace |
|---------|----------|
| `ingest --date D` | descarga la fuente y escribe la partición raw de un día |
| `backfill --start A --end B` | lo mismo para un rango de días |
| `curate --start A [--end B]` | raw a curated: costos simulados y tablas mensuales |
| `daily [--date D] [--warehouse]` | ingesta + curated del día simulado y, opcionalmente, refresco de BigQuery |
| `warehouse` | refresca BigQuery desde `curated/` (ver [warehouse](warehouse.md)) |

## Configuración (variables de entorno)

| Variable | Por defecto | Para qué sirve |
|----------|-------------|----------------|
| `PIPELINE_BACKEND` | `local` | `local` (carpeta) o `gcs` (Cloud Storage) |
| `PIPELINE_DATA_DIR` | `data` | raíz del lake con backend local |
| `PIPELINE_BUCKET` | vacío | bucket del lake con backend `gcs` |
| `PIPELINE_PROJECT` | vacío | proyecto de GCP, necesario para el warehouse |
| `PIPELINE_SOURCE` | `kaggle` | `kaggle` (API) o `file` (CSV local, sin conexión) |
| `PIPELINE_KAGGLE_DATASET` | `missionjee/car-sales-report` | dataset a descargar |
| `PIPELINE_KAGGLE_FILE` | vacío | nombre del CSV si el dataset trae varios |
| `PIPELINE_SOURCE_CSV` | `data/source/Car Sales.csv` | ruta del CSV con `PIPELINE_SOURCE=file` |
| `PIPELINE_SIM_YEAR` | `2022` | año del dataset que `daily` reproduce |
| `KAGGLE_API_TOKEN` | vacío | credencial de Kaggle (en la nube viene de Secret Manager) |

## Decisiones de diseño

- **Idempotencia:** cada ejecución sobrescribe su partición. Correr dos veces la
  misma fecha no duplica filas, y en BigQuery todas las sentencias son
  `CREATE OR REPLACE`. Hay pruebas para ello.
- **Fuente estática, carga incremental simulada:** el dataset de Kaggle no
  cambia, así que cada día `daily` reproduce el mismo día del calendario del año
  `PIPELINE_SIM_YEAR`. Así el job programado siempre trae datos nuevos y se puede
  probar el diseño incremental (carga diaria, backfill, recarga sin duplicar).
- **Privacidad desde el origen:** nombre, teléfono, género e ingreso del cliente
  se eliminan al cargar la fuente y nunca llegan al lake. Una validación
  comprueba que no reaparezcan.
- **Simulación reproducible:** cada valor sintético sale de un hash estable de su
  clave de negocio (modelo, venta, concesionaria y mes), no de un generador con
  estado. Procesar un día solo, en lote o en otro orden da exactamente los mismos
  números.
- **Simulación separada de la limpieza:** `simulate.py` son funciones puras sin
  I/O; `curate.py` se ocupa de leer y escribir.
- **Mismo código en local y en la nube:** `LocalStorage` y `GCSStorage` comparten
  interfaz, así las pruebas locales cubren la lógica que corre en GCP.
- **Pruebas sin red ni credenciales:** la descarga de Kaggle y el cliente de
  BigQuery se inyectan, y las pruebas usan sustitutos.
- **Tablas mensuales:** gastos y objetivos de un mes se recalculan con los días
  curados disponibles, así que durante el mes en curso crecen día a día.
- **Escritura atómica** en local: se escribe a un temporal y se renombra.

## Validaciones de calidad

`validate.py` son funciones puras que devuelven una lista de incidencias. Si hay
alguna, el pipeline se detiene y **el lote no pasa a la siguiente capa**. En
Cloud Run la ejecución falla y queda en los logs.

| Capa | Qué comprueba |
|------|---------------|
| raw (antes de escribir) | columnas obligatorias, nulos, tipos, `price` en (0, 10M], textos en blanco, `car_id` duplicado, **ausencia de datos personales** |
| curated (antes de escribir) | mismo número de filas que raw, nulos, `0 < costo < price`, `utilidad_bruta = price - costo`, margen entre 5% y 25% |
| tablas mensuales | clave dealer+mes única, gastos sin negativos ni nulos, `objetivo_ventas > 0`, gastos y objetivos cubren las mismas claves |

Las reglas están escritas en pandas puro, sin dependencias extra. Si más adelante
prefieres un esquema declarativo, `pandera` encaja en el mismo lugar.
