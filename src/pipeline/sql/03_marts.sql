-- Capa de consumo para Power BI: dos dimensiones y dos vistas de hechos.
-- Las razones (margen_bruto, margen_ebitda, cumplimiento) van de 0 a 1 y se
-- formatean como porcentaje en el reporte. Para agregar por varias filas se
-- suman los importes y se vuelve a dividir, nunca se promedian las razones.

CREATE OR REPLACE VIEW `${project}.dealer_marts.dim_concesionaria` AS
SELECT
  dealer_name,
  ANY_VALUE(dealer_region) AS region
FROM `${project}.dealer_curated.ventas`
GROUP BY dealer_name;

CREATE OR REPLACE VIEW `${project}.dealer_marts.dim_fecha` AS
SELECT
  d AS fecha,
  DATE_TRUNC(d, MONTH) AS mes,
  EXTRACT(YEAR FROM d) AS anio,
  EXTRACT(MONTH FROM d) AS mes_numero,
  FORMAT_DATE('%Y-%m', d) AS anio_mes
FROM UNNEST(GENERATE_DATE_ARRAY(
  (SELECT MIN(fecha) FROM `${project}.dealer_curated.ventas`),
  (SELECT MAX(fecha) FROM `${project}.dealer_curated.ventas`)
)) AS d;

CREATE OR REPLACE VIEW `${project}.dealer_marts.kpi_diario` AS
SELECT
  fecha,
  dealer_name,
  COUNT(*) AS num_ventas,
  SUM(precio) AS ventas,
  SUM(costo) AS costo,
  SUM(utilidad_bruta) AS utilidad_bruta
FROM `${project}.dealer_curated.ventas`
GROUP BY fecha, dealer_name;

CREATE OR REPLACE VIEW `${project}.dealer_marts.kpi_mensual` AS
WITH ventas_mes AS (
  SELECT
    dealer_name,
    mes,
    COUNT(*) AS num_ventas,
    SUM(precio) AS ventas,
    SUM(costo) AS costo,
    SUM(utilidad_bruta) AS utilidad_bruta
  FROM `${project}.dealer_curated.ventas`
  GROUP BY dealer_name, mes
),
base AS (
  SELECT
    v.dealer_name,
    v.mes,
    v.num_ventas,
    v.ventas,
    v.costo,
    v.utilidad_bruta,
    g.nomina,
    g.renta,
    g.marketing,
    g.otros_gastos,
    g.depreciacion,
    g.intereses,
    g.impuestos,
    g.nomina + g.renta + g.marketing + g.otros_gastos AS opex,
    o.objetivo_ventas
  FROM ventas_mes AS v
  LEFT JOIN `${project}.dealer_curated.gastos_mensuales` AS g
    ON g.dealer_name = v.dealer_name AND g.mes = v.mes
  LEFT JOIN `${project}.dealer_curated.objetivos` AS o
    ON o.dealer_name = v.dealer_name AND o.mes = v.mes
)
SELECT
  dealer_name,
  mes,
  num_ventas,
  ventas,
  costo,
  utilidad_bruta,
  opex,
  utilidad_bruta - opex AS ebitda,
  depreciacion,
  intereses,
  impuestos,
  utilidad_bruta - opex - depreciacion - intereses - impuestos AS utilidad_neta,
  objetivo_ventas,
  SAFE_DIVIDE(ventas, num_ventas) AS ticket_promedio,
  SAFE_DIVIDE(utilidad_bruta, ventas) AS margen_bruto,
  SAFE_DIVIDE(utilidad_bruta - opex, ventas) AS margen_ebitda,
  SAFE_DIVIDE(ventas, objetivo_ventas) AS cumplimiento
FROM base;
