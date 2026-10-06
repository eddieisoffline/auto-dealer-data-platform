---
title:
  es: "Plataforma de datos para concesionarias en Google Cloud"
  en: "Car Dealership Data Platform on Google Cloud"
slug: "auto-dealer-data-platform"
summary:
  es: "Pipeline automatizado de Kaggle a BigQuery que convierte ventas de concesionarias en KPIs financieros (utilidad bruta, EBITDA, cumplimiento) para Power BI, desplegado en Google Cloud con infraestructura como código y despliegue continuo."
  en: "Automated Kaggle-to-BigQuery pipeline that turns dealership sales into financial KPIs (gross profit, EBITDA, target attainment) for Power BI, deployed on Google Cloud with infrastructure as code and continuous deployment."
tools: ["Python", "pandas", "SQL", "BigQuery", "Cloud Storage", "Cloud Run", "Terraform", "GitHub Actions", "Power BI"]
repo_url: "https://github.com/eddieisoffline/auto-dealer-data-platform"
cover_image: "https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-resumen.png"
featured: true
date: "2026-10-05"
---

:::es
## Problema

En muchas redes de concesionarias, los reportes de desempeño (ventas, utilidad bruta, EBITDA y cumplimiento de objetivos por sucursal) se arman a mano en Excel, tardan semanas en cada cierre y llegan cuando ya no sirven para decidir. Este proyecto construye la alternativa: un flujo automático, reproducible y verificable, de la fuente al tablero, con actualización diaria.

## Arquitectura

```text
API de Kaggle ─► raw/ (Parquet por día) ─► curated/ (Parquet) ─► BigQuery ─► Power BI
                 └──────── Cloud Storage ───────┘
Cloud Scheduler (diario) ─► Cloud Run Job ─► ejecuta el pipeline
```

| Capa | Dónde | Contenido |
|------|-------|-----------|
| Fuente | API de Kaggle | ventas de un dataset público, sin datos personales desde la carga |
| `raw` | Cloud Storage | ventas validadas, un Parquet por día |
| `curated` | Cloud Storage | ventas con costo y utilidad bruta, más gastos y objetivos mensuales |
| Warehouse | BigQuery `dealer_curated` | tablas tipadas; `ventas` particionada por fecha |
| Consumo | BigQuery `dealer_marts` | dimensiones y vistas de KPIs para Power BI |

## Metodología

- **Ingesta:** descarga desde la API de Kaggle, limpieza y una partición Parquet por día. Incluye backfill por rango de fechas. Los datos personales (nombre, teléfono, género, ingreso) se eliminan al cargar y nunca llegan al lake.
- **Curated:** costos, gastos y objetivos mensuales simulados con funciones puras, más la utilidad bruta por venta.
- **Calidad:** validaciones entre capas que detienen el pipeline antes de propagar un lote defectuoso: columnas, nulos, tipos, duplicados, rangos de precio, margen entre 5 % y 25 %, igualdad de filas entre raw y curated y ausencia de datos personales.
- **Warehouse (ELT):** tablas externas sobre el Parquet, tablas nativas tipadas y vistas de consumo (`dim_concesionaria`, `dim_fecha`, `kpi_diario`, `kpi_mensual`). Los KPIs se calculan en SQL, no en Python ni en el reporte:
  - EBITDA = utilidad bruta − (nómina + renta + marketing + otros gastos)
  - Utilidad neta = EBITDA − depreciación − intereses − impuestos
- **Power BI:** medidas DAX que suman importes y después dividen con `DIVIDE`, en lugar de promediar razones.
- **Operación:** Terraform crea el bucket, los datasets, las cuentas de servicio con mínimo privilegio, Secret Manager, Artifact Registry, el Cloud Run Job y Cloud Scheduler. GitHub Actions prueba, valida Terraform y despliega una imagen etiquetada con el SHA de cada commit a `main`.

## Decisiones de diseño

- **Idempotente de punta a punta:** cada ejecución sobrescribe su partición y cada sentencia de BigQuery es `CREATE OR REPLACE`. Correr dos veces el mismo día no duplica filas.
- **Simulación reproducible:** cada valor sintético sale de un hash de su clave de negocio, no de un generador con estado. El orden o el tamaño del lote no cambian el resultado.
- **Mismo código en local y en la nube:** el almacenamiento tiene una interfaz común (`LocalStorage` / `GCSStorage`), así las pruebas locales cubren la lógica que corre en GCP.
- **Sin credenciales en el repositorio:** el token de Kaggle vive en Secret Manager y GitHub se autentica en GCP con Workload Identity Federation, limitado a este repositorio y a la rama `main`.

