terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Estado remoto (recomendado si trabajas en equipo o desde CI):
  #   1. crea a mano un bucket solo para el estado
  #   2. descomenta este bloque y ejecuta `terraform init -migrate-state`
  # backend "gcs" {
  #   bucket = "<bucket-de-estado>"
  #   prefix = "dealer-platform"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
