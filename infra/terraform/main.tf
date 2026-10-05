locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_id}-dealer-lake"

  datasets = {
    dealer_curated = "Tablas curadas cargadas desde el data lake"
    dealer_marts   = "Vistas de KPIs para Power BI"
  }

  services = concat(
    [
      "artifactregistry.googleapis.com",
      "bigquery.googleapis.com",
      "cloudscheduler.googleapis.com",
      "iam.googleapis.com",
      "run.googleapis.com",
      "secretmanager.googleapis.com",
      "storage.googleapis.com",
    ],
    var.billing_account_id != "" ? ["billingbudgets.googleapis.com"] : [],
    local.github_enabled ? ["iamcredentials.googleapis.com", "sts.googleapis.com"] : [],
  )

  runner_member = "serviceAccount:${google_service_account.runner.email}"

  github_enabled = var.github_repository != ""
}

# --- APIs --------------------------------------------------------------------

resource "google_project_service" "enabled" {
  for_each = toset(local.services)

  service            = each.key
  disable_on_destroy = false
}

# --- Data lake (capas raw/ y curated/ viven dentro de este bucket) -----------

resource "google_storage_bucket" "lake" {
  name                        = local.bucket_name
  location                    = var.region
  force_destroy               = var.force_destroy
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Cada ejecución sobrescribe su partición; el versionado permite recuperar
  # una versión anterior y la regla borra las viejas a los 7 días para no pagar de más.
  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 7
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}

# --- Warehouse ---------------------------------------------------------------

resource "google_bigquery_dataset" "dw" {
  for_each = local.datasets

  dataset_id                 = each.key
  description                = each.value
  location                   = var.bq_location
  delete_contents_on_destroy = false

  depends_on = [google_project_service.enabled]
}

# --- Identidades (mínimo privilegio) -----------------------------------------

resource "google_service_account" "runner" {
  account_id   = "dealer-pipeline-runner"
  display_name = "Dealer pipeline runner"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "scheduler" {
  account_id   = "dealer-pipeline-sched"
  display_name = "Dealer pipeline scheduler"

  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket_iam_member" "runner_lake" {
  bucket = google_storage_bucket.lake.name
  role   = "roles/storage.objectAdmin"
  member = local.runner_member
}

resource "google_bigquery_dataset_iam_member" "runner_editor" {
  for_each = local.datasets

  dataset_id = google_bigquery_dataset.dw[each.key].dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = local.runner_member
}

resource "google_project_iam_member" "runner_bq_jobs" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = local.runner_member
}

# --- Credencial de Kaggle (el valor NO vive en Terraform ni en el repo) -------
# Terraform crea solo el contenedor del secreto. El valor se agrega a mano:
#   printf '%s' "$KAGGLE_API_TOKEN" | gcloud secrets versions add kaggle-api-token --data-file=-

resource "google_secret_manager_secret" "kaggle_token" {
  secret_id = "kaggle-api-token"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_iam_member" "runner_kaggle" {
  secret_id = google_secret_manager_secret.kaggle_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.runner_member
}

# --- Imágenes ----------------------------------------------------------------

resource "google_artifact_registry_repository" "pipeline" {
  repository_id = "pipeline"
  format        = "DOCKER"
  location      = var.region
  description   = "Imágenes del pipeline de datos"

  depends_on = [google_project_service.enabled]
}

# --- Ejecución: Cloud Run Job + Cloud Scheduler ------------------------------
# Se crean solo con deploy_job = true, porque la imagen debe existir antes.

resource "google_cloud_run_v2_job" "pipeline" {
  count = var.deploy_job ? 1 : 0

  name                = "dealer-pipeline"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.runner.email
      max_retries     = 1
      timeout         = "1800s"

      containers {
        image = var.image
        args  = var.job_args

        env {
          name  = "PIPELINE_BACKEND"
          value = "gcs"
        }

        env {
          name  = "PIPELINE_BUCKET"
          value = google_storage_bucket.lake.name
        }

        env {
          name  = "PIPELINE_PROJECT"
          value = var.project_id
        }

        env {
          name  = "PIPELINE_SIM_YEAR"
          value = tostring(var.sim_year)
        }

        env {
          name  = "PIPELINE_SOURCE"
          value = "kaggle"
        }

        env {
          name  = "PIPELINE_KAGGLE_DATASET"
          value = var.kaggle_dataset
        }

        env {
          name = "KAGGLE_API_TOKEN"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.kaggle_token.secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.image != ""
      error_message = "Define var.image cuando deploy_job = true."
    }

    # Después de la primera creación, la imagen la actualiza GitHub Actions;
    # así un terraform apply posterior no la devuelve a la versión inicial.
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.enabled,
    google_storage_bucket_iam_member.runner_lake,
    google_secret_manager_secret_iam_member.runner_kaggle,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  count = var.deploy_job ? 1 : 0

  location = var.region
  name     = google_cloud_run_v2_job.pipeline[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "daily" {
  count = var.deploy_job ? 1 : 0

  name             = "dealer-pipeline-daily"
  description      = "Ejecuta el pipeline una vez al día"
  region           = var.region
  schedule         = var.schedule
  time_zone        = var.time_zone
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.pipeline[0].name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_invoker]
}

# --- Despliegue automático desde GitHub Actions (opcional) --------------------
# Autenticación sin llaves: GitHub presenta un token OIDC que solo se acepta si
# viene de este repositorio y de la rama main. No se guarda ninguna credencial.

resource "google_iam_workload_identity_pool" "github" {
  count = local.github_enabled ? 1 : 0

  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count = local.github_enabled ? 1 : 0

  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.ref == \"refs/heads/main\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  count = local.github_enabled ? 1 : 0

  account_id   = "dealer-pipeline-deployer"
  display_name = "Dealer pipeline deployer (GitHub Actions)"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account_iam_member" "deployer_wif" {
  count = local.github_enabled ? 1 : 0

  service_account_id = google_service_account.deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  count = local.github_enabled ? 1 : 0

  repository = google_artifact_registry_repository.pipeline.name
  location   = google_artifact_registry_repository.pipeline.location
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer[0].email}"
}

# Para actualizar el job, el deployer debe poder "actuar como" la cuenta con la que corre.
resource "google_service_account_iam_member" "deployer_acts_as_runner" {
  count = local.github_enabled ? 1 : 0

  service_account_id = google_service_account.runner.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer[0].email}"
}

resource "google_cloud_run_v2_job_iam_member" "deployer_updates_job" {
  count = local.github_enabled && var.deploy_job ? 1 : 0

  location = var.region
  name     = google_cloud_run_v2_job.pipeline[0].name
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer[0].email}"
}

# --- Alerta de presupuesto (opcional) ----------------------------------------

data "google_project" "this" {
  project_id = var.project_id
}

resource "google_billing_budget" "monthly" {
  count = var.billing_account_id != "" ? 1 : 0

  billing_account = var.billing_account_id
  display_name    = "dealer-platform-${var.project_id}"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.enabled]
}
