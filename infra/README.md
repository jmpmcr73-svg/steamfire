# SteamFire — infra runbook

Migraciones SQL aplicadas en Kronos (proyecto Supabase `zsmlntktqisiclzaxoky`) durante Sprint M0.

## Orden cronológico (2026-05-02)

| # | version | name |
|---|---|---|
| 1 | 20260502225118 | piro_m0_001_core_schema |
| 2 | 20260502225150 | piro_m0_002_indexes |
| 3 | 20260502225218 | piro_m0_003_triggers_audit |
| 4 | 20260502225301 | piro_m0_004_views_rls |
| 5 | 20260502225522 | piro_m0_005a_extend_mapping_constraint |
| 6 | 20260502225658 | piro_m0_005b_seed_agents |
| 7 | 20260502225812 | piro_m0_006_kronos_integration_seed |
| 8 | 20260502225948 | piro_m0_007_seed_quemas_y_dispositivos_lab |

Las migraciones están persistidas en Supabase. Para descargarlas como archivos SQL versionables:

```bash
supabase login
supabase link --project-ref zsmlntktqisiclzaxoky
supabase db pull
# las migraciones aparecerán en supabase/migrations/
```

## Queries de verificación

### Estado consolidado del seed M0

```sql
SELECT 'agentes_piro' AS metrica, count(*)::text AS valor
FROM public.idworld_agentes WHERE proyecto='steamfire'
UNION ALL SELECT 'mapping_piro', count(*)::text
FROM public.move_agente_mapping WHERE dominio LIKE 'D_piro_%'
UNION ALL SELECT 'zonas_creadas', count(*)::text FROM public.piro_zonas
UNION ALL SELECT 'decisiones_steamfire', count(*)::text
FROM public.kronos_decisiones WHERE proyecto='steamfire' AND vigente
UNION ALL SELECT 'pendientes_steamfire', count(*)::text
FROM public.kronos_pendientes
WHERE proyecto='steamfire' AND estado IN ('abierto','en_progreso')
UNION ALL SELECT 'tablas_piro', count(*)::text
FROM information_schema.tables
WHERE table_schema='public' AND table_name LIKE 'piro_%'
UNION ALL SELECT 'vistas_piro', count(*)::text
FROM information_schema.views
WHERE table_schema='public' AND table_name LIKE 'v_piro_%'
UNION ALL SELECT 'quemas_planificadas', count(*)::text
FROM public.piro_quemas WHERE proyecto='steamfire'
UNION ALL SELECT 'dispositivos_total', count(*)::text
FROM public.piro_dispositivos WHERE proyecto='steamfire'
UNION ALL SELECT 'audit_entries', count(*)::text FROM public.piro_audit_log;
```

Resultado esperado tras M0: 6 / 6 / 7 / 1 / 12 / 11 / 7 / 12 / 12 / ≥31.

### Briefing en vivo

```sql
SELECT * FROM public.v_piro_briefing;
```

### Verificar integridad audit log (cualquier tampering rompe la cadena)

```sql
SELECT count(*) FILTER (WHERE valido) AS validos,
       count(*) FILTER (WHERE NOT valido) AS rotos
FROM public.piro_verify_audit_chain();
```

### Pendientes activos

```sql
SELECT pendiente_id, prioridad, titulo, estado
FROM public.kronos_pendientes
WHERE proyecto='steamfire' AND estado IN ('abierto','en_progreso')
ORDER BY prioridad, fecha_creacion;
```

### Listar agentes PIRO

```sql
SELECT agente_id, nombre, modelo_ia, estado, capa_logica
FROM public.idworld_agentes
WHERE proyecto='steamfire'
ORDER BY agente_id;
```

## Reset / re-aplicación en branch de desarrollo

Si quieres testear cambios sin tocar prod:

```bash
# crear branch (mismo schema, datos en blanco)
# vía MCP Supabase: Supabase:create_branch name=steamfire-dev
# luego apuntar SUPABASE_URL al branch para correr agentes
```

## Estructura tablas piro_*

```
piro_zonas                      ─ geometría espacial bajo monitoreo
piro_dispositivos               ─ nodos sensoriales
piro_eventos (PARTITIONED)      ─ stream raw telemetría (BRIN+GIN)
  └─ piro_eventos_default       ─ partition catch-all (pg_partman luego)
piro_inferencias                ─ output cada agente IA
piro_matriz_vida                ─ personas detectadas por zona
piro_propagacion_predicciones   ─ flashover + propagación
piro_acciones_simuladas         ─ shadow mode PIROACT
piro_quemas                     ─ controlled burns metadata
piro_kpis                       ─ métricas por quema vs ground truth
piro_audit_log                  ─ inmutable hash-chained SHA256
```

## Vistas operativas

```
v_piro_briefing                 ─ snapshot agregado sistema
v_piro_dispositivos_health      ─ salud de cada nodo
v_piro_quema_actual             ─ quema en curso si hay
v_piro_calibracion              ─ KPIs por quema
v_piro_inferencias_recientes    ─ stream para dashboard
v_piro_acciones_recientes       ─ shadow actions auditoría
v_piro_matriz_vida_actual       ─ snapshot últimos 5min por zona
```
