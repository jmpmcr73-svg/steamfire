# SteamFire — Etapa 0.PRE

Sistema de detección temprana de incendios + matriz de vidas + IA orquestada.
Rama PIRO bajo MOVE — Alejandría Steam Labs.

---

## Estado actual (2026-05-02)

Sprints completados en este repo:

| Sprint | Entregable | Estado |
|---|---|---|
| **M0** | Schema PIRO en Kronos (10 tablas + 7 vistas + RLS + audit hash-chain) | Aplicado en Supabase `zsmlntktqisiclzaxoky` |
| **M0** | 6 agentes PIRO sembrados con prompts (`idworld_agentes` + `move_agente_mapping`) | Aplicado |
| **M0** | 7 zonas + 12 quemas + 12 dispositivos lab Jose | Aplicado ($2,314 hardware planificado) |
| **M0** | 1 decisión SteamFire + 12 pendientes en Kronos | Aplicado |
| **M0.5** | Generador sintético `simulator/synthetic_generator.py` + 12 escenarios | Código listo |
| **M1** | AG-PIROIA detección humo/llama + P-Flash | Código listo (heurística + adapter ONNX) |
| **M2** | AG-ANIMA matriz vidas mmWave + Kalman tracking | Código listo (DBSCAN + filterpy) |
| **M3** | AG-IGNIS orquestador con Gemini 2.5 Pro + reglas fallback | Código listo |
| **M4** | AG-TACTICA backend (Telegram/WhatsApp/ICS XML) | Código listo |
| **M4** | Dashboard Next.js 14 con Realtime | Código listo (5 paneles) |
| **M4** | Bot Telegram BCBRP | Código listo |

---

## Flujo demo end-to-end (cuando vuelvas)

### 1. Setup (10 min)

```bash
cd steamfire
make install              # crea .venv y pip install
cp .env.example .env      # editar con tus credenciales

cd dashboard
cp .env.local.example .env.local   # NEXT_PUBLIC_SUPABASE_URL + ANON_KEY
npm install
cd ..
```

### 2. Lanzar dashboard

```bash
make dashboard-dev
# abrir http://localhost:3000
```

Verás 5 paneles vacíos esperando data: Briefing, Stream inferencias, Matriz vidas, Acciones shadow, Dispositivos.

### 3. Lanzar los 4 agentes en otra terminal

```bash
source .venv/bin/activate
make all-agents           # lanza piroia, anima, ignis, tactica en paralelo
```

Empezarás a ver logs JSON estructurados de los 4 agentes corriendo en bucle.

### 4. Inyectar un escenario sintético en otra terminal

```bash
source .venv/bin/activate
make simulate-list                                # ver los 12 escenarios

make simulate s=Q01-VELA-BASELINE                 # baseline humo bajo, sin alarma esperada
make simulate s=Q11-FALSO-POSITIVO                # humo teatro, IGNIS NO debe alertar
make simulate s=Q10-MULTI-PERSONA                 # 2 personas + humo denso → evacuación
make simulate-rt s=Q12-FULL-LAB                   # full scale en tiempo real (7 min)
```

A medida que el simulador inyecta eventos en `piro_eventos`:

1. **AG-PIROIA** detecta humo/llama y predice flashover → inserts en `piro_inferencias`.
2. **AG-ANIMA** procesa point-clouds mmWave → tracks Kalman → inserts en `piro_matriz_vida`.
3. **AG-IGNIS** lee inferencias + matriz vidas → consulta Gemini → emite decisión + acciones shadow.
4. **AG-TACTICA** detecta nuevas decisiones IGNIS → genera mensajes Telegram/WhatsApp/ICS XML.
5. **Dashboard** se actualiza en tiempo real vía Supabase Realtime.

### 5. Verificar con SQL

```sql
-- Eventos sintéticos procesados
SELECT count(*) FROM piro_eventos
WHERE fuente='sintetico' AND ts > now() - interval '15 minutes';

-- Última decisión IGNIS
SELECT ts, resultado->>'decision' AS decision,
       resultado->>'riesgo_incendio_pct' AS riesgo,
       resultado->>'personas_en_zona' AS personas
FROM piro_inferencias
WHERE agente_codigo='AG-IGNIS' AND tipo_inferencia='ignis_decision'
ORDER BY ts DESC LIMIT 5;

-- Acciones shadow emitidas
SELECT ts, tipo_accion, prioridad, justificacion
FROM piro_acciones_simuladas
ORDER BY ts DESC LIMIT 10;
```

