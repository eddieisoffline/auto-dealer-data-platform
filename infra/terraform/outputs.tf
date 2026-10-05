output "bucket_name" {
  description = "Bucket del data lake (capas raw/ y curated/)."
  value       = google_storage_bucket.lake.name
}

output "kaggle_secret_id" {
  description = "Secreto donde guardar el token de la API de Kaggle."
  value       = google_secret_manager_secret.kaggle_token.secret_id
}

output "image_repository" {
  description = "Repositorio donde subir la imagen Docker."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.pipeline.repository_id}"
}

output "bigquery_datasets" {
  description = "Datasets creados en BigQuery."
  value       = [for d in google_bigquery_dataset.dw : d.dataset_id]
}

output "runner_service_account" {
  description = "Cuenta de servicio con la que corre el pipeline."
  value       = google_service_account.runner.email
}

output "github_workload_identity_provider" {
  description = "Valor de la variable GCP_WORKLOAD_IDENTITY_PROVIDER en GitHub."
  value       = local.github_enabled ? google_iam_workload_identity_pool_provider.github[0].name : "github_repository vacío: despliegue automático sin configurar"
}

output "github_deployer_service_account" {
  description = "Valor de la variable GCP_DEPLOYER_SA en GitHub."
  value       = local.github_enabled ? google_service_account.deployer[0].email : "github_repository vacío: despliegue automático sin configurar"
}

output "run_job_command" {
  description = "Comando para ejecutar el job a mano (solo con deploy_job = true)."
  value       = var.deploy_job ? "gcloud run jobs execute dealer-pipeline --region ${var.region} --project ${var.project_id}" : "deploy_job = false: el job aún no existe"
}
