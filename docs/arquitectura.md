# Arquitectura y decisiones de diseño

Referencia técnica del pipeline. La visión general está en el [README](../README.md);
el warehouse y el modelo semántico, en [warehouse.md](warehouse.md); la
infraestructura, en [despliegue.md](despliegue.md).

## Flujo de datos

```text
API de Kaggle ─► ingesta ─► raw/ ─► simulación + validación ─► curated/ ─► BigQuery ─► Power BI
```

Patrón ELT: Python extrae, limpia, simula y valida; las transformaciones analíticas
y los KPIs se calculan en BigQuery con SQL. Ningún KPI se calcula en Python ni en
el reporte.

### Distribución del data lake

```text
raw/ventas/sale_date=YYYY-MM-DD/ventas.parquet
curated/ventas/sale_date=YYYY-MM-DD/ventas.parquet          # + costo, utilidad_bruta, mes
curated/gastos_mensuales/month=YYYY-MM/gastos.parquet
curated/objetivos/month=YYYY-MM/objetivos.parquet
```

Particionado estilo Hive: una partición por día en ventas y una por mes en las
tablas mensuales. Con backend local las rutas cuelgan de `PIPELINE_DATA_DIR`; con
backend `gcs`, de la raíz del bucket. Los días sin ventas en la fuente no generan
partición (en 2022: 292 particiones de 365 días).

## Comandos

| Comando | Operación |
|---------|-----------|
| `ingest --date D` | descarga la fuente y escribe la partición raw del día `D` |
| `backfill --start A --end B` | `ingest` para cada día del rango |
| `curate --start A [--end B]` | raw → curated: costos simulados por venta y tablas mensuales de los meses afectados |
| `daily [--date D] [--warehouse]` | `ingest` + `curate` del día simulado y, opcionalmente, refresco del warehouse |
| `warehouse` | reconstruye tablas y vistas de BigQuery desde `curated/` ([warehouse.md](warehouse.md)) |

## Configuración

| Variable | Valor por defecto | Función |
|----------|-------------------|---------|
| `PIPELINE_BACKEND` | `local` | `local` (sistema de archivos) o `gcs` (Cloud Storage) |
| `PIPELINE_DATA_DIR` | `data` | raíz del lake con backend local |
| `PIPELINE_BUCKET` | — | bucket del lake con backend `gcs` |
| `PIPELINE_PROJECT` | — | proyecto de GCP; requerido por `warehouse` |
| `PIPELINE_SOURCE` | `kaggle` | `kaggle` (API) o `file` (CSV local) |
| `PIPELINE_KAGGLE_DATASET` | `missionjee/car-sales-report` | dataset de origen |
| `PIPELINE_KAGGLE_FILE` | — | CSV a usar si el dataset contiene varios |
| `PIPELINE_SOURCE_CSV` | `data/source/Car Sales.csv` | ruta del CSV con `PIPELINE_SOURCE=file` |
| `PIPELINE_SIM_YEAR` | `2022` | año del dataset que reproduce `daily` |
| `KAGGLE_API_TOKEN` | — | credencial de Kaggle; en Cloud Run se inyecta desde Secret Manager |

## Contrato de almacenamiento

`storage.py` define un `Protocol` con cuatro operaciones (`write_bytes`,
`read_bytes`, `exists`, `list`) y dos implementaciones:

| Implementación | Escritura | `list(prefix)` |
|----------------|-----------|----------------|
| `LocalStorage` | atómica: archivo `.tmp` + `replace`, nunca deja archivos parciales | recorrido recursivo con semántica de prefijo idéntica a GCS; ignora `.tmp` |
| `GCSStorage` | `upload_from_string` sobre el blob | `list_blobs(prefix=...)` |

El resto del pipeline solo depende del protocolo, así que las pruebas locales
ejercitan la misma lógica que corre contra Cloud Storage. Limitación conocida:
`GCSStorage` no fija `content_type`, por lo que los objetos Parquet quedan
registrados como `text/plain`; BigQuery los lee por formato declarado en la tabla
externa, sin efecto funcional.

