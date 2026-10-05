# Capturas para el README

El README de portada no incluye imágenes todavía: hay que tomarlas de tu propio
despliegue. Tómalas, guárdalas en esta carpeta con estos nombres y descomenta el
bloque "Capturas" del README.

| Archivo | Qué capturar |
|---------|--------------|
| `powerbi-resumen.png` | página de resumen: tarjetas de ventas, utilidad bruta, EBITDA, utilidad neta y cumplimiento |
| `powerbi-sucursales.png` | comparativo entre concesionarias con ranking y semáforo de cumplimiento |
| `bigquery-marts.png` | explorador de BigQuery con las tablas de `dealer_curated` y las vistas de `dealer_marts` |
| `gcs-lake.png` | bucket con las carpetas `raw/` y `curated/` y sus particiones |
| `cloud-run-job.png` | historial de ejecuciones del job `dealer-pipeline`, con ejecuciones exitosas |
| `ci-verde.png` | una ejecución del workflow en GitHub Actions con `test`, `terraform` y `deploy` en verde |

Antes de publicarlas, tapa lo que no debe verse: ID del proyecto de GCP, correo,
cuenta de facturación y cualquier token.

## Resultados reales para el README

Cuando lo hayas ejecutado, agrega cifras medidas por ti, no estimadas. Algunas
formas de obtenerlas:

```sql
SELECT COUNT(*) AS filas, MIN(fecha) AS desde, MAX(fecha) AS hasta
FROM `<proyecto>.dealer_curated.ventas`;
```

- Duración de una ejecución diaria: columna de duración en el historial del job.
- Costo mensual aproximado: informe de facturación del proyecto.
- Pruebas: salida de `pytest` (número de pruebas).

## Actualizar el caso de estudio del portafolio

`case-study.md` es lo que publica el portafolio. Con las capturas y las cifras:

1. Agrega las imágenes en ambos bloques (`:::es` y `:::en`) con URL absoluta,
   por ejemplo
   `![Resumen en Power BI](https://github.com/eddieisoffline/auto-dealer-data-platform/blob/main/docs/img/powerbi-resumen.png?raw=true)`.
   Las rutas relativas no funcionan en el portafolio.
2. En el frontmatter, agrega `cover_image` con la URL de `powerbi-resumen.png` y,
   si el reporte es público, `demo_url`.
3. Reemplaza el párrafo de "siguiente paso" en "Resultados" por las cifras medidas.
4. Cambia `featured: false` a `featured: true`.
5. En el backend del portafolio, agrega `eddieisoffline/auto-dealer-data-platform`
   a `ALLOWED_REPOS` y crea el webhook del repo.