## Resultados

- **Carga histórica de 2022 en Cloud Run:** 10,645 ventas de 28 concesionarias en 292 días con ventas. Cada paso tarda entre 2 y 3 minutos: backfill 2:12, curate 2:51 y warehouse 2:10.
- **Calidad:** las validaciones pasaron sin incidencias; raw y curated tienen las mismas 10,645 filas.
- **Warehouse:** 6 tablas en `dealer_curated` y 4 vistas en `dealer_marts`, reconstruidas en 10 sentencias SQL. Margen bruto anual de 13.95 % y cumplimiento de objetivos de 97.76 % (cifras sintéticas).
- **CI/CD:** 68 pruebas unitarias sin red ni credenciales; cada push a `main` prueba, valida Terraform y despliega la nueva imagen en el Cloud Run Job en alrededor de un minuto.
- **Reporte:** Power BI con resumen ejecutivo, comparativo entre concesionarias y operación diaria, conectado a `dealer_marts`.

![Resumen ejecutivo en Power BI: KPIs, ventas contra objetivo y cascada de ventas a utilidad neta](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-resumen.png)

![Comparativo entre concesionarias: ranking de ventas y semáforo de cumplimiento](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-sucursales.png)

![Operación diaria: ventas por día con media móvil de 7 días](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-diario.png)

## Evidencia en Google Cloud

Data lake en Cloud Storage con particiones por día (`sale_date=`) y por mes (`month=`):

![Data lake en Cloud Storage con particiones por día y por mes](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/gcs-lake.png)

Tablas y vistas en BigQuery, con una consulta a `kpi_mensual`:

![Tablas y vistas en BigQuery con una consulta a kpi_mensual](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/bigquery-marts.png)

Ejecuciones del Cloud Run Job y logs del refresco del warehouse:

![Historial de ejecuciones del Cloud Run Job](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/cloud-run-job.png)

![Logs del refresco del warehouse: 10 sentencias CREATE OR REPLACE](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/cloud-run-job-logs.png)

CI/CD en GitHub Actions:

![CI/CD en GitHub Actions: test, terraform y deploy en verde](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/ci-verde.png)

## Stack

Python (pandas, pyarrow) · SQL (BigQuery) · Google Cloud (Cloud Storage, BigQuery, Cloud Run Jobs, Cloud Scheduler, Secret Manager, Artifact Registry) · Terraform · Docker · GitHub Actions · Power BI

## Datos

