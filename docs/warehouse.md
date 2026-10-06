# Warehouse y Power BI

`python -m pipeline.cli warehouse` ejecuta tres archivos SQL
(`src/pipeline/sql/`) en BigQuery. Es ELT: Python mueve y valida, SQL transforma.

| Archivo | Qué crea |
|---------|----------|
| `01_external_tables.sql` | tablas externas `ext_*` sobre el Parquet de `curated/` (solo staging) |
| `02_tables.sql` | tablas nativas tipadas en `dealer_curated`: `ventas` (particionada por fecha y agrupada por concesionaria), `gastos_mensuales`, `objetivos` |
| `03_marts.sql` | vistas de consumo en `dealer_marts`: `dim_concesionaria`, `dim_fecha`, `kpi_diario`, `kpi_mensual` |

Todas las sentencias son `CREATE OR REPLACE`, así que se puede ejecutar cuantas
veces haga falta sin duplicar nada. Cada refresco reconstruye las tablas
completas: con este volumen es lo más simple y seguro. Si crece, se cambia por
`MERGE` sobre la partición del día.

El comando se niega a correr si `curated/` está vacío, porque las tablas externas
necesitan al menos un archivo.

## Qué trae `kpi_mensual`

Por concesionaria y mes: ventas, costo, utilidad bruta, gastos operativos, EBITDA,
utilidad neta, objetivo y las razones `margen_bruto`, `margen_ebitda` y
`cumplimiento` (de 0 a 1).

```
EBITDA         = utilidad bruta - (nómina + renta + marketing + otros gastos)
Utilidad neta  = EBITDA - depreciación - intereses - impuestos
```

## Conectar Power BI

El reporte está en [`docs/powerbi/dashboard.pbix`](powerbi/dashboard.pbix): resumen
ejecutivo, comparativo entre concesionarias y operación diaria. Para refrescarlo
contra tu propio proyecto se necesitan los permisos que se describen abajo.

Obtener datos, Google BigQuery, tu proyecto, dataset `dealer_marts`. Quien abra el
reporte necesita permiso de lectura sobre `dealer_marts` y también sobre
`dealer_curated`, porque las vistas leen de ahí. Relaciona
`kpi_mensual[dealer_name]` con `dim_concesionaria` y `kpi_mensual[mes]` con
`dim_fecha[mes]`.

Las razones no se promedian: se suman los importes y se vuelve a dividir.

```
Ventas          = SUM ( kpi_mensual[ventas] )
Utilidad Bruta  = SUM ( kpi_mensual[utilidad_bruta] )
EBITDA          = SUM ( kpi_mensual[ebitda] )
Utilidad Neta   = SUM ( kpi_mensual[utilidad_neta] )
Margen Bruto %  = DIVIDE ( [Utilidad Bruta], [Ventas] )
Cumplimiento %  = DIVIDE ( [Ventas], SUM ( kpi_mensual[objetivo_ventas] ) )
```

Si más adelante quieres que alguien consulte el reporte sin acceso a
`dealer_curated`, convierte las vistas de `dealer_marts` en vistas autorizadas.
