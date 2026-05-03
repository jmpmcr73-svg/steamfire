"""
SteamFire — Base agent class.

Helpers comunes a IGNIS, PIROIA, ANIMA, TACTICA, PIROCHEM, PIROACT.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any

import structlog
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

log = structlog.get_logger()


class BaseAgent:
    """Clase base para agentes PIRO — opera sobre Kronos (`zsmlntktqisiclzaxoky`)."""

    AGENTE_CODIGO: str = "BASE"

    def __init__(self) -> None:
        self.sb: Client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
        self.shadow_mode: bool = os.environ.get("PIRO_SHADOW_MODE", "true").lower() == "true"
        self.etapa: str = os.environ.get("PIRO_ETAPA", "0_pre")
        self.log = log.bind(agente=self.AGENTE_CODIGO, etapa=self.etapa)
        self._cargar_config()

    def _cargar_config(self) -> None:
        """Lee `idworld_agentes` para traer modelo IA y prompt sistema."""
        resp = (
            self.sb.table("idworld_agentes")
            .select("agente_id, modelo_ia, system_prompt, config_json")
            .eq("agente_id", self.AGENTE_CODIGO)
            .single()
            .execute()
        )
        if not resp.data:
            self.log.warning("agente_no_registrado_en_kronos")
            self.modelo_ia = None
            self.system_prompt = ""
            self.config = {}
            return
        self.modelo_ia = resp.data["modelo_ia"]
        self.system_prompt = resp.data["system_prompt"] or ""
        self.config = resp.data.get("config_json") or {}
        self.log.info("config_cargada", modelo=self.modelo_ia)

    @contextmanager
    def measure_latency(self):
        """Context manager para medir latencia ms — uso `with self.measure_latency() as t: ... ; print(t())`."""
        start = time.perf_counter()
        elapsed = {"ms": 0}
        def get():
            return elapsed["ms"]
        try:
            yield get
        finally:
            elapsed["ms"] = int((time.perf_counter() - start) * 1000)

    def insert_inferencia(
        self,
        tipo_inferencia: str,
        resultado: dict,
        zona_id: int | None = None,
        confianza: float | None = None,
        latencia_ms: int | None = None,
        eventos_basados_ids: list[int] | None = None,
        ventana_ts_ini: str | None = None,
        ventana_ts_fin: str | None = None,
        trigger_emitido: bool = False,
        quema_id: int | None = None,
        notas: str | None = None,
    ) -> int:
        """Inserta en `piro_inferencias` y devuelve el inferencia_id."""
        payload = {
            "agente_codigo": self.AGENTE_CODIGO,
            "agente_id": self.AGENTE_CODIGO,
            "zona_id": zona_id,
            "tipo_inferencia": tipo_inferencia,
            "resultado": resultado,
            "confianza": confianza,
            "modelo_usado": self.modelo_ia,
            "latencia_ms": latencia_ms,
            "ventana_ts_ini": ventana_ts_ini,
            "ventana_ts_fin": ventana_ts_fin,
            "eventos_basados_ids": eventos_basados_ids,
            "shadow_mode": self.shadow_mode,
            "trigger_emitido": trigger_emitido,
            "quema_id": quema_id,
            "notas": notas,
            "fuente": "real",  # se sobreescribe a sintetico desde el simulador si aplica
        }
        # filtrar None para que defaults DB tomen efecto
        payload = {k: v for k, v in payload.items() if v is not None}
        resp = self.sb.table("piro_inferencias").insert(payload).execute()
        inf_id = resp.data[0]["inferencia_id"]
        self.log.info(
            "inferencia",
            tipo=tipo_inferencia,
            confianza=confianza,
            latencia_ms=latencia_ms,
            trigger=trigger_emitido,
        )
        return inf_id

    def emit_accion_simulada(
        self,
        tipo_accion: str,
        objetivo: str,
        prioridad: str,
        justificacion: str,
        zona_id: int | None = None,
        parametros: dict | None = None,
        inferencia_id: int | None = None,
        quema_id: int | None = None,
        habria_evitado_dano: str | None = None,
    ) -> int:
        """Inserta en `piro_acciones_simuladas`. Etapa 0 = ejecutada=False siempre."""
        if not self.shadow_mode:
            self.log.error("shadow_mode_desactivado_en_etapa_0", aborting=True)
            raise RuntimeError("Etapa 0 debe operar shadow_mode=true. Aborting.")
        payload = {
            "zona_id": zona_id,
            "agente_codigo": self.AGENTE_CODIGO,
            "tipo_accion": tipo_accion,
            "objetivo": objetivo,
            "parametros": parametros or {},
            "justificacion": justificacion,
            "prioridad": prioridad,
            "ejecutada": False,
            "shadow_mode": True,
            "habria_evitado_dano": habria_evitado_dano,
            "inferencia_id": inferencia_id,
            "quema_id": quema_id,
        }
        resp = self.sb.table("piro_acciones_simuladas").insert(payload).execute()
        accion_id = resp.data[0]["accion_id"]
        self.log.warning(
            "accion_shadow",
            accion_id=accion_id,
            tipo=tipo_accion,
            objetivo=objetivo,
            prioridad=prioridad,
        )
        return accion_id

    def fetch_eventos_recientes(
        self,
        zona_id: int | None = None,
        ventana_s: int = 10,
        limite: int = 500,
        tipo_lectura: str | None = None,
    ) -> list[dict]:
        """Lee eventos recientes de la zona en la ventana dada."""
        from datetime import datetime, timedelta, timezone
        desde = (datetime.now(timezone.utc) - timedelta(seconds=ventana_s)).isoformat()
        q = self.sb.table("piro_eventos").select("*").gte("ts", desde).order("ts", desc=True).limit(limite)
        if zona_id is not None:
            q = q.eq("zona_id", zona_id)
        if tipo_lectura:
            q = q.eq("tipo_lectura", tipo_lectura)
        return q.execute().data or []

    def fetch_inferencias_recientes(
        self,
        zona_id: int | None = None,
        ventana_s: int = 10,
        agentes: list[str] | None = None,
        limite: int = 100,
    ) -> list[dict]:
        from datetime import datetime, timedelta, timezone
        desde = (datetime.now(timezone.utc) - timedelta(seconds=ventana_s)).isoformat()
        q = (
            self.sb.table("piro_inferencias")
            .select("*")
            .gte("ts", desde)
            .order("ts", desc=True)
            .limit(limite)
        )
        if zona_id is not None:
            q = q.eq("zona_id", zona_id)
        if agentes:
            q = q.in_("agente_codigo", agentes)
        return q.execute().data or []

    def fetch_matriz_vida_actual(self, zona_id: int) -> dict | None:
        resp = (
            self.sb.table("piro_matriz_vida")
            .select("*")
            .eq("zona_id", zona_id)
            .order("ts", desc=True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def fetch_zonas_activas(self) -> list[dict]:
        return (
            self.sb.table("piro_zonas")
            .select("zona_id, codigo, nombre, area_m2, volumen_m3, contexto")
            .eq("activo", True)
            .execute()
            .data or []
        )