La fuente es el dataset público [Car Sales Report](https://www.kaggle.com/datasets/missionjee/car-sales-report) de Kaggle, que es estático. Las cargas incrementales se **simulan** reproduciendo un día del calendario por ejecución. Costos, gastos y objetivos son **sintéticos** (semilla fija) y no representan datos reales de ninguna empresa.

Documentación técnica: [arquitectura y decisiones](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/arquitectura.md), [warehouse y Power BI](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/warehouse.md) y [despliegue en Google Cloud](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/despliegue.md).
:::

:::en
## Problem

In many dealership networks, performance reports (sales, gross profit, EBITDA, and target attainment per branch) are assembled by hand in Excel. Each close takes weeks, and the numbers arrive too late to support decisions. This project builds the alternative: an automated, reproducible, and verifiable flow from source to dashboard, refreshed daily.

## Architecture

```text
Kaggle API ─► raw/ (daily Parquet) ─► curated/ (Parquet) ─► BigQuery ─► Power BI
              └─────── Cloud Storage ───────┘
Cloud Scheduler (daily) ─► Cloud Run Job ─► runs the pipeline
```

| Layer | Where | Content |
|-------|-------|---------|
| Source | Kaggle API | sales from a public dataset, personal data removed at load time |
| `raw` | Cloud Storage | validated sales, one Parquet file per day |
| `curated` | Cloud Storage | sales with cost and gross profit, plus monthly expenses and targets |
| Warehouse | BigQuery `dealer_curated` | typed tables; `ventas` partitioned by date |
| Consumption | BigQuery `dealer_marts` | dimensions and KPI views for Power BI |

## Methodology

- **Ingestion:** download from the Kaggle API, cleaning, and one Parquet partition per day, with date-range backfill. Personal data (name, phone, gender, income) is dropped at load time and never reaches the lake.
- **Curated:** costs, expenses, and monthly targets simulated with pure functions, plus gross profit per sale.
- **Quality:** cross-layer validations that stop the pipeline before a bad batch propagates: columns, nulls, types, duplicates, price ranges, a 5%–25% margin, equal row counts between raw and curated, and no personal data.
- **Warehouse (ELT):** external tables over Parquet, typed native tables, and consumption views (`dim_concesionaria`, `dim_fecha`, `kpi_diario`, `kpi_mensual`). KPIs are computed in SQL, not in Python or in the report:
  - EBITDA = gross profit − (payroll + rent + marketing + other expenses)
  - Net income = EBITDA − depreciation − interest − taxes
- **Power BI:** DAX measures that sum amounts and then divide with `DIVIDE`, instead of averaging ratios.
- **Operations:** Terraform provisions the bucket, datasets, least-privilege service accounts, Secret Manager, Artifact Registry, the Cloud Run Job, and Cloud Scheduler. GitHub Actions tests, validates Terraform, and deploys an image tagged with the SHA of each commit to `main`.

## Design decisions

- **Idempotent end to end:** each run overwrites its partition and every BigQuery statement is `CREATE OR REPLACE`. Running the same day twice never duplicates rows.
- **Reproducible simulation:** every synthetic value is derived from a hash of its business key, not from a stateful generator. Batch order and size do not change the result.
- **Same code locally and in the cloud:** storage sits behind a common interface (`LocalStorage` / `GCSStorage`), so local tests cover the logic that runs on GCP.
- **No credentials in the repository:** the Kaggle token lives in Secret Manager, and GitHub authenticates to GCP through Workload Identity Federation, restricted to this repository and the `main` branch.

## Results

- **2022 historical load on Cloud Run:** 10,645 sales from 28 dealerships across 292 days with sales. Each step takes 2 to 3 minutes: backfill 2:12, curate 2:51, and warehouse 2:10.
- **Quality:** validations passed with no issues; raw and curated hold the same 10,645 rows.
- **Warehouse:** 6 tables in `dealer_curated` and 4 views in `dealer_marts`, rebuilt by 10 SQL statements. Annual gross margin of 13.95% and target attainment of 97.76% (synthetic figures).
- **CI/CD:** 68 unit tests with no network or credentials; every push to `main` runs the tests, validates Terraform, and deploys the new image to the Cloud Run Job in about a minute.
- **Report:** Power BI with an executive summary, a dealership comparison, and daily operations, connected to `dealer_marts`.

![Power BI executive summary: KPIs, sales versus target, and a waterfall from sales to net income](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-resumen.png)

![Dealership comparison: sales ranking and target attainment traffic light](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-sucursales.png)

![Daily operations: daily sales with a 7-day moving average](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/powerbi-diario.png)

## Evidence on Google Cloud

Cloud Storage data lake with daily (`sale_date=`) and monthly (`month=`) partitions:

![Cloud Storage data lake with daily and monthly partitions](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/gcs-lake.png)

BigQuery tables and views, with a query on `kpi_mensual`:

![BigQuery tables and views with a query on kpi_mensual](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/bigquery-marts.png)

Cloud Run Job executions and warehouse refresh logs:

![Cloud Run Job execution history](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/cloud-run-job.png)

![Warehouse refresh logs: 10 CREATE OR REPLACE statements](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/cloud-run-job-logs.png)

CI/CD on GitHub Actions:

![CI/CD on GitHub Actions: test, terraform, and deploy passing](https://raw.githubusercontent.com/eddieisoffline/auto-dealer-data-platform/main/docs/img/ci-verde.png)

## Stack

Python (pandas, pyarrow) · SQL (BigQuery) · Google Cloud (Cloud Storage, BigQuery, Cloud Run Jobs, Cloud Scheduler, Secret Manager, Artifact Registry) · Terraform · Docker · GitHub Actions · Power BI

## Data

The source is the public [Car Sales Report](https://www.kaggle.com/datasets/missionjee/car-sales-report) dataset on Kaggle, which is static. Incremental loads are **simulated** by replaying one calendar day per run. Costs, expenses, and targets are **synthetic** (fixed seed) and do not represent any real company's data.

Technical documentation (in Spanish): [architecture and decisions](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/arquitectura.md), [warehouse and Power BI](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/warehouse.md), and [Google Cloud deployment](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/despliegue.md).
:::
