"""
SteamFire — Sprint M0.5 — Generador sintético de eventos

Lee scenarios.json y genera streams realistas en piro_eventos siguiendo:
  - Modelo Heskestad t-squared para HRR(t) = alpha * t^2
  - Firmas químicas por material (CO/CO2/particulas)
  - mmWave point clouds para personas según trayectoria
  - Jitter realista en sensores hobbyist (MQ-2/MQ-7/DHT22)

Permite probar el pipeline IA completo SIN un solo sensor real.

Uso:
    python -m simulator.synthetic_generator --scenario Q01-VELA-BASELINE
    python -m simulator.synthetic_generator --scenario Q12-FULL-LAB --realtime
    python -m simulator.synthetic_generator --list
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

log = structlog.get_logger()

SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"


def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


@dataclass
class FirePhysics:
    """Modelo simplificado Heskestad t-squared + radiación + capa caliente."""

    alpha: float                      # m/s^2 (slow=0.0029, medium=0.0117, fast=0.047, ultrafast=0.187)
    hrr_pico_kw: float
    tiempo_pico_s: float
    decay_constant_s: float = 90.0    # tiempo característico de extinción
    pre_ignicion_s: float = 0.0
    flashover_t_s: float | None = None

    def hrr_kw(self, t: float) -> float:
        if t < self.pre_ignicion_s:
            return 0.0
        t_eff = t - self.pre_ignicion_s
        if t_eff <= self.tiempo_pico_s:
            return min(self.alpha * t_eff * t_eff, self.hrr_pico_kw)
        # decaimiento exponencial post-pico
        delta = t_eff - self.tiempo_pico_s
        return self.hrr_pico_kw * math.exp(-delta / self.decay_constant_s)

    def temp_capa_caliente_c(self, t: float, volumen_m3: float, t_ambiente: float = 26.0) -> float:
        """Aproximación simple del modelo de McCaffrey/Quintiere para capa caliente."""
        hrr = self.hrr_kw(t)
        if hrr < 0.05:
            return t_ambiente
        # delta_T proporcional a HRR^(2/3) / volumen^(1/3)
        delta = 6.85 * (hrr ** (2 / 3)) / (volumen_m3 ** (1 / 3))
        # caps físicos razonables para Etapa 0 lab
        return min(t_ambiente + delta, 720.0)

    def radiacion_kw_m2(self, t: float, distancia_m: float = 1.0) -> float:
        hrr = self.hrr_kw(t)
        # fracción radiativa ~30% para combustibles típicos
        return (0.30 * hrr) / (4 * math.pi * max(distancia_m, 0.3) ** 2)


@dataclass
class Particula:
    """Productos de combustión por material — simplificado para Etapa 0."""

    obscuracion_pct_max: float
    co_ppm_max: float
    co2_ppm_max: float
    rise_constant_s: float = 30.0
    humo_teatro: bool = False  # Q11 — humo sin combustión

    def obscuracion_pct(self, t: float, hrr: float, hrr_pico: float) -> float:
        if hrr_pico < 0.01:
            return 0.0
        progreso = min(hrr / hrr_pico, 1.0)
        # ramp-up no lineal proporcional a HRR
        return self.obscuracion_pct_max * (progreso ** 0.7)

    def co_ppm(self, t: float, hrr: float, hrr_pico: float) -> float:
        if self.humo_teatro:
            return 0.0
        if hrr_pico < 0.01:
            return 0.0
        progreso = min(hrr / hrr_pico, 1.0)
        return self.co_ppm_max * progreso

    def co2_ppm(self, t: float, hrr: float, hrr_pico: float, ambiente: float = 420.0) -> float:
        if hrr_pico < 0.01:
            return ambiente
        progreso = min(hrr / hrr_pico, 1.0)
        return ambiente + (self.co2_ppm_max - ambiente) * progreso


@dataclass
class TrayectoriaPersona:
    track_id: int
    x_m: float
    y_m: float
    vx: float = 0.0
    vy: float = 0.0
    postura: str = "de_pie"

    def step(self, dt: float, modo: str, zona_dim: tuple[float, float]) -> None:
        if modo == "estatico_centro":
            return
        if modo == "lineal_lento":
            self.vx, self.vy = 0.15, 0.0
        elif modo == "cruce_diagonal":
            self.vx, self.vy = 0.25, 0.20 if self.track_id % 2 == 0 else -0.20
        elif modo == "alejandose":
            self.vx, self.vy = -0.30, 0.0
        elif modo == "evacuacion_lenta":
            self.vx, self.vy = 0.40, 0.10
        # rebote en bordes
        if self.x_m + self.vx * dt < 0.2 or self.x_m + self.vx * dt > zona_dim[0] - 0.2:
            self.vx = -self.vx
        if self.y_m + self.vy * dt < 0.2 or self.y_m + self.vy * dt > zona_dim[1] - 0.2:
            self.vy = -self.vy
        self.x_m += self.vx * dt
        self.y_m += self.vy * dt


def jitter(valor: float, pct: float = 0.05) -> float:
    """Ruido gaussiano proporcional para sensores hobbyist."""
    if valor == 0:
        return 0.0
    return valor * (1.0 + random.gauss(0, pct))


@dataclass
class SimulatorState:
    sb: Client
    scenario: dict
    zona_id: int
    quema_id: int | None
    dispositivos: dict[str, int]      # codigo -> dispositivo_id
    zona_dim: tuple[float, float]
    volumen_m3: float
    physics: FirePhysics
    particulas: Particula
    personas: list[TrayectoriaPersona] = field(default_factory=list)
    eventos_buffer: list[dict] = field(default_factory=list)
    flush_every: int = 50

    async def insert_evento(self, **kwargs) -> None:
        kwargs.setdefault("fuente", "sintetico")
        kwargs.setdefault("calidad", "ok")
        if self.quema_id:
            kwargs.setdefault("quema_id", self.quema_id)
        self.eventos_buffer.append(kwargs)
        if len(self.eventos_buffer) >= self.flush_every:
            await self.flush()

    async def flush(self) -> None:
        if not self.eventos_buffer:
            return
        try:
            self.sb.table("piro_eventos").insert(self.eventos_buffer).execute()
            log.info("flushed", n=len(self.eventos_buffer))
        except Exception as e:
            log.error("flush_failed", err=str(e))
        self.eventos_buffer.clear()


async def setup_state(sb: Client, scenario: dict) -> SimulatorState:
    # zona
    zona_resp = (
        sb.table("piro_zonas")
        .select("zona_id, area_m2, volumen_m3")
        .eq("codigo", scenario["zona_codigo"])
        .single()
        .execute()
    )
    if not zona_resp.data:
        raise SystemExit(f"Zona no encontrada: {scenario['zona_codigo']}")
    zona = zona_resp.data
    zona_id = zona["zona_id"]
    area = float(zona["area_m2"] or 9.0)
    lado = math.sqrt(area)
    volumen = float(zona["volumen_m3"] or 22.5)

    # quema (si existe)
    quema_resp = (
        sb.table("piro_quemas")
        .select("quema_id")
        .eq("codigo", scenario["codigo"])
        .execute()
    )
    quema_id = quema_resp.data[0]["quema_id"] if quema_resp.data else None

    # dispositivos zona
    disp_resp = (
        sb.table("piro_dispositivos")
        .select("dispositivo_id, codigo, tipo")
        .eq("zona_id", zona_id)
        .execute()
    )
    dispositivos = {d["codigo"]: d["dispositivo_id"] for d in disp_resp.data}

    # físicas
    physics = FirePhysics(
        alpha=scenario.get("alpha_fire_growth", 0.0117),
        hrr_pico_kw=scenario["hrr_pico_kw"],
        tiempo_pico_s=scenario.get("tiempo_pico_s", scenario["duracion_s"] * 0.4),
        pre_ignicion_s=scenario.get("fase_pre_ignicion_s", 0.0),
        flashover_t_s=scenario.get("flashover_t_estimado_s"),
    )
    particulas = Particula(
        obscuracion_pct_max=scenario.get("particulas_humo_pct_max", 30),
        co_ppm_max=scenario.get("co_ppm_max", 200),
        co2_ppm_max=scenario.get("co2_ppm_max", 2000),
        humo_teatro=scenario.get("humo_teatro", False),
    )

    # personas
    n = scenario.get("personas_simuladas", 0)
    trayectoria_modo = scenario.get("personas_trayectoria", "estatico_centro")
    personas = []
    for i in range(n):
        personas.append(
            TrayectoriaPersona(
                track_id=i + 1,
                x_m=lado * 0.5 + (0.6 if i else 0),
                y_m=lado * 0.5 - (0.4 if i else 0),
                postura="de_pie",
            )
        )

    # marcar quema como ignicion
    if quema_id:
        sb.table("piro_quemas").update({
            "fase": "ignicion",
            "ts_ignicion": "now()",
        }).eq("quema_id", quema_id).execute()

    return SimulatorState(
        sb=sb,
        scenario=scenario,
        zona_id=zona_id,
        quema_id=quema_id,
        dispositivos=dispositivos,
        zona_dim=(lado, lado),
        volumen_m3=volumen,
        physics=physics,
        particulas=particulas,
        personas=personas,
    )


async def emit_tick(state: SimulatorState, t: float, dt: float) -> None:
    sc = state.scenario
    hrr = state.physics.hrr_kw(t)
    temp = state.physics.temp_capa_caliente_c(t, state.volumen_m3)

    # NODOS HUMO+CO+T (uno por nodo de la zona)
    for codigo, disp_id in state.dispositivos.items():
        if not codigo.startswith("NODO-LAB-"):
            continue
        # MQ-2 humo (% obscuración)
        obs = state.particulas.obscuracion_pct(t, hrr, state.physics.hrr_pico_kw)
        await state.insert_evento(
            ts="now()",
            dispositivo_id=disp_id,
            zona_id=state.zona_id,
            tipo_lectura="humo_obscuracion",
            valor_num=jitter(obs, 0.08),
            unidad="pct",
        )
        # MQ-7 CO
        co = state.particulas.co_ppm(t, hrr, state.physics.hrr_pico_kw)
        await state.insert_evento(
            ts="now()",
            dispositivo_id=disp_id,
            zona_id=state.zona_id,
            tipo_lectura="co_ppm",
            valor_num=jitter(co, 0.10),
            unidad="ppm",
        )
        # CO2
        co2 = state.particulas.co2_ppm(t, hrr, state.physics.hrr_pico_kw)
        await state.insert_evento(
            ts="now()",
            dispositivo_id=disp_id,
            zona_id=state.zona_id,
            tipo_lectura="co2_ppm",
            valor_num=jitter(co2, 0.04),
            unidad="ppm",
        )
        # DHT22 + termopar
        await state.insert_evento(
            ts="now()",
            dispositivo_id=disp_id,
            zona_id=state.zona_id,
            tipo_lectura="temp_c",
            valor_num=jitter(temp, 0.03),
            unidad="C",
        )
        # KY-026 llama (uv) — solo si tiene sensor llama
        if codigo == "NODO-LAB-03":
            llama_uv = sc.get("llama_uv_pico", 0) * min(hrr / max(state.physics.hrr_pico_kw, 0.01), 1.0)
            await state.insert_evento(
                ts="now()",
                dispositivo_id=disp_id,
                zona_id=state.zona_id,
                tipo_lectura="flama_uv",
                valor_num=jitter(llama_uv, 0.12),
                unidad="pu",
            )
        # Termopar K (alta T cerca del fuego)
        await state.insert_evento(
            ts="now()",
            dispositivo_id=disp_id,
            zona_id=state.zona_id,
            tipo_lectura="termopar_c",
            valor_num=jitter(temp + random.uniform(-15, 60), 0.05),
            unidad="C",
        )

    # Pre-ignición gas (Q08)
    if t < state.physics.pre_ignicion_s and "MQ-5" in str(sc):
        gas_lel = sc.get("gas_lel_pre_ignicion_pct", 0) * (t / max(state.physics.pre_ignicion_s, 1))
        nodo_gas = state.dispositivos.get("NODO-LAB-04")
        if nodo_gas:
            await state.insert_evento(
                ts="now()",
                dispositivo_id=nodo_gas,
                zona_id=state.zona_id,
                tipo_lectura="gas_lel",
                valor_num=jitter(gas_lel, 0.08),
                unidad="pct_LEL",
            )

    # mmWave personas → point clouds simulados
    mmwave_id = state.dispositivos.get("MMWAVE-LAB-01") or state.dispositivos.get("MMWAVE-LAB-02")
    if mmwave_id and state.personas:
        modo = sc.get("personas_trayectoria", "estatico_centro")
        for p in state.personas:
            p.step(dt, modo, state.zona_dim)
        # Generar point cloud aproximado (cada persona = ~6-12 puntos en área ~30cm)
        points = []
        for p in state.personas:
            n_pts = random.randint(6, 12)
            for _ in range(n_pts):
                points.append({
                    "x": jitter(p.x_m, 0.05),
                    "y": jitter(p.y_m, 0.05),
                    "vx": jitter(p.vx, 0.20),
                    "vy": jitter(p.vy, 0.20),
                    "snr": random.uniform(15, 35),
                })
        # ruido ambiental (~3 puntos espurios por frame)
        for _ in range(3):
            points.append({
                "x": random.uniform(0, state.zona_dim[0]),
                "y": random.uniform(0, state.zona_dim[1]),
                "vx": 0, "vy": 0,
                "snr": random.uniform(8, 14),
            })
        await state.insert_evento(
            ts="now()",
            dispositivo_id=mmwave_id,
            zona_id=state.zona_id,
            tipo_lectura="mmwave_pcl",
            valor_jsonb={"points": points, "n_targets_estimados": len(state.personas)},
            unidad="pcl",
        )

    # CAM frame hash (simulado)
    cam_id = state.dispositivos.get("CAM-LAB-01") or state.dispositivos.get("WEB-LAB-01")
    if cam_id and t % 1.0 < dt:  # 1 fps
        await state.insert_evento(
            ts="now()",
            dispositivo_id=cam_id,
            zona_id=state.zona_id,
            tipo_lectura="imagen_hash",
            valor_jsonb={
                "frame_id": int(t * 1000),
                "obscuracion_estimada": state.particulas.obscuracion_pct(t, hrr, state.physics.hrr_pico_kw),
                "llama_visible": hrr > 0.5 and not state.particulas.humo_teatro,
            },
            unidad="hash",
        )


async def run_scenario(scenario_code: str, realtime: bool = False, duration_override: float | None = None) -> None:
    with open(SCENARIOS_PATH) as f:
        catalog = json.load(f)
    scenario = next((s for s in catalog["escenarios"] if s["codigo"] == scenario_code), None)
    if not scenario:
        codes = [s["codigo"] for s in catalog["escenarios"]]
        raise SystemExit(f"Escenario no encontrado: {scenario_code}. Disponibles: {codes}")

    sb = get_supabase()
    state = await setup_state(sb, scenario)

    duration = float(duration_override or scenario["duracion_s"])
    dt = 0.5  # 2 Hz tick
    log.info("scenario_started", codigo=scenario_code, duracion_s=duration, zona=scenario["zona_codigo"], realtime=realtime)

    t = 0.0
    while t <= duration:
        await emit_tick(state, t, dt)
        if realtime:
            await asyncio.sleep(dt)
        t += dt

    await state.flush()

    # cerrar quema como documentada
    if state.quema_id:
        sb.table("piro_quemas").update({
            "fase": "documentada",
            "ts_extinguida": "now()",
        }).eq("quema_id", state.quema_id).execute()

    log.info("scenario_done", codigo=scenario_code)


def list_scenarios() -> None:
    with open(SCENARIOS_PATH) as f:
        catalog = json.load(f)
    print(f"{'codigo':<25} {'tipo':<22} {'dur_s':>6} {'personas':>9} {'flashover':<10} {'decision_correcta':<15}")
    print("-" * 100)
    for s in catalog["escenarios"]:
        print(f"{s['codigo']:<25} {s['tipo']:<22} {s['duracion_s']:>6} {s.get('personas_simuladas', 0):>9} "
              f"{str(s.get('flashover_esperado', False)):<10} {s.get('decision_correcta_ignis', 'n/a'):<15}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SteamFire synthetic event generator")
    parser.add_argument("--scenario", help="Código de escenario (ej. Q01-VELA-BASELINE)")
    parser.add_argument("--realtime", action="store_true", help="Emitir en tiempo real (sleep entre ticks)")
    parser.add_argument("--duration", type=float, help="Override duración (segundos)")
    parser.add_argument("--list", action="store_true", help="Listar escenarios disponibles")
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return
    if not args.scenario:
        parser.print_help()
        sys.exit(1)
    asyncio.run(run_scenario(args.scenario, args.realtime, args.duration))


if __name__ == "__main__":
    main()
