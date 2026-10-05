-- Tablas nativas del warehouse con tipos explícitos.
-- Se reconstruyen completas en cada refresco: el volumen es pequeño y así la
-- carga es idempotente y nunca duplica filas. Con más volumen, cambiar a MERGE
-- por partición.

CREATE OR REPLACE TABLE `${project}.dealer_curated.ventas`
PARTITION BY fecha
CLUSTER BY dealer_name
AS
SELECT
  CAST(car_id AS STRING) AS car_id,
  CAST(`date` AS DATE) AS fecha,
  CAST(mes AS DATE) AS mes,
  dealer_name,
  dealer_region,
  company,
  model,
  CAST(price AS NUMERIC) AS precio,
  CAST(costo AS NUMERIC) AS costo,
  CAST(utilidad_bruta AS NUMERIC) AS utilidad_bruta
FROM `${project}.dealer_curated.ext_ventas`;

CREATE OR REPLACE TABLE `${project}.dealer_curated.gastos_mensuales`
AS
SELECT
  dealer_name,
  CAST(mes AS DATE) AS mes,
  CAST(nomina AS NUMERIC) AS nomina,
  CAST(renta AS NUMERIC) AS renta,
  CAST(marketing AS NUMERIC) AS marketing,
  CAST(otros_gastos AS NUMERIC) AS otros_gastos,
  CAST(depreciacion AS NUMERIC) AS depreciacion,
  CAST(intereses AS NUMERIC) AS intereses,
  CAST(impuestos AS NUMERIC) AS impuestos
FROM `${project}.dealer_curated.ext_gastos_mensuales`;

CREATE OR REPLACE TABLE `${project}.dealer_curated.objetivos`
AS
SELECT
  dealer_name,
  CAST(mes AS DATE) AS mes,
  CAST(objetivo_ventas AS NUMERIC) AS objetivo_ventas
FROM `${project}.dealer_curated.ext_objetivos`;
