# Despliegue en Google Cloud

## Probar en la nube sin desplegar el job

```bash
export PIPELINE_BACKEND=gcs
export PIPELINE_BUCKET=<tu-bucket>
python -m pipeline.cli ingest --date 2022-01-15
```

La imagen Docker ejecuta el mismo comando, pensada para Cloud Run Jobs.

## Infraestructura (Terraform)

Todo vive en `infra/terraform/`: APIs, bucket del lake (versionado, acceso público
bloqueado), datasets `dealer_curated` y `dealer_marts` en BigQuery, cuentas de
servicio con mínimo privilegio, Secret Manager para el token de Kaggle, Artifact
Registry, Cloud Run Job, Cloud Scheduler y una alerta de presupuesto opcional.

El job necesita que la imagen exista antes de crearse, por eso se despliega en dos
pasadas:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars     # pon tu project_id
gcloud auth application-default login

# 1) Infraestructura base
terraform init
terraform apply

# 2) Token de Kaggle (Secret Manager) e imagen
#    El job no se crea si el secreto no tiene ninguna versión.
printf '%s' "$KAGGLE_API_TOKEN" | \
  gcloud secrets versions add kaggle-api-token --data-file=-
REPO=$(terraform output -raw image_repository)
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t $REPO/pipeline:0.1.0 ../..
docker push $REPO/pipeline:0.1.0

# 3) Job y Scheduler
terraform apply -var deploy_job=true -var image=$REPO/pipeline:0.1.0

# Carga histórica una vez (el timeout del job es de 30 min)
gcloud run jobs execute dealer-pipeline --region us-central1 \
  --args="backfill,--start,2022-01-01,--end,2022-12-31"
gcloud run jobs execute dealer-pipeline --region us-central1 \
  --args="curate,--start,2022-01-01,--end,2022-12-31"
# Primera carga del warehouse (necesita datos en curated/)
gcloud run jobs execute dealer-pipeline --region us-central1 --args="warehouse"
```

Desde ahí, el Scheduler ejecuta `daily --warehouse` todos los días a las 6:00
(hora de Ciudad de México): cada día real reproduce el mismo día del calendario de
`sim_year`, así siempre llegan datos nuevos aunque el dataset sea estático, y al
terminar se refresca BigQuery.

Notas:

- El token de Kaggle vive solo en Secret Manager: no está en el código, en el
  estado de Terraform ni en las variables. Genera el tuyo en tu cuenta de Kaggle
  (Settings, sección API).
- Ejecuta `terraform fmt` antes de tu primer commit; el CI comprueba el formato.
- Haz commit de `.terraform.lock.hcl` y no de `terraform.tfstate`. Para trabajar
  en equipo o desde CI, activa el backend remoto comentado en `versions.tf`.
- Bucket y dataset deben estar en la misma geografía (con los valores por defecto,
  `us-central1` y `US` lo están).
- La alerta de presupuesto necesita permisos sobre la cuenta de facturación;
  déjala vacía si tu usuario no los tiene.

## Despliegue automático (GitHub Actions)

Cada push a `main` ejecuta las pruebas y la validación de Terraform y, si pasan,
construye la imagen, la sube a Artifact Registry con el SHA del commit como
etiqueta y actualiza el Cloud Run Job. Cada versión desplegada queda así
identificada con su commit.

No se guarda ninguna credencial en GitHub: la autenticación usa Workload Identity
Federation. Google solo acepta el token de GitHub si viene de **tu repositorio** y
de la rama **main**, y la cuenta `deployer` solo puede subir imágenes y actualizar
ese job.

Se activa en tres pasos, después de haber creado el job (`deploy_job = true`):

```bash
# 1) En terraform.tfvars: github_repository = "eddieisoffline/auto-dealer-data-platform"
cd infra/terraform && terraform apply -var deploy_job=true -var image=$REPO/pipeline:0.1.0

# 2) Variables del repositorio (no son secretos), con los valores de Terraform
gh variable set GCP_PROJECT_ID                 --body "tu-proyecto-gcp"
gh variable set GCP_REGION                     --body "us-central1"
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --body "$(terraform output -raw github_workload_identity_provider)"
gh variable set GCP_DEPLOYER_SA                --body "$(terraform output -raw github_deployer_service_account)"

# 3) Haz push a main
```

Mientras la variable `GCP_WORKLOAD_IDENTITY_PROVIDER` no exista, el job `deploy`
se omite y el resto del CI funciona igual. Terraform ignora la imagen del job
después de crearlo, así que un `terraform apply` posterior no deshace un
despliegue.

Para volver a una versión anterior, actualiza el job con la etiqueta de ese
commit:

```bash
gcloud run jobs update dealer-pipeline --region us-central1 \
  --image $REPO/pipeline:<sha-del-commit>
```
