# Warehouse y modelo semántico

Capa analítica en BigQuery (`dealer_curated` y `dealer_marts`) y modelo semántico
del reporte de Power BI. El pipeline que alimenta estas tablas está descrito en
[arquitectura.md](arquitectura.md).

## Ejecución del SQL

`python -m pipeline.cli warehouse` (`warehouse.py`) ejecuta tres archivos de
`src/pipeline/sql/`, empaquetados con el módulo, en este orden:

| Archivo | Objetos |
|---------|---------|
| `01_external_tables.sql` | tablas externas `ext_ventas`, `ext_gastos_mensuales`, `ext_objetivos` sobre `gs://<bucket>/curated/<tabla>/*` (Parquet) |
| `02_tables.sql` | tablas nativas tipadas en `dealer_curated` |
| `03_marts.sql` | vistas de consumo en `dealer_marts` |

Cada archivo se procesa con `string.Template.substitute(project=..., bucket=...)`:
un marcador sin valor provoca un error en vez de SQL inválido. El texto se divide
en sentencias por `;` y las 10 sentencias resultantes se ejecutan en serie,
esperando el resultado de cada una. El comando exige `PIPELINE_BACKEND=gcs`,
`PIPELINE_PROJECT` y `PIPELINE_BUCKET`, y aborta si `curated/` no contiene
archivos, porque una tabla externa sin objetos que coincidan con su URI falla al
crearse. El cliente de BigQuery se inyecta, lo que permite probar la generación y
el orden de las sentencias sin red.

## Diseño físico

Todas las sentencias son `CREATE OR REPLACE`: cada refresco reconstruye las tablas
completas a partir del lake, por lo que el warehouse es una función determinista de
`curated/` y reejecutarlo no duplica filas. Con el volumen actual (10,645 ventas)
las 10 sentencias de la reconstrucción completa se ejecutan en unos 16 segundos;
el camino de escalado es `MERGE` sobre la partición del día.

| Objeto | Tipo | Diseño |
|--------|------|--------|
| `dealer_curated.ext_*` | tabla externa | staging sin almacenamiento propio; se recrea en cada refresco |
| `dealer_curated.ventas` | tabla | `PARTITION BY fecha` (diaria), `CLUSTER BY dealer_name`; 10,645 filas |
| `dealer_curated.gastos_mensuales` | tabla | una fila por concesionaria y mes; 336 filas |
| `dealer_curated.objetivos` | tabla | una fila por concesionaria y mes; 336 filas |
| `dealer_marts.*` | vista | lógica de KPIs sin materializar |

Los importes se tipan como `NUMERIC` (decimal exacto), no como `FLOAT64`, para que
las sumas monetarias no acumulen error de punto flotante.

### Esquemas

`dealer_curated.ventas`

| Columna | Tipo | Origen |
|---------|------|--------|
| `car_id` | STRING | identificador de la venta |
| `fecha` | DATE | fecha de la venta; columna de partición |
| `mes` | DATE | primer día del mes de la venta |
| `dealer_name` | STRING | concesionaria; columna de clustering |
| `dealer_region` | STRING | región de la concesionaria |
| `company`, `model` | STRING | marca y modelo |
| `precio` | NUMERIC | `price` de la fuente |
| `costo` | NUMERIC | costo simulado |
| `utilidad_bruta` | NUMERIC | `precio − costo` |

`dealer_curated.gastos_mensuales`: `dealer_name` STRING, `mes` DATE y los importes
NUMERIC `nomina`, `renta`, `marketing`, `otros_gastos`, `depreciacion`,
`intereses` e `impuestos`.

`dealer_curated.objetivos`: `dealer_name` STRING, `mes` DATE y `objetivo_ventas`
NUMERIC.

## Vistas de consumo

