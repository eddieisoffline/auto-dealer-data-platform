---
title:
  es: "Plataforma de datos para concesionarias en Google Cloud"
  en: "Car Dealership Data Platform on Google Cloud"
slug: "auto-dealer-data-platform"
summary:
  es: "Pipeline automatizado de Kaggle a BigQuery que convierte ventas de concesionarias en KPIs financieros (utilidad bruta, EBITDA, cumplimiento) listos para Power BI, con infraestructura como código y despliegue continuo."
  en: "Automated Kaggle-to-BigQuery pipeline that turns dealership sales into financial KPIs (gross profit, EBITDA, target attainment) ready for Power BI, with infrastructure as code and continuous deployment."
tools: ["Python", "pandas", "SQL", "BigQuery", "Cloud Storage", "Cloud Run", "Terraform", "GitHub Actions", "Power BI"]
repo_url: "https://github.com/eddieisoffline/auto-dealer-data-platform"
featured: false
date: "2026-10-04"
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

- Pipeline completo en código: ingesta, curated, validaciones y refresco del warehouse, con línea de comandos para carga diaria y backfill.
- 68 pruebas unitarias que corren sin red ni credenciales, gracias a la inyección del descargador de Kaggle y del cliente de BigQuery.
- Infraestructura de GCP completa como código en Terraform y CI/CD sin llaves guardadas.
- Modelo de KPIs financieros en SQL listo para conectar Power BI.

La ejecución en Google Cloud y el reporte de Power BI son el siguiente paso; este caso se actualizará con capturas y cifras medidas.

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

- Complete pipeline in code: ingestion, curated layer, validations, and warehouse refresh, with a CLI for daily loads and backfills.
- 68 unit tests that run without network or credentials, thanks to injecting the Kaggle downloader and the BigQuery client.
- Full GCP infrastructure as code in Terraform, and CI/CD with no stored keys.
- SQL model of financial KPIs ready to connect to Power BI.

Running the pipeline on Google Cloud and building the Power BI report are the next steps; this case study will be updated with screenshots and measured figures.

## Stack

Python (pandas, pyarrow) · SQL (BigQuery) · Google Cloud (Cloud Storage, BigQuery, Cloud Run Jobs, Cloud Scheduler, Secret Manager, Artifact Registry) · Terraform · Docker · GitHub Actions · Power BI

## Data

The source is the public [Car Sales Report](https://www.kaggle.com/datasets/missionjee/car-sales-report) dataset on Kaggle, which is static. Incremental loads are **simulated** by replaying one calendar day per run. Costs, expenses, and targets are **synthetic** (fixed seed) and do not represent any real company's data.

Technical documentation (in Spanish): [architecture and decisions](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/arquitectura.md), [warehouse and Power BI](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/warehouse.md), and [Google Cloud deployment](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/despliegue.md).
:::
