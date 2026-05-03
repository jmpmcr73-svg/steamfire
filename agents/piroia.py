"""
SteamFire — Sprint M1 — AG-PIROIA

Agente percepción visual + termodinámica.
- Detección humo/llama en imágenes (YOLOv8-nano fine-tuned, fallback a heurística)
- P-Flash: SVR sobre features termopares + tasa subida T (NIST PB 79-15)
- CNN-LSTM lead time predictor (placeholder hasta entrenar con sintéticos)

Etapa 0.PRE: opera sobre eventos sintéticos de simulator/synthetic_generator.
Etapa 0.POST: opera sobre frames reales de cámaras + termopares en container BCBRP.

Uso:
    python -m agents.piroia --watch         # bucle continuo, infiere cada 1s
    python -m agents.piroia --once --zona 1 # una sola inferencia y salir
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
from collections import defaultdict
from datetime import datetime, timezone

from agents.base import BaseAgent

# Adapter ONNX condicional — si no hay weights todavía, usa heurística
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False


class AgentePiroIA(BaseAgent):
    AGENTE_CODIGO = "AG-PIROIA"

    # Umbrales calibrables (M5 los ajusta con datos reales de lab)
    UMBRAL_HUMO_PCT = 5.0          # obscuración mínima para "smoke detected"
    UMBRAL_TEMP_C = 60.0            # subida sobre ambiente para alarma
    UMBRAL_LLAMA_UV = 0.30
    TASA_SUBIDA_T_FLASHOVER = 8.0   # °C/s sostenido → riesgo flashover
    YOLO_WEIGHTS = os.environ.get("YOLO_WEIGHTS_PATH", "./weights/yolov8n_fire.onnx")

    def __init__(self) -> None:
        super().__init__()
        self.yolo_session = None
        if ONNX_AVAILABLE and os.path.exists(self.YOLO_WEIGHTS):
            try:
                self.yolo_session = ort.InferenceSession(self.YOLO_WEIGHTS)
                self.log.info("yolo_weights_cargados", path=self.YOLO_WEIGHTS)
            except Exception as e:
                self.log.warning("yolo_load_falló_usando_heuristica", err=str(e))

    # ---------- detección humo/llama (fusion de eventos multi-sensor) ----------
    def detect_humo_llama(self, eventos: list[dict]) -> dict:
        """Heurística calibrada para Etapa 0.PRE.

        Cuando existan weights YOLOv8 fine-tuned, ese path corre en paralelo
        sobre frames de cámara y se hace ensemble con esta heurística.
        """
        humo_max = 0.0
        co_max = 0.0
        temp_max = 0.0
        llama_uv_max = 0.0
        llama_ir_max = 0.0
        n_frames_llama = 0
        for e in eventos:
            v = e.get("valor_num") or 0
            tipo = e["tipo_lectura"]
            if tipo == "humo_obscuracion":
                humo_max = max(humo_max, v)
            elif tipo == "co_ppm":
                co_max = max(co_max, v)
            elif tipo == "termopar_c" or tipo == "temp_c":
                temp_max = max(temp_max, v)
            elif tipo == "flama_uv":
                llama_uv_max = max(llama_uv_max, v)
            elif tipo == "flama_ir":
                llama_ir_max = max(llama_ir_max, v)
            elif tipo == "imagen_hash":
                meta = e.get("valor_jsonb") or {}
                if meta.get("llama_visible"):
                    n_frames_llama += 1
                humo_max = max(humo_max, meta.get("obscuracion_estimada", 0))

        smoke_detected = humo_max > self.UMBRAL_HUMO_PCT
        flame_detected = (
            llama_uv_max > self.UMBRAL_LLAMA_UV
            or llama_ir_max > self.UMBRAL_LLAMA_UV
            or n_frames_llama >= 2
        )
        # Confianza calibrada (Platt-style aproximación)
        if smoke_detected and flame_detected:
            confianza = min(0.92, 0.5 + 0.4 * math.log10(1 + max(humo_max, 1) / 10))
        elif smoke_detected:
            confianza = min(0.78, 0.4 + 0.3 * math.log10(1 + humo_max / 5))
        elif flame_detected:
            confianza = 0.65
        else:
            confianza = 0.05
        # Penalizar si CO=0 y humo>0 (probable falso positivo tipo Q11 humo teatro)
        if smoke_detected and co_max < 5 and humo_max > 30:
            confianza = max(0.15, confianza - 0.5)

        return {
            "smoke_detected": smoke_detected,
            "flame_detected": flame_detected,
            "humo_max_pct": round(humo_max, 2),
            "co_max_ppm": round(co_max, 2),
            "temp_max_c": round(temp_max, 2),
            "llama_uv_max": round(llama_uv_max, 3),
            "llama_ir_max": round(llama_ir_max, 3),
            "n_eventos": len(eventos),
            "confianza": round(confianza, 4),
        }

    # ---------- P-Flash adaptación NIST PB 79-15 (SVR sobre tasa subida T) -----
    def predict_flashover(self, eventos: list[dict]) -> dict:
        """Estima probabilidad de flashover en horizontes 5/10/25/60 s.

        Implementación inicial: regresión logística sobre tasa subida T y T pico.
        Entrenamiento con sintéticos (Sprint M1 fine-tune); placeholder funcional.
        """
        # Series temporales termopar
        series = sorted(
            [(e["ts"], float(e["valor_num"] or 0)) for e in eventos if e["tipo_lectura"] == "termopar_c"],
            key=lambda x: x[0],
        )
        if len(series) < 4:
            return {
                "h5": 0.0, "h10": 0.0, "h25": 0.0, "h60": 0.0,
                "tasa_subida_c_s": 0.0, "temp_actual_c": 0.0,
                "lead_time_s": None,
                "out_of_distribution": True,
            }
        # Aproximar dT/dt sobre últimos 5 puntos
        ultimos = series[-5:]
        n = len(ultimos)
        t0 = datetime.fromisoformat(ultimos[0][0].replace("Z", "+00:00")).timestamp()
        ts = [(datetime.fromisoformat(p[0].replace("Z", "+00:00")).timestamp() - t0) for p in ultimos]
        ys = [p[1] for p in ultimos]
        # regresión lineal simple
        mean_t = sum(ts) / n
        mean_y = sum(ys) / n
        num = sum((ts[i] - mean_t) * (ys[i] - mean_y) for i in range(n))
        den = sum((ts[i] - mean_t) ** 2 for i in range(n)) or 1e-6
        tasa = num / den  # °C/s
        temp_actual = ys[-1]

        # Probabilidad por horizonte — sigmoide sobre (tasa, temp_actual)
        def sig(x): return 1.0 / (1.0 + math.exp(-x))

        # Coeficientes iniciales (tunear con sintéticos M1)
        h5 = sig(0.5 * tasa + 0.012 * (temp_actual - 100) - 4)
        h10 = sig(0.6 * tasa + 0.014 * (temp_actual - 90) - 3.5)
        h25 = sig(0.8 * tasa + 0.018 * (temp_actual - 70) - 3)
        h60 = sig(0.9 * tasa + 0.022 * (temp_actual - 50) - 2.5)

        # Lead time: si h60>0.7, estima cuándo pasa umbral 600°C
        lead_time = None
        if h60 > 0.7 and tasa > 1.0:
            lead_time = max(0.0, (600.0 - temp_actual) / max(tasa, 0.1))

        return {
            "h5": round(h5, 4),
            "h10": round(h10, 4),
            "h25": round(h25, 4),
            "h60": round(h60, 4),
            "tasa_subida_c_s": round(tasa, 3),
            "temp_actual_c": round(temp_actual, 2),
            "lead_time_s": round(lead_time, 1) if lead_time else None,
            "out_of_distribution": tasa > 50 or temp_actual > 700,
        }

    # ---------- ciclo de inferencia ----------
    def infer_zona(self, zona: dict) -> tuple[int | None, int | None]:
        """Una pasada: detección + flashover + insert en piro_inferencias."""
        zona_id = zona["zona_id"]
        eventos = self.fetch_eventos_recientes(zona_id=zona_id, ventana_s=8, limite=400)
        if not eventos:
            return None, None
        ids = [e["evento_id"] for e in eventos]
        ventana_ini = eventos[-1]["ts"]
        ventana_fin = eventos[0]["ts"]

        # Inferencia 1 — detección humo/llama
        with self.measure_latency() as t_lat:
            det = self.detect_humo_llama(eventos)
        det_id = self.insert_inferencia(
            tipo_inferencia="detect_humo" if det["smoke_detected"] else "detect_baseline",
            resultado=det,
            zona_id=zona_id,
            confianza=det["confianza"],
            latencia_ms=t_lat(),
            eventos_basados_ids=ids[:50],
            ventana_ts_ini=ventana_ini,
            ventana_ts_fin=ventana_fin,
            trigger_emitido=det["smoke_detected"] and det["flame_detected"],
        )

        # Inferencia 2 — predicción flashover
        with self.measure_latency() as t_lat:
            flash = self.predict_flashover(eventos)
        flash_id = self.insert_inferencia(
            tipo_inferencia="flashover_pred",
            resultado=flash,
            zona_id=zona_id,
            confianza=1.0 - 0.5 if flash.get("out_of_distribution") else 0.85,
            latencia_ms=t_lat(),
            eventos_basados_ids=ids[:50],
            ventana_ts_ini=ventana_ini,
            ventana_ts_fin=ventana_fin,
            trigger_emitido=(flash["h60"] >= 0.7 and (flash.get("lead_time_s") or 999) < 60),
        )
        return det_id, flash_id


async def run_watch(intervalo_s: float = 1.0) -> None:
    agent = AgentePiroIA()
    agent.log.info("piroia_watch_started", intervalo_s=intervalo_s)
    while True:
        zonas = agent.fetch_zonas_activas()
        for z in zonas:
            try:
                agent.infer_zona(z)
            except Exception as e:
                agent.log.error("infer_zona_falló", zona=z["codigo"], err=str(e))
        await asyncio.sleep(intervalo_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="AG-PIROIA — Sprint M1")
    parser.add_argument("--watch", action="store_true", help="Bucle continuo")
    parser.add_argument("--once", action="store_true", help="Una sola inferencia y salir")
    parser.add_argument("--zona", type=int, help="zona_id específica para --once")
    parser.add_argument("--intervalo", type=float, default=1.0, help="Segundos entre inferencias en --watch")
    args = parser.parse_args()

    if args.watch:
        asyncio.run(run_watch(args.intervalo))
    elif args.once:
        agent = AgentePiroIA()
        if args.zona:
            zona = {"zona_id": args.zona, "codigo": f"zona_{args.zona}"}
        else:
            zonas = agent.fetch_zonas_activas()
            zona = zonas[0] if zonas else None
        if zona:
            det, flash = agent.infer_zona(zona)
            print(f"detección_id={det}  flashover_id={flash}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
