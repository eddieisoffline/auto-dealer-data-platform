-- Staging: tablas externas sobre el Parquet curado del data lake.
-- No almacenan datos y se recrean en cada refresco del warehouse.

CREATE OR REPLACE EXTERNAL TABLE `${project}.dealer_curated.ext_ventas`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://${bucket}/curated/ventas/*']
);

CREATE OR REPLACE EXTERNAL TABLE `${project}.dealer_curated.ext_gastos_mensuales`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://${bucket}/curated/gastos_mensuales/*']
);

CREATE OR REPLACE EXTERNAL TABLE `${project}.dealer_curated.ext_objetivos`
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://${bucket}/curated/objetivos/*']
);
