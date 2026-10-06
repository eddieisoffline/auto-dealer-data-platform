# Infraestructura y despliegue

Toda la infraestructura está definida en `infra/terraform/` (proveedor
`hashicorp/google` ~> 6.0, versión fijada en `.terraform.lock.hcl`). Ninguna
credencial vive en el repositorio, en las variables de Terraform ni en su estado.

## Inventario de recursos

| Recurso | Nombre | Configuración |
|---------|--------|---------------|
| Cloud Storage | `<proyecto>-dealer-lake` | `us-central1`, acceso uniforme, public access prevention `enforced`, versionado de objetos; las versiones no vigentes se eliminan a los 7 días |
| BigQuery | `dealer_curated`, `dealer_marts` | multirregión `US`; `delete_contents_on_destroy` controlado por `force_destroy` |
| Secret Manager | `kaggle-api-token` | replicación automática; Terraform crea solo el contenedor, el valor se agrega como versión fuera de Terraform |
| Artifact Registry | `pipeline` (Docker) | `us-central1`; política de limpieza: KEEP de las `images_to_keep` versiones más recientes (5) y DELETE de las de más de 1 día; KEEP tiene precedencia |
| Cloud Run Job | `dealer-pipeline` | 1 vCPU, 1 GiB, timeout 1800 s, 1 reintento; argumentos por defecto `daily --warehouse`; `KAGGLE_API_TOKEN` desde Secret Manager (`latest`) |
| Cloud Scheduler | `dealer-pipeline-daily` | `0 6 * * *` en `America/Mexico_City`; POST autenticado con OAuth a la API `jobs/<job>:run`; `attempt_deadline` 320 s, 1 reintento |
| Workload Identity | pool `github`, proveedor `github` | emisor `https://token.actions.githubusercontent.com` |
| Presupuesto | `dealer-platform-<proyecto>` | monto mensual configurable con umbrales de 50 %, 90 % y 100 %; opcional (`billing_account_id`) |

El job y el Scheduler se crean solo con `deploy_job = true`, porque el job exige
que la imagen y el secreto existan al crearse.

## Identidades y permisos

Tres cuentas de servicio con permisos acotados al recurso que usan:

| Cuenta | Rol | Alcance |
|--------|-----|---------|
| `dealer-pipeline-runner` (ejecuta el job) | `roles/storage.objectAdmin` | bucket del lake |
| | `roles/bigquery.dataEditor` | datasets `dealer_curated` y `dealer_marts` |
| | `roles/bigquery.jobUser` | proyecto (requerido para ejecutar consultas) |
| | `roles/secretmanager.secretAccessor` | secreto `kaggle-api-token` |
| `dealer-pipeline-sched` (Scheduler) | `roles/run.invoker` | job `dealer-pipeline` |
| `dealer-pipeline-deployer` (GitHub Actions) | `roles/artifactregistry.writer` | repositorio `pipeline` |
| | `roles/run.developer` | job `dealer-pipeline` |
| | `roles/iam.serviceAccountUser` | cuenta `dealer-pipeline-runner` (para actualizar un job que corre con ella) |
| principal federado del repositorio | `roles/iam.workloadIdentityUser` | cuenta `dealer-pipeline-deployer` |

### Federación de identidad con GitHub

GitHub Actions se autentica con un token OIDC de corta duración; no existen llaves
de cuenta de servicio. El proveedor mapea `google.subject`, `attribute.repository`
y `attribute.ref` desde el token y aplica la condición:

```text
assertion.repository == "eddieisoffline/auto-dealer-data-platform"
  && assertion.ref == "refs/heads/main"
```

Solo los workflows de este repositorio en la rama `main` pueden suplantar a la
cuenta `deployer`, y esa cuenta solo puede publicar imágenes y actualizar el job.

### Proveedor y quota project

El proveedor declara `user_project_override = true` y `billing_project`. Con
credenciales de usuario (Application Default Credentials), APIs como
`billingbudgets.googleapis.com` exigen un quota project explícito; sin esa
configuración, la llamada se factura al proyecto del cliente OAuth de gcloud y
falla con 403. Como consecuencia, `cloudresourcemanager.googleapis.com` debe estar
habilitada en el proyecto antes del primer `plan`, porque Terraform la usa para
leer el proyecto y el estado de sus APIs.

## CI/CD

`.github/workflows/ci.yml` corre en cada push y pull request:

| Job | Contenido | Condición |
|-----|-----------|-----------|
| `test` | Python 3.12, `pip install -e ".[dev]"`, `pytest` | siempre |
| `terraform` | `fmt -check`, `init -backend=false`, `validate` | siempre |
| `deploy` | autenticación por WIF, `docker build`, push a Artifact Registry con el SHA del commit como etiqueta, `gcloud run jobs update` | después de `test` y `terraform`, solo en push a `main` y si existe la variable `GCP_WORKLOAD_IDENTITY_PROVIDER` |

