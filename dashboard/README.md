# SteamFire Dashboard

Dashboard Next.js 14 + Supabase Realtime para visualizar el estado del sistema PIRO en tiempo real.

## Setup

```bash
cp .env.local.example .env.local
# editar con NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY

npm install
npm run dev
# http://localhost:3000
```

## Paneles

- **Briefing** — vistazo agregado del sistema (zonas, dispositivos, eventos, triggers, audit log).
- **Stream de inferencias** — log en vivo de cada decisión IGNIS / detección PIROIA / matriz ANIMA.
- **Matriz de vidas** — visualización por zona de personas detectadas con tracks Kalman.
- **Acciones shadow** — qué habría ejecutado AG-PIROACT (todo en shadow mode Etapa 0).
- **Dispositivos** — health de nodos sensoriales.

## Arquitectura

Lee directamente de las vistas operativas de Kronos:
- `v_piro_briefing`
- `v_piro_inferencias_recientes`
- `v_piro_matriz_vida_actual`
- `v_piro_acciones_recientes`
- `v_piro_dispositivos_health`

Subscripciones Supabase Realtime sobre `piro_inferencias` y `piro_acciones_simuladas` para refresco automático cuando aparece nueva data.

## Deploy a Vercel

```bash
vercel
# añadir env vars NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY en project settings
```