| Vista | Grano | Contenido |
|-------|-------|-----------|
| `dim_concesionaria` | concesionaria | `dealer_name`, `region` |
| `dim_fecha` | día | `fecha`, `mes`, `anio`, `mes_numero`, `anio_mes`; generada con `GENERATE_DATE_ARRAY` entre la primera y la última venta, sin huecos |
| `kpi_diario` | fecha × concesionaria | `num_ventas`, `ventas`, `costo`, `utilidad_bruta` |
| `kpi_mensual` | mes × concesionaria | importes de ventas, gastos (`LEFT JOIN` a `gastos_mensuales` y `objetivos` por concesionaria y mes), resultados y razones |

`dim_fecha` es continua aunque haya días sin ventas (73 en 2022), por lo que las
series temporales y las ventanas móviles del reporte operan sobre un calendario
completo y no sobre las fechas con ventas.

## Definición de KPIs

Calculados en `kpi_mensual`; las razones van de 0 a 1 y usan `SAFE_DIVIDE`, que
devuelve `NULL` en lugar de error si el denominador es cero.

| KPI | Definición |
|-----|-----------|
| `opex` | `nomina + renta + marketing + otros_gastos` |
| `ebitda` | `utilidad_bruta − opex` |
| `utilidad_neta` | `utilidad_bruta − opex − depreciacion − intereses − impuestos` |
| `ticket_promedio` | `ventas / num_ventas` |
| `margen_bruto` | `utilidad_bruta / ventas` |
| `margen_ebitda` | `(utilidad_bruta − opex) / ventas` |
| `cumplimiento` | `ventas / objetivo_ventas` |

Las razones de la vista son válidas solo al grano mes × concesionaria. Para
cualquier agregación superior (varias concesionarias, varios meses) se suman los
importes y se vuelve a dividir; promediar razones daría el mismo peso a una
concesionaria pequeña que a una grande.

## Modelo semántico (Power BI)

El reporte se versiona como proyecto de Power BI (PBIP) en `docs/powerbi/`:

| Artefacto | Contenido |
|-----------|-----------|
| `dashboard.pbip` | punto de entrada del proyecto |
| `dashboard.SemanticModel/definition/` | modelo en TMDL: tablas, relaciones, medidas DAX y consultas M; fuente de verdad del modelo |
| `dashboard.Report/definition/` | páginas y visuales en JSON (formato PBIR) |
| `dashboard.pbix` | copia binaria con los datos importados, para abrir el reporte sin acceso a BigQuery |

La caché local del modelo (`.pbi/cache.abf`) y la configuración local
(`.pbi/localSettings.json`) no se versionan.

### Origen y almacenamiento

Las cuatro tablas de BigQuery se cargan en modo **Import** con el conector
`GoogleBigQuery.Database` (implementación 2.0), leyendo las vistas de
`dealer_marts`. El proyecto de origen es un parámetro de Power Query
(`ProyectoGCP`, en `expressions.tmdl`); las consultas no contienen el ID del
proyecto y el mismo modelo puede apuntar a otro entorno cambiando el parámetro.

| Tabla | Origen | Rol |
|-------|--------|-----|
| `kpi_mensual` | vista `kpi_mensual` | hechos, grano mes × concesionaria |
| `kpi_diario` | vista `kpi_diario` | hechos, grano día × concesionaria |
| `dim_concesionaria` | vista `dim_concesionaria` | dimensión de concesionaria y región |
| `dim_fecha` | vista `dim_fecha` | dimensión de calendario diaria y continua |
| `DimMes` | tabla calculada: `DISTINCT ( SELECTCOLUMNS ( dim_fecha, "mes", dim_fecha[mes] ) )` | dimensión de mes compartida por ambos granos |
| `CascadaPasos` | tabla calculada con `DATATABLE` | pasos del gráfico de cascada; desconectada |
| `kpis` | consulta vacía | contenedor de las 42 medidas |

### Relaciones

Todas son muchos a uno con filtrado en una sola dirección:

| Desde (muchos) | Hacia (uno) |
|----------------|-------------|
| `kpi_mensual[mes]` | `DimMes[mes]` |
| `kpi_mensual[dealer_name]` | `dim_concesionaria[dealer_name]` |
| `kpi_diario[fecha]` | `dim_fecha[fecha]` |
| `kpi_diario[dealer_name]` | `dim_concesionaria[dealer_name]` |
| `dim_fecha[mes]` | `DimMes[mes]` |

`DimMes` es el punto común de los dos granos: un filtro de mes llega a
`kpi_mensual` directamente y a `kpi_diario` a través de `dim_fecha` (copo de
nieve), y `dim_concesionaria` filtra ambas tablas de hechos. Así, los
segmentadores de mes, región y concesionaria de cada página afectan por igual a
los visuales mensuales y a los diarios.

### Medidas

Las medidas de importe suman columnas aditivas; las razones se calculan con
`DIVIDE` sobre importes ya agregados, de modo que cualquier nivel de agregación da
el valor correcto.

| Grupo | Medidas | Definición |
|-------|---------|-----------|
| Importes mensuales (8) | `Ventas`, `Costo`, `Utilidad Bruta`, `Gastos Operativos`, `EBITDA`, `Utilidad Neta`, `Num Ventas`, `Objetivo Ventas` | `SUM` de la columna correspondiente de `kpi_mensual` |
| Razones y brechas (7) | `Margen Bruto %`, `Margen EBITDA %`, `Margen Neto %`, `Ticket Promedio`, `Cumplimiento %`, `Brecha vs Objetivo`, `pp vs objetivo` | `DIVIDE ( [Utilidad Bruta], [Ventas] )`, `DIVIDE ( [EBITDA], [Ventas] )`, `DIVIDE ( [Utilidad Neta], [Ventas] )`, `DIVIDE ( [Ventas], [Num Ventas] )`, `DIVIDE ( [Ventas], SUM ( kpi_mensual[objetivo_ventas] ) )`, `[Ventas] - [Objetivo Ventas]`, `[Cumplimiento %] - 1` |
| Grano diario (5) | `Ventas Día`, `Costo Día`, `Utilidad Bruta Día`, `Num Ventas Día`, `Margen Bruto Día %` | `SUM` sobre `kpi_diario`; el margen con `DIVIDE` |
| Inteligencia de tiempo (3) | `Ventas Mes Anterior`, `Ventas vs Mes Anterior %`, `Ventas Media Móvil 7d` | ver abajo |
| Cascada (6) | `Monto Paso`, `Nivel Paso`, `Cascada Base`, `Cascada Baja`, `Cascada Total`, `maximo eje cascada` | ver abajo |
| Ranking (2) | `Ventas Máx Contexto`, `Es Top Ventas` | `MAXX ( ALLSELECTED ( dim_concesionaria[dealer_name] ), [Ventas] )` y comparación con `[Ventas]` |
| Formato condicional (11) | `Color …`, `Fondo Top Ventas` | códigos de color calculados con `SWITCH ( TRUE (), … )` |

**Mes anterior.** Se desplaza el mes con `EDATE` sobre `DimMes`, reemplazando el
filtro de mes del contexto:

```dax
Ventas Mes Anterior =
VAR m = MAX ( DimMes[mes] )
RETURN
    CALCULATE ( [Ventas], FILTER ( ALL ( DimMes[mes] ), DimMes[mes] = EDATE ( m, -1 ) ) )

Ventas vs Mes Anterior % =
DIVIDE ( [Ventas] - [Ventas Mes Anterior], [Ventas Mes Anterior] )
```

**Media móvil de 7 días.** Ventana de 7 días de calendario que termina en la fecha
del contexto. `ALL ( DimMes )` retira el filtro del segmentador de mes para que
la ventana de los primeros días del mes incluya los últimos días del mes anterior.
El divisor es 7 constante: sobre el calendario continuo de `dim_fecha`, los días
sin ventas cuentan como cero.

