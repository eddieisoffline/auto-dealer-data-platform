# CLAUDE.md — auto-dealer-data-platform

Pipeline de datos en GCP: API de Kaggle → raw (Parquet) → curated → BigQuery → Power BI.
Proyecto de portafolio (data engineering). Idioma de docs y comentarios: español. Código e identificadores: inglés.

## Datos: qué es real y qué es sintético
- Fuente real: dataset de Kaggle `missionjee/car-sales-report` (estático). Las cargas incrementales se SIMULAN: `daily` reproduce el mismo día del calendario de `PIPELINE_SIM_YEAR` (2022).
- Costos, gastos y objetivos son SINTÉTICOS (hash SHA-256 de la clave de negocio, SEED=42). Nunca presentarlos como datos reales en docs ni README.
- PII (`customer_name`, `phone`, `gender`, `annual_income`) se elimina al cargar. Nunca escribirla en raw/curated ni en logs.

## Comandos
- Instalar: `pip install -e ".[dev,kaggle]"`
- Pruebas: `pytest` (no requieren red ni credenciales)
- Pipeline: `python -m pipeline.cli {ingest|backfill|curate|daily|warehouse}` (ver docs/arquitectura.md)
- Terraform: `cd infra/terraform && terraform fmt && terraform validate` (el CI comprueba el formato)

## Arquitectura (src/pipeline/)
- `kaggle_source.py` descarga · `ingest.py` carga/limpia/particiona raw · `simulate.py` funciones puras · `curate.py` raw→curated · `validate.py` calidad · `warehouse.py` + `sql/` BigQuery · `storage.py` Local/GCS · `daily.py`, `cli.py`.
- Layout del lake: `raw/ventas/sale_date=YYYY-MM-DD/`, `curated/ventas/...`, `curated/gastos_mensuales/month=.../`, `curated/objetivos/month=.../`.
- Python mueve y valida; SQL (BigQuery) calcula KPIs. No mover KPIs a Python ni a Power BI.

## Reglas que no se rompen
- Idempotencia: cada ejecución sobrescribe su partición; todo SQL es `CREATE OR REPLACE`. Correr dos veces no duplica filas.
- `simulate.py` sin I/O y sin generadores con estado (nada de `random` global); mismo resultado en cualquier orden o tamaño de lote.
- Las validaciones (`validate.py`) detienen el pipeline; no convertirlas en warnings. Límites actuales: price (0, 10M], margen 5%–25%.
- Mismo código en local y nube: usar la interfaz de `storage.py`, no `open()`/`google.cloud.storage` directo en la lógica.
- Inyectar el descargador de Kaggle y el cliente de BigQuery para que las pruebas no usen red.
- Secretos: token de Kaggle solo en Secret Manager / `KAGGLE_API_TOKEN`. Nunca en el repo, tfvars ni estado de Terraform.
- Fórmulas: EBITDA = utilidad_bruta − (nómina + renta + marketing + otros_gastos); utilidad_neta = EBITDA − depreciación − intereses − impuestos (TAX_RATE=0.30). En Power BI se suman importes y luego `DIVIDE` (no promediar razones).

## Estado verificado (no afirmar más de esto)
- CI en GitHub Actions en verde (2026-10-05): 68 pruebas con pandas 3.0.6 y pyarrow 25.0.1 reales, y `terraform fmt -check` + `validate` (proveedor google 6.50). Kaggle real, SQL en BigQuery y `terraform apply` NO se han ejecutado todavía. Actualizar la tabla "Estado" del README solo con lo medido.
- Pendiente del autor: aplicar Terraform, subir token a Secret Manager, correr el pipeline, capturas (docs/img/README.md), cifras medidas.

## Portafolio
- `case-study.md` es la única fuente que publica el backend del portafolio (sincroniza los `.md` del repo y omite los que no tienen frontmatter `title`/`slug`). `README.md` y `docs/*.md` no llevan frontmatter.
- Cuerpo bilingüe en bloques `:::es` / `:::en` con las mismas secciones; mantener ambos idiomas sincronizados.
- El backend renderiza con HTML desactivado: nada de HTML crudo, comentarios `<!-- -->` ni Mermaid (saldrían como texto o código). Enlaces e imágenes con URL absoluta de GitHub (imágenes: `blob/main/...?raw=true`).
- "Resultados" solo con lo verificado (ver "Estado verificado"). Pasar a `featured: true` y conectar el webhook del portafolio cuando haya capturas y cifras medidas.

## Al hacer cambios
- Si cambias columnas, actualiza validaciones, SQL y docs/arquitectura.md juntos.
- Cada commit: pruebas en verde antes de proponer push a `main` (el deploy es automático).
