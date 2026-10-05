variable "project_id" {
  description = "ID del proyecto de GCP donde se crea todo."
  type        = string
}

variable "region" {
  description = "Región de Cloud Run, Artifact Registry y del bucket."
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "Ubicación de los datasets de BigQuery. Debe incluir a la región del bucket (US incluye us-central1)."
  type        = string
  default     = "US"
}

variable "bucket_name" {
  description = "Nombre del bucket del data lake. Vacío = <project_id>-dealer-lake."
  type        = string
  default     = ""
}

variable "force_destroy" {
  description = "Permite que terraform destroy borre el bucket aunque tenga objetos."
  type        = bool
  default     = false
}

variable "deploy_job" {
  description = "false = solo infraestructura base; true = además el Cloud Run Job y su Scheduler (requiere var.image)."
  type        = bool
  default     = false
}

variable "image" {
  description = "Imagen Docker del pipeline, por ejemplo us-central1-docker.pkg.dev/<proyecto>/pipeline/pipeline:0.1.0."
  type        = string
  default     = ""
}

variable "job_args" {
  description = "Argumentos del contenedor. Por defecto ejecuta el día simulado y refresca BigQuery."
  type        = list(string)
  default     = ["daily", "--warehouse"]
}

variable "github_repository" {
  description = "Repositorio de GitHub con formato owner/repo. Vacío = sin despliegue automático."
  type        = string
  default     = ""

  validation {
    condition     = var.github_repository == "" || can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository debe tener el formato owner/repo."
  }
}

variable "kaggle_dataset" {
  description = "Dataset de Kaggle (owner/slug) que descarga el pipeline."
  type        = string
  default     = "missionjee/car-sales-report"
}

variable "sim_year" {
  description = "Año del dataset que se reproduce cada día (PIPELINE_SIM_YEAR)."
  type        = number
  default     = 2022
}

variable "schedule" {
  description = "Cron del Cloud Scheduler."
  type        = string
  default     = "0 6 * * *"
}

variable "time_zone" {
  description = "Zona horaria del cron."
  type        = string
  default     = "America/Mexico_City"
}

variable "billing_account_id" {
  description = "ID de la cuenta de facturación (XXXXXX-XXXXXX-XXXXXX). Vacío = no crea alerta de presupuesto."
  type        = string
  default     = ""
}

variable "budget_amount" {
  description = "Monto mensual de la alerta de presupuesto, en número entero."
  type        = number
  default     = 5

  validation {
    condition     = var.budget_amount == floor(var.budget_amount) && var.budget_amount > 0
    error_message = "budget_amount debe ser un entero mayor que 0."
  }
}

variable "budget_currency" {
  description = "Moneda del presupuesto; debe coincidir con la de la cuenta de facturación."
  type        = string
  default     = "USD"
}
