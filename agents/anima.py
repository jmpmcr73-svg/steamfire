"""
SteamFire — Sprint M2 — AG-ANIMA

Matriz de vidas: detección, conteo y tracking de personas usando mmWave 60GHz
(HLK-LD2410B hobbyist / TI IWR6843 profesional) + cámara térmica (FLIR/Optris).

Pipeline:
  1. Lectura point-cloud de piro_eventos (tipo='mmwave_pcl')
  2. Filtrado SNR + clustering DBSCAN sobre (x, y) → tracks
  3. Asociación con tracks previos (greedy nearest neighbor con coste euclídeo + velocidad)
  4. Update Kalman 2D (estado [x, y, vx, vy]) con filterpy
  5. Inferencia de postura (de_pie/sentado/tumbado/caido) — placeholder Etapa 0
  6. Insert en piro_matriz_vida con confianza ponderada por num fuentes

Etapa 0.PRE: usa eventos sintéticos del simulator.
Etapa 0.POST: lee /dev/ttyUSB del HLK-LD2410B y frames térmicos vía gRPC del Jetson.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os

from agents.base import BaseAgent

try:
    from sklearn.cluster import DBSCAN
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    from filterpy.kalman import KalmanFilter
    import numpy as np
    KALMAN_OK = True
except ImportError:
    KALMAN_OK = False


class TrackKalman:
    """Track Kalman 2D — estado [x, y, vx, vy], obs [x, y]."""

    def __init__(self, track_id: int, x0: float, y0: float, dt: float = 0.5):
        self.track_id = track_id
        self.dt = dt
        self.frames_visto = 1
        self.frames_perdido = 0
        if KALMAN_OK:
            self.kf = KalmanFilter(dim_x=4, dim_z=2)
            self.kf.F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]])
            self.kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
            self.kf.R *= 0.05    # ruido medición pequeño
            self.kf.Q *= 0.01    # ruido proceso pequeño
            self.kf.x = np.array([x0, y0, 0, 0]).reshape(4, 1)
            self.kf.P *= 1.0
        else:
            self.x, self.y, self.vx, self.vy = x0, y0, 0.0, 0.0

    def predict(self) -> tuple[float, float]:
        if KALMAN_OK:
            self.kf.predict()
            return float(self.kf.x[0]), float(self.kf.x[1])
        else:
            self.x += self.vx * self.dt
            self.y += self.vy * self.dt
            return self.x, self.y

    def update(self, x: float, y: float) -> None:
        if KALMAN_OK:
            self.kf.update(np.array([x, y]).reshape(2, 1))
        else:
            new_vx = (x - self.x) / self.dt
            new_vy = (y - self.y) / self.dt
            self.vx = 0.7 * self.vx + 0.3 * new_vx
            self.vy = 0.7 * self.vy + 0.3 * new_vy
            self.x, self.y = x, y
        self.frames_visto += 1
        self.frames_perdido = 0

    def state(self) -> dict:
        if KALMAN_OK:
            x, y, vx, vy = float(self.kf.x[0]), float(self.kf.x[1]), float(self.kf.x[2]), float(self.kf.x[3])
        else:
            x, y, vx, vy = self.x, self.y, self.vx, self.vy
        return {
            "track_id": self.track_id,
            "x_m": round(x, 3),
            "y_m": round(y, 3),
            "vx": round(vx, 3),
            "vy": round(vy, 3),
            "postura": "de_pie",  # postura inferida en Etapa 1 con CNN sobre térmica
            "certeza": min(0.95, 0.4 + 0.06 * self.frames_visto),
        }


class AgenteAnima(BaseAgent):
    AGENTE_CODIGO = "AG-ANIMA"

    DBSCAN_EPS = 0.45         # m — radio cluster persona (típico HLK-LD2410B)
    DBSCAN_MIN_SAMPLES = 3
    SNR_MIN = 12.0
    MAX_FRAMES_PERDIDO = 4    # 2 segundos a 2Hz

    def __init__(self) -> None:
        super().__init__()
        self.tracks_por_zona: dict[int, list[TrackKalman]] = {}
        self.next_track_id_por_zona: dict[int, int] = {}

    # ---------- procesamiento point cloud ----------
    def cluster_points(self, points: list[dict]) -> list[tuple[float, float]]:
        """Filtra por SNR y agrupa con DBSCAN. Devuelve centroides (x, y)."""
        if not points:
            return []
        filtrados = [(p["x"], p["y"]) for p in points if p.get("snr", 0) >= self.SNR_MIN]
        if len(filtrados) < self.DBSCAN_MIN_SAMPLES:
            return []
        if not SKLEARN_OK:
            # fallback ingenuo: una zona con todos los puntos
            x_avg = sum(p[0] for p in filtrados) / len(filtrados)
            y_avg = sum(p[1] for p in filtrados) / len(filtrados)
            return [(x_avg, y_avg)]
        import numpy as np
        X = np.array(filtrados)
        db = DBSCAN(eps=self.DBSCAN_EPS, min_samples=self.DBSCAN_MIN_SAMPLES).fit(X)
        centroides = []
        for label in set(db.labels_):
            if label == -1:
                continue
            mask = db.labels_ == label
            cx = float(X[mask, 0].mean())
            cy = float(X[mask, 1].mean())
            centroides.append((cx, cy))
        return centroides

    # ---------- asociación greedy ----------
    def associate(self, zona_id: int, centroides: list[tuple[float, float]]) -> None:
        tracks = self.tracks_por_zona.setdefault(zona_id, [])
        # predict
        for t in tracks:
            t.predict()
        # asociar greedy por distancia
        usados_centroides: set[int] = set()
        usados_tracks: set[int] = set()
        pares: list[tuple[float, int, int]] = []
        for ti, t in enumerate(tracks):
            tx, ty = (t.kf.x[0], t.kf.x[1]) if KALMAN_OK else (t.x, t.y)
            tx, ty = float(tx), float(ty)
            for ci, (cx, cy) in enumerate(centroides):
                d = math.hypot(cx - tx, cy - ty)
                if d < 0.8:  # ventana asociación 80cm
                    pares.append((d, ti, ci))
        pares.sort(key=lambda p: p[0])
        for d, ti, ci in pares:
            if ti in usados_tracks or ci in usados_centroides:
                continue
            cx, cy = centroides[ci]
            tracks[ti].update(cx, cy)
            usados_tracks.add(ti)
            usados_centroides.add(ci)
        # tracks no actualizados
        for ti, t in enumerate(tracks):
            if ti not in usados_tracks:
                t.frames_perdido += 1
        # nuevos tracks para centroides no asociados
        next_id = self.next_track_id_por_zona.setdefault(zona_id, 1)
        for ci, (cx, cy) in enumerate(centroides):
            if ci not in usados_centroides:
                tracks.append(TrackKalman(track_id=next_id, x0=cx, y0=cy))
                next_id += 1
        self.next_track_id_por_zona[zona_id] = next_id
        # eliminar tracks perdidos
        self.tracks_por_zona[zona_id] = [t for t in tracks if t.frames_perdido <= self.MAX_FRAMES_PERDIDO]

    # ---------- ciclo principal ----------
    def update_zona(self, zona: dict) -> int | None:
        zona_id = zona["zona_id"]
        eventos = self.fetch_eventos_recientes(
            zona_id=zona_id, ventana_s=2, limite=20, tipo_lectura="mmwave_pcl"
        )
        if not eventos:
            return None
        # Tomar el más reciente
        ev_pcl = eventos[0]
        points = (ev_pcl.get("valor_jsonb") or {}).get("points", [])
        with self.measure_latency() as t_lat:
            centroides = self.cluster_points(points)
            self.associate(zona_id, centroides)
            tracks_estables = [t for t in self.tracks_por_zona[zona_id] if t.frames_visto >= 2]
            personas_state = [t.state() for t in tracks_estables]

        # Lectura humo/T para incluir en matriz_vida
        eventos_amb = self.fetch_eventos_recientes(zona_id=zona_id, ventana_s=3, limite=80)
        humo = max((e.get("valor_num") or 0) for e in eventos_amb if e["tipo_lectura"] == "humo_obscuracion") if eventos_amb else 0
        co = max((e.get("valor_num") or 0) for e in eventos_amb if e["tipo_lectura"] == "co_ppm") if eventos_amb else 0
        temp = max((e.get("valor_num") or 0) for e in eventos_amb if e["tipo_lectura"] in ("temp_c", "termopar_c")) if eventos_amb else 0

        fuentes = ["mmwave"]
        # En Etapa 0.POST se sumará "termica" y la confianza sube
        confianza = 0.6 if len(fuentes) == 1 else (0.85 if len(fuentes) == 2 else 0.95)

        # Insert matriz_vida
        payload = {
            "zona_id": zona_id,
            "num_personas": len(personas_state),
            "personas": personas_state,
            "obscuracion_pct": float(humo) if humo else None,
            "co_ppm": float(co) if co else None,
            "temp_max_c": float(temp) if temp else None,
            "fuentes_consultadas": fuentes,
            "confianza_global": confianza,
            "fuente": "real",
        }
        resp = self.sb.table("piro_matriz_vida").insert(payload).execute()
        matriz_id = resp.data[0]["matriz_id"]

        # También loguear como inferencia ANIMA
        self.insert_inferencia(
            tipo_inferencia="life_count",
            resultado={
                "num_personas": len(personas_state),
                "matriz_id": matriz_id,
                "personas": personas_state,
                "humo_pct": float(humo) if humo else 0,
            },
            zona_id=zona_id,
            confianza=confianza,
            latencia_ms=t_lat(),
            trigger_emitido=len(personas_state) > 0 and (humo or 0) > 60,
        )
        return matriz_id


async def run_watch(intervalo_s: float = 0.5) -> None:
    agent = AgenteAnima()
    agent.log.info("anima_watch_started", intervalo_s=intervalo_s)
    while True:
        zonas = agent.fetch_zonas_activas()
        for z in zonas:
            try:
                agent.update_zona(z)
            except Exception as e:
                agent.log.error("update_zona_falló", zona=z["codigo"], err=str(e))
        await asyncio.sleep(intervalo_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="AG-ANIMA — Sprint M2")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--intervalo", type=float, default=0.5)
    args = parser.parse_args()
    if args.watch:
        asyncio.run(run_watch(args.intervalo))
    elif args.once:
        agent = AgenteAnima()
        for z in agent.fetch_zonas_activas():
            mid = agent.update_zona(z)
            print(f"zona={z['codigo']} matriz_id={mid} tracks={len(agent.tracks_por_zona.get(z['zona_id'], []))}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
