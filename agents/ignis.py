"""
SteamFire — Sprint M3 — AG-IGNIS

Orquestador maestro PIRO. Lee inferencias de PIROIA + ANIMA + matriz_vida,
consulta Gemini 2.5 Pro con system prompt cargado desde idworld_agentes,
emite decisión estructurada en piro_inferencias y acciones shadow en piro_acciones_simuladas.

Jerarquía de prioridades (estricta):
  1. Vidas humanas (matriz_vida obligatoria)
  2. Detección temprana (humo + llama + tasa T)
  3. Prevención flashover (lead time < 30s → crítica)
  4. Continuidad operativa (minimizar falsos positivos)

Etapa 0 = shadow_mode SIEMPRE. ejecutada=False SIEMPRE.

Uso:
    python -m agents.ignis --watch
    python -m agents.ignis --once
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from agents.base import BaseAgent

try:
    import google.generativeai as genai
    GEMINI_OK = True
except ImportError:
    GEMINI_OK = False


class AgenteIgnis(BaseAgent):
    AGENTE_CODIGO = "AG-IGNIS"

    UMBRAL_PRE_ALERTA = 0.40
    UMBRAL_ALERTA = 0.60
    UMBRAL_CRITICA = 0.80

    def __init__(self) -> None:
        super().__init__()
        if GEMINI_OK and os.environ.get("GEMINI_API_KEY"):
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            modelo = self.modelo_ia or "gemini-2.5-pro"
            try:
                self.gemini = genai.GenerativeModel(
                    modelo,
                    system_instruction=self.system_prompt,
                )
                self.log.info("gemini_listo", modelo=modelo)
            except Exception as e:
                self.log.warning("gemini_init_falló", err=str(e))
                self.gemini = None
        else:
            self.gemini = None
            self.log.warning("gemini_no_disponible_usando_reglas")

    # ---------- decisión por reglas (fallback / sanity check) ----------
    def decide_por_reglas(self, contexto: dict) -> dict:
        det = contexto.get("deteccion") or {}
        flash = contexto.get("flashover") or {}
        matriz = contexto.get("matriz_vida") or {}
        personas = (matriz.get("num_personas") or 0)
        humo = det.get("humo_max_pct", 0) or 0
        flame = det.get("flame_detected", False)
        smoke = det.get("smoke_detected", False)
        temp = det.get("temp_max_c", 0) or 0
        h60 = flash.get("h60", 0) or 0
        lead_time = flash.get("lead_time_s")

        # heurística capa principal
        riesgo_incendio = 0.0
        if smoke and flame:
            riesgo_incendio = min(0.95, 0.6 + 0.3 * (humo / 80))
        elif smoke:
            riesgo_incendio = min(0.6, 0.3 + 0.3 * (humo / 80))
        elif flame:
            riesgo_incendio = 0.5
        # penalizar humo teatro: humo>30 + CO=0
        co = det.get("co_max_ppm", 0) or 0
        if smoke and co < 5 and humo > 30:
            riesgo_incendio = max(0.10, riesgo_incendio - 0.55)

        riesgo_flashover = h60

        # Decisión por jerarquía
        if riesgo_flashover > 0.7 and (lead_time or 999) < 30:
            decision = "critica"
        elif personas > 0 and (humo > 60 or flame):
            decision = "evacuacion"
        elif riesgo_incendio >= self.UMBRAL_CRITICA:
            decision = "critica"
        elif riesgo_incendio >= self.UMBRAL_ALERTA:
            decision = "alerta"
        elif riesgo_incendio >= self.UMBRAL_PRE_ALERTA:
            decision = "pre_alerta"
        else:
            decision = "monitoreo"

        # Acciones recomendadas
        acciones = []
        if decision in ("alerta", "critica", "evacuacion"):
            acciones.append({
                "tipo": "alertar_bcbrp",
                "objetivo": "BCBRP_canal_telegram",
                "prioridad": "critical" if decision == "critica" else "urgent",
                "justificacion": f"Detección {decision} en zona — humo={humo:.1f}% temp={temp:.1f}°C personas={personas}",
            })
        if decision == "critica" or (riesgo_flashover > 0.5):
            acciones.append({
                "tipo": "cortar_gas",
                "objetivo": f"zona_{contexto.get('zona_codigo')}",
                "prioridad": "urgent",
                "justificacion": "Prevención escalada — corte automático línea gas",
            })
        if personas > 0 and decision in ("critica", "evacuacion"):
            acciones.append({
                "tipo": "evacuacion_zonal",
                "objetivo": f"zona_{contexto.get('zona_codigo')}",
                "prioridad": "critical",
                "justificacion": f"{personas} personas en zona con humo/llama crítica",
            })
            acciones.append({
                "tipo": "presurizar_escalera",
                "objetivo": "escalera_emergencia_principal",
                "prioridad": "urgent",
                "justificacion": "Mantener vía evacuación libre de humo (NFPA 92)",
            })
            acciones.append({
                "tipo": "recall_ascensor",
                "objetivo": "todos_los_ascensores",
                "prioridad": "urgent",
                "justificacion": "Phase I NFPA 72 — ascensores a piso seguro",
            })

        return {
            "decision": decision,
            "zona_id": contexto.get("zona_id"),
            "riesgo_incendio_pct": round(riesgo_incendio * 100, 1),
            "riesgo_flashover_pct": round(riesgo_flashover * 100, 1),
            "lead_time_estimado_s": lead_time,
            "personas_en_zona": personas,
            "acciones_recomendadas": acciones,
            "evidencia": {
                "humo_pct": humo,
                "temp_c": temp,
                "co_ppm": co,
                "flame_detected": flame,
                "smoke_detected": smoke,
                "h60_flashover_prob": h60,
            },
            "metodo": "reglas",
        }

    # ---------- decisión Gemini (con fallback a reglas) ----------
    def decide(self, contexto: dict) -> dict:
        # Siempre calculamos el baseline por reglas — sirve de sanity check
        baseline = self.decide_por_reglas(contexto)
        if not self.gemini:
            return baseline
        prompt_user = (
            "Contexto JSON con telemetría reciente, inferencias PIROIA y matriz de vidas ANIMA. "
            "Analiza y devuelve SOLO un JSON válido (sin texto extra) con la estructura:\n"
            "{decision, zona_id, riesgo_incendio_pct, riesgo_flashover_pct, lead_time_estimado_s, "
            "personas_en_zona, acciones_recomendadas[], evidencia{}}\n\n"
            "Decision ∈ {monitoreo, pre_alerta, alerta, critica, evacuacion}.\n\n"
            "BASELINE_REGLAS (puedes confirmar o discrepar justificadamente):\n"
            f"{json.dumps(baseline, ensure_ascii=False, indent=2)}\n\n"
            "CONTEXTO:\n"
            f"{json.dumps(contexto, ensure_ascii=False, indent=2)}"
        )
        try:
            resp = self.gemini.generate_content(
                prompt_user,
                generation_config={"response_mime_type": "application/json", "temperature": 0.1},
            )
            decision = json.loads(resp.text)
            decision["metodo"] = "gemini"
            return decision
        except Exception as e:
            self.log.warning("gemini_falló_usando_reglas", err=str(e))
            return baseline

    # ---------- ciclo zona ----------
    def orquestar_zona(self, zona: dict) -> int | None:
        zona_id = zona["zona_id"]
        # Inferencias recientes PIROIA (humo+flashover)
        inf = self.fetch_inferencias_recientes(
            zona_id=zona_id, ventana_s=5, agentes=["AG-PIROIA"], limite=10
        )
        det = next((i for i in inf if i["tipo_inferencia"] in ("detect_humo", "detect_baseline")), None)
        flash = next((i for i in inf if i["tipo_inferencia"] == "flashover_pred"), None)
        matriz = self.fetch_matriz_vida_actual(zona_id=zona_id)

        contexto = {
            "zona_id": zona_id,
            "zona_codigo": zona.get("codigo"),
            "deteccion": det.get("resultado") if det else None,
            "flashover": flash.get("resultado") if flash else None,
            "matriz_vida": matriz,
        }
        with self.measure_latency() as t_lat:
            decision = self.decide(contexto)
        latencia = t_lat()

        # Insertar inferencia IGNIS
        confianza_decision = {
            "monitoreo": 0.95, "pre_alerta": 0.75, "alerta": 0.85,
            "critica": 0.90, "evacuacion": 0.92,
        }.get(decision.get("decision"), 0.7)
        inf_id = self.insert_inferencia(
            tipo_inferencia="ignis_decision",
            resultado=decision,
            zona_id=zona_id,
            confianza=confianza_decision,
            latencia_ms=latencia,
            trigger_emitido=decision.get("decision") in ("alerta", "critica", "evacuacion"),
        )

        # Emitir acciones shadow recomendadas
        for accion in decision.get("acciones_recomendadas", []):
            try:
                self.emit_accion_simulada(
                    tipo_accion=accion["tipo"],
                    objetivo=accion.get("objetivo", "n/a"),
                    prioridad=accion.get("prioridad", "info"),
                    justificacion=accion.get("justificacion", "—"),
                    zona_id=zona_id,
                    parametros=accion.get("parametros") or {},
                    inferencia_id=inf_id,
                )
            except Exception as e:
                self.log.error("emit_accion_falló", tipo=accion.get("tipo"), err=str(e))

        return inf_id


async def run_watch(intervalo_s: float = 1.5) -> None:
    agent = AgenteIgnis()
    agent.log.info("ignis_watch_started", intervalo_s=intervalo_s, modelo=agent.modelo_ia)
    while True:
        zonas = agent.fetch_zonas_activas()
        for z in zonas:
            try:
                agent.orquestar_zona(z)
            except Exception as e:
                agent.log.error("orquestar_zona_falló", zona=z.get("codigo"), err=str(e))
        await asyncio.sleep(intervalo_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="AG-IGNIS — Sprint M3")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--intervalo", type=float, default=1.5)
    args = parser.parse_args()
    if args.watch:
        asyncio.run(run_watch(args.intervalo))
    elif args.once:
        agent = AgenteIgnis()
        for z in agent.fetch_zonas_activas():
            inf_id = agent.orquestar_zona(z)
            print(f"zona={z['codigo']} ignis_inferencia_id={inf_id}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