```dax
Ventas Media Móvil 7d =
VAR fin = MAX ( dim_fecha[fecha] )
VAR ventana =
    FILTER ( ALL ( dim_fecha[fecha] ), dim_fecha[fecha] > fin - 7 && dim_fecha[fecha] <= fin )
RETURN
    DIVIDE ( CALCULATE ( [Ventas Día], ventana, ALL ( DimMes ) ), 7 )
```

**Cascada de ventas a utilidad neta.** `CascadaPasos` define nueve pasos
ordenados (`Orden` 1–9), cada uno de tipo `Total` (Ventas, Utilidad bruta, EBITDA,
Utilidad neta) o `Baja` (Costo de ventas, Gastos operativos, Depreciación,
Intereses, Impuestos). El visual es un gráfico de columnas apiladas sobre
`CascadaPasos[Paso]`:

- `Nivel Paso` devuelve el nivel acumulado tras cada paso (por ejemplo,
  `[EBITDA] - depreciación - intereses` en el paso 7) y `Monto Paso` el importe
  que resta cada `Baja`.
- `Cascada Base` (`Nivel Paso` en los pasos `Baja`) es el segmento inferior, con
  transparencia del 100 % y sin etiquetas, que eleva cada bajada a su altura;
  `Cascada Baja` (`Monto Paso`, en rojo) es el segmento visible apilado encima;
  `Cascada Total` (en azul) dibuja las columnas de subtotal.
- `maximo eje cascada` (`[Cascada Total] * 1.1`) se enlaza al máximo del eje de
  valores para dejar margen a las etiquetas.

Como todos los niveles derivan de las mismas medidas de importe, la cascada
responde a los segmentadores de mes, región y concesionaria.

**Formato condicional.** El semáforo de cumplimiento usa umbrales fijos:

```dax
Color Cumplimiento =
SWITCH (
    TRUE (),
    ISBLANK ( [Cumplimiento %] ), BLANK (),
    [Cumplimiento %] >= 1,    "#2E7D32",
    [Cumplimiento %] >= 0.9,  "#F9A825",
    "#C62828"
)
```

Los demás colores siguen el mismo patrón por signo (negativo en rojo, positivo en
verde). `Color Fuente Cumplimiento` ajusta el color del texto al fondo para
mantener el contraste, y `Es Top Ventas` resalta la concesionaria con más ventas
dentro de la selección actual (`ALLSELECTED`).

### Páginas

| Página | Visuales |
|--------|----------|
| Resumen ejecutivo | tarjetas de Ventas, Utilidad Bruta, EBITDA, Utilidad Neta y Cumplimiento % con indicadores secundarios (variación contra el mes anterior, márgenes y brecha contra el objetivo); combinado de ventas contra objetivo y cumplimiento por mes; cascada de ventas a utilidad neta; márgenes bruto y EBITDA por mes |
| Concesionarias | ranking de ventas con la concesionaria líder resaltada; cumplimiento por concesionaria con semáforo; matriz de detalle con ventas, utilidad bruta, EBITDA, márgenes, cumplimiento y utilidad neta |
| Operación diaria | tarjetas de unidades, ticket promedio y utilidad bruta; combinado de ventas por día y media móvil de 7 días; tabla de detalle por fecha y concesionaria |

Cada página tiene segmentadores de mes, región y concesionaria sincronizados entre
páginas (grupos de sincronización), de modo que una selección se conserva al
navegar.

## Control de acceso

Las vistas de `dealer_marts` leen de `dealer_curated`, así que un lector necesita
`roles/bigquery.dataViewer` en ambos datasets, además de `roles/bigquery.jobUser`
en un proyecto para ejecutar consultas. Convertir las vistas de `dealer_marts` en
vistas autorizadas sobre `dealer_curated` permitiría restringir a los lectores al
dataset de consumo.