## Modelo de simulación

La fuente no trae costos, gastos ni objetivos. `simulate.py` los genera con
funciones puras: cada valor aleatorio es `SHA-256(SEED=42 | claves de negocio)`
mapeado a un uniforme en `[lo, hi)`, sin generadores con estado.

| Variable | Clave del hash | Regla |
|----------|----------------|-------|
| Margen por modelo | `company`, `model` | uniforme 8 %–20 % |
| Variación por venta | `car_id` | ±1 % sobre el margen del modelo |
| Costo | — | `price × (1 − margen − variación)`, redondeado a centavos |
| Nómina / renta / marketing / otros | concepto, concesionaria, mes | fracción de las ventas del mes: 3.0–4.5 %, 1.0–2.0 %, 0.5–1.5 %, 0.5–1.2 % |
| Depreciación / intereses | concepto, concesionaria, mes | 0.3–0.6 % y 0.2–0.8 % de las ventas del mes |
| Impuestos | — | 30 % sobre la utilidad antes de impuestos, con piso en 0 |
| Objetivo de ventas | concesionaria, mes | ventas reales del mes × uniforme 0.90–1.15 |

Consecuencia: reprocesar un día, ejecutar un backfill o cambiar el tamaño del lote
produce exactamente los mismos valores.

## Simulación incremental

El dataset es estático. `daily` calcula el día simulado con `simulated_day`: mismo
día y mes de la fecha real, en `PIPELINE_SIM_YEAR`; el 29 de febrero se mapea al
28 cuando el año simulado no es bisiesto. Así el job programado procesa una
partición nueva cada día y ejercita el diseño incremental (carga diaria, backfill
y recarga sin duplicados).

## Decisiones de diseño

- **Idempotencia:** cada ejecución sobrescribe su partición y toda sentencia de
  BigQuery es `CREATE OR REPLACE`; reprocesar una fecha no duplica filas. Cubierto
  por pruebas.
- **Privacidad en la carga:** `customer_name`, `phone`, `gender` y `annual_income`
  se eliminan al leer la fuente y nunca llegan al lake; una validación de raw
  bloquea el lote si reaparecen.
- **Separación de responsabilidades:** `simulate.py` no hace I/O; `curate.py` lee y
  escribe; `validate.py` decide si un lote avanza.
- **Dependencias inyectadas:** el descargador de Kaggle y el cliente de BigQuery se
  reciben como parámetros, por lo que la suite (68 pruebas) corre sin red ni
  credenciales.
- **Tablas mensuales recalculadas:** gastos y objetivos de un mes se reconstruyen
  con los días curados disponibles, de modo que durante el mes en curso crecen día
  a día.

## Validaciones de calidad

`validate.py` contiene funciones puras que devuelven la lista de incidencias de un
lote. Cualquier incidencia detiene el pipeline antes de escribir: el lote no pasa a
la siguiente capa y la ejecución de Cloud Run termina con error.

| Capa | Reglas |
|------|--------|
| raw (antes de escribir) | columnas obligatorias, nulos, tipos, `price` en (0, 10M], textos en blanco, `car_id` duplicado, ausencia de datos personales |
| curated (antes de escribir) | mismo número de filas que raw, nulos, `0 < costo < price`, `utilidad_bruta = price − costo`, margen entre 5 % y 25 % |
| tablas mensuales | clave concesionaria + mes única, gastos sin negativos ni nulos, `objetivo_ventas > 0`, gastos y objetivos con las mismas claves |

Las reglas están implementadas en pandas, sin dependencias adicionales; la
interfaz (lote → lista de incidencias) admite sustituirlas por un validador
declarativo como `pandera` sin cambiar a quien las invoca.

## Observabilidad

Los comandos registran con `logging` a stderr (nivel INFO): partición escrita y
número de filas, días sin ventas, tablas mensuales generadas, cada sentencia del
warehouse y un resumen por comando. Cloud Run envía stderr a Cloud Logging. Los
registros son texto plano, por lo que Cloud Logging no les asigna severidad; un
formato JSON estructurado permitiría filtrar errores por severidad.