Permisos del workflow: `contents: read` por defecto; `deploy` añade
`id-token: write` para emitir el token OIDC. `deploy` usa un grupo de concurrencia
sin cancelación, para que dos despliegues no se pisen.

Terraform declara `ignore_changes` sobre la imagen del job: después de la creación,
la imagen la gestiona exclusivamente el CI y un `terraform apply` posterior no
revierte un despliegue. El rollback consiste en actualizar el job a la etiqueta de
un commit anterior que siga dentro de las `images_to_keep` conservadas:

```bash
gcloud run jobs update dealer-pipeline --region us-central1 \
  --image us-central1-docker.pkg.dev/<proyecto>/pipeline/pipeline:<sha>
```

## Bootstrap

El despliegue inicial se hace en tres fases, porque el job depende de recursos que
Terraform no puede poblar: la imagen y el valor del secreto.

```bash
# Prerrequisitos: ADC con quota project y Cloud Resource Manager habilitada
gcloud auth application-default login
gcloud auth application-default set-quota-project <proyecto>
gcloud services enable cloudresourcemanager.googleapis.com --project <proyecto>

# Fase 1: APIs, lake, datasets, secreto, registro, cuentas de servicio y WIF
cd infra/terraform
terraform init
terraform apply                                   # deploy_job = false

# Fase 2: valor del secreto e imagen inicial
printf '%s' "$KAGGLE_API_TOKEN" | \
  gcloud secrets versions add kaggle-api-token --data-file=- --project <proyecto>
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t us-central1-docker.pkg.dev/<proyecto>/pipeline/pipeline:0.1.0 ../..
docker push us-central1-docker.pkg.dev/<proyecto>/pipeline/pipeline:0.1.0

# Fase 3: job y Scheduler (deploy_job = true e image en terraform.tfvars)
terraform apply
```

`deploy_job` e `image` se fijan en `terraform.tfvars` y no por `-var`, para que un
`apply` posterior sin argumentos no planifique la eliminación del job. Las cuatro
variables del repositorio que consume el job `deploy` (`GCP_PROJECT_ID`,
`GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SA`) salen de los
outputs de Terraform y no son secretos.

Carga histórica (el timeout de 30 min por ejecución cubre un año completo):

```bash
gcloud run jobs execute dealer-pipeline --region us-central1 --wait \
  --args="backfill,--start,2022-01-01,--end,2022-12-31"
gcloud run jobs execute dealer-pipeline --region us-central1 --wait \
  --args="curate,--start,2022-01-01,--end,2022-12-31"
gcloud run jobs execute dealer-pipeline --region us-central1 --wait --args="warehouse"
```

A partir de ahí, el Scheduler ejecuta `daily --warehouse` cada día: procesa el día
simulado (ver [arquitectura.md](arquitectura.md)) y reconstruye el warehouse.

## Ejecución con backend GCS sin el job

La misma imagen y el mismo CLI corren fuera de Cloud Run apuntando al lake:

```bash
export PIPELINE_BACKEND=gcs PIPELINE_BUCKET=<bucket> PIPELINE_PROJECT=<proyecto>
python -m pipeline.cli ingest --date 2022-01-15
```

## Operación y ciclo de vida

**Costo.** Con el volumen de este proyecto (unos 2.4 MB en raw y ejecuciones de
2–3 minutos con 1 vCPU), el consumo cae dentro de los niveles gratuitos de Cloud
Run, Cloud Storage en `us-central1`, BigQuery, Cloud Scheduler y Secret Manager.
El único almacenamiento que crece con cada despliegue es Artifact Registry, que
queda acotado por la política de limpieza. El presupuesto solo emite alertas; no
limita el gasto.

**Pausa.** Pausar el Scheduler detiene las ejecuciones y conserva datos, vistas,
historial y la conexión del reporte:

```bash
gcloud scheduler jobs pause  dealer-pipeline-daily --location us-central1
gcloud scheduler jobs resume dealer-pipeline-daily --location us-central1
```

**Eliminación.** El bucket y los datasets están protegidos contra borrado con
datos (`force_destroy = false`). Terraform lee esa protección del estado, no de la
configuración, así que desactivarla requiere un `apply` antes del `destroy`:

```bash
terraform apply   -var force_destroy=true
terraform destroy -var force_destroy=true
```

Las APIs se declaran con `disable_on_destroy = false`, de modo que el `destroy` no
deshabilita servicios del proyecto. El pool de Workload Identity queda en borrado
suave durante 30 días; recrear la infraestructura dentro de ese plazo requiere
restaurar o importar el pool `github` en lugar de crearlo.