---

## Estructura del repo

```
steamfire/
├── README.md                  ← este archivo
├── Makefile                   ← comandos rápidos
├── .env.example
├── requirements.txt
│
├── simulator/
│   ├── synthetic_generator.py      ← Sprint M0.5
│   └── scenarios.json              ← 12 escenarios catalogados
│
├── agents/
│   ├── base.py                     ← BaseAgent compartido
│   ├── piroia.py                   ← Sprint M1
│   ├── anima.py                    ← Sprint M2
│   ├── ignis.py                    ← Sprint M3
│   └── tactica.py                  ← Sprint M4 backend
│
├── dashboard/                       ← Sprint M4 frontend (Next.js 14)
│   ├── package.json
│   ├── app/page.tsx
│   ├── app/components/             ← 5 paneles
│   └── lib/supabase.ts + types.ts
│
├── bots/
│   └── telegram_bot.py             ← /briefing /zonas /quemas /alertas
│
└── infra/
    └── README.md                    ← runbook migraciones Supabase
```

---

## Arquitectura

```
                  ┌──────────────────────────┐
                  │  AG-IGNIS (gemini-pro)   │  orquestador
                  │  decide + emite shadow   │
                  └────────────┬─────────────┘
                          ▲    │ acciones
                  inferencias  │
                  ┌──────┴─────┴─────────┐
                  │                       │
            ┌─────▼─────────┐    ┌────────▼────────┐
            │ AG-PIROIA     │    │ AG-ANIMA         │
            │ humo/llama    │    │ matriz vidas     │
            │ P-Flash       │    │ mmWave + Kalman  │
            │ lead time     │    │                  │
            └───────────────┘    └──────────────────┘
                  ▲                       ▲
                  └────────┬──────────────┘
                           │ piro_eventos (stream)
                           │
                   ┌───────┴────────┐
                   │ Lab Jose       │  Etapa 0.PRE
                   │ ESP32+sensores │  ($2,314)
                   │ + Jetson Nano  │  reusable POST
                   └────────────────┘

    todas las decisiones IGNIS pasan por:

         AG-PIROCHEM (selector químico, scaffolding)
             ↓
         AG-PIROACT (actuadores BMS — SHADOW MODE)
             ↓
         piro_acciones_simuladas (ejecutada=false SIEMPRE Etapa 0)
             ↓
         AG-TACTICA → Dashboard / Telegram / WhatsApp / ICS
```

Toda mutación pasa por `piro_audit_log` con SHA256 hash-chain (tampering evidente).

---

## Pendientes activos en Kronos

```sql
SELECT pendiente_id, prioridad, titulo
FROM kronos_pendientes
WHERE proyecto='steamfire' AND estado IN ('abierto','en_progreso')
ORDER BY prioridad, fecha_creacion;
```

Los 12 sembrados en Sprint M0:
- M0 schema (en_progreso → marcar completo cuando verifiques)
- M0.5 simulador (código listo, falta correr)
- M1 PIROIA (código listo, falta entrenar YOLOv8 y P-Flash con sintéticos)
- M2 ANIMA (código listo, validar con datos reales en M5)
- M3 IGNIS (código listo, calibrar prompts y umbrales)
- M4 TACTICA + Dashboard (código listo, deploy a Vercel)
- M5 hardware lab personal ($2,314)
- M5 quemas mínimas calibración
- M6 whitepaper + outreach
- Decidir Gemini API budget
- Decidir SV vs Panamá container
- Carta a Cnel. Víctor Álvarez BCBRP

---

## Proyecto Supabase

- ID: `zsmlntktqisiclzaxoky`
- Nombre: `move-idworld`
- Schema PIRO: prefijo `piro_*` en `public`
- Agentes: en `public.idworld_agentes` con `proyecto='steamfire'`
- Mapping: en `public.move_agente_mapping` con `dominio LIKE 'D_piro_%'`

---

## Créditos

Sub-proyecto SteamFire bajo MOVE / iDWorld de Alejandría Steam Labs.
Diseñado para BCBRP (Benemérito Cuerpo de Bomberos de la República de Panamá) — Cnel. Víctor Álvarez (Director General).
Sesión de implementación: 2026-05-02.
