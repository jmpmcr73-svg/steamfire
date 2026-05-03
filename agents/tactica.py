"""
SteamFire — Sprint M4 (backend) — AG-TACTICA

Traduce decisiones IGNIS + estado matriz_vida en mensajes accionables para:
  - Telegram BCBRP (<300 chars, ASCII puro)
  - WhatsApp Business (<1024 chars, bullets)
  - ICS XML (compatible NFIRS + EDXL-DE 2.0)
  - Realtime channel `piro_zona_<id>` para dashboard

Etapa 0.PRE: solo loguea mensajes (no envía realmente al BCBRP — eso es Etapa 0.POST tras MOU).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from agents.base import BaseAgent

try:
    import httpx
    HTTPX_OK = True
except ImportError:
    HTTPX_OK = False


class AgenteTactica(BaseAgent):
    AGENTE_CODIGO = "AG-TACTICA"

    def __init__(self) -> None:
        super().__init__()
        self.tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID_BCBRP")
        self.envio_real = os.environ.get("PIRO_TACTICA_ENVIO_REAL", "false").lower() == "true"

    # ---------- formatters ----------
    def fmt_telegram(self, decision: dict, zona_codigo: str) -> str:
        d = decision.get("decision", "n/a").upper()
        ri = decision.get("riesgo_incendio_pct", 0)
        rf = decision.get("riesgo_flashover_pct", 0)
        lt = decision.get("lead_time_estimado_s")
        ppl = decision.get("personas_en_zona", 0)
        lt_str = f" LT={lt}s" if lt else ""
        msg = (
            f"[STEAMFIRE-{d}] zona={zona_codigo} "
            f"RI={ri:.0f}% RF={rf:.0f}%{lt_str} "
            f"personas={ppl}"
        )
        return msg[:300]

    def fmt_whatsapp(self, decision: dict, zona_codigo: str) -> str:
        lines = [
            f"*SteamFire - {decision.get('decision', 'n/a').upper()}*",
            f"Zona: {zona_codigo}",
            f"Riesgo incendio: {decision.get('riesgo_incendio_pct', 0):.0f}%",
            f"Riesgo flashover: {decision.get('riesgo_flashover_pct', 0):.0f}%",
        ]
        lt = decision.get("lead_time_estimado_s")
        if lt:
            lines.append(f"Lead time: {lt}s")
        lines.append(f"Personas en zona: {decision.get('personas_en_zona', 0)}")
        ev = decision.get("evidencia") or {}
        if ev:
            lines.append("")
            lines.append("Evidencia:")
            for k, v in ev.items():
                lines.append(f"  - {k}: {v}")
        acciones = decision.get("acciones_recomendadas") or []
        if acciones:
            lines.append("")
            lines.append("Acciones recomendadas:")
            for a in acciones[:5]:
                lines.append(f"  - {a.get('tipo')} -> {a.get('objetivo')} ({a.get('prioridad')})")
        msg = "\n".join(lines)
        return msg[:1024]

    def fmt_ics_xml(self, decision: dict, zona: dict) -> str:
        """ICS XML compatible EDXL-DE 2.0 para integración CAD bomberos."""
        ts = datetime.now(timezone.utc).isoformat()
        root = ET.Element("EDXLDistribution", {"xmlns": "urn:oasis:names:tc:emergency:EDXL:DE:2.0"})
        ET.SubElement(root, "distributionID").text = f"steamfire-{decision.get('zona_id')}-{int(datetime.now().timestamp())}"
        ET.SubElement(root, "senderID").text = "alejandria-steamlabs"
        ET.SubElement(root, "dateTimeSent").text = ts
        ET.SubElement(root, "distributionStatus").text = "Actual"
        ET.SubElement(root, "distributionType").text = "Alert"
        contentObject = ET.SubElement(root, "contentObject")
        contentDescription = ET.SubElement(contentObject, "contentDescription")
        contentDescription.text = (
            f"SteamFire {decision.get('decision', 'n/a').upper()} "
            f"zona={zona.get('codigo')}"
        )
        xmlContent = ET.SubElement(contentObject, "xmlContent")
        embedded = ET.SubElement(xmlContent, "incident")
        ET.SubElement(embedded, "type").text = "fire_detection"
        ET.SubElement(embedded, "severity").text = decision.get("decision", "monitoreo")
        ET.SubElement(embedded, "zone").text = zona.get("codigo", "")
        ET.SubElement(embedded, "personsAtRisk").text = str(decision.get("personas_en_zona", 0))
        ET.SubElement(embedded, "fireRiskPct").text = str(decision.get("riesgo_incendio_pct", 0))
        ET.SubElement(embedded, "flashoverRiskPct").text = str(decision.get("riesgo_flashover_pct", 0))
        if decision.get("lead_time_estimado_s"):
            ET.SubElement(embedded, "flashoverLeadTimeSec").text = str(decision["lead_time_estimado_s"])
        return ET.tostring(root, encoding="unicode")

    # ---------- envío canales ----------
    async def send_telegram(self, mensaje: str) -> bool:
        if not (self.tg_token and self.tg_chat_id and HTTPX_OK and self.envio_real):
            self.log.info("telegram_dry_run", mensaje=mensaje)
            return False
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.post(url, json={"chat_id": self.tg_chat_id, "text": mensaje})
                self.log.info("telegram_sent", status=r.status_code)
                return r.status_code == 200
            except Exception as e:
                self.log.error("telegram_falló", err=str(e))
                return False

    # ---------- ciclo zona ----------
    async def procesar_decision_zona(self, zona: dict, ignis_inf: dict) -> None:
        decision = ignis_inf.get("resultado") or {}
        if decision.get("decision") in (None, "monitoreo"):
            return  # nada que comunicar
        zona_codigo = zona.get("codigo", f"zona_{zona['zona_id']}")
        tg_msg = self.fmt_telegram(decision, zona_codigo)
        wa_msg = self.fmt_whatsapp(decision, zona_codigo)
        ics = self.fmt_ics_xml(decision, zona)

        # Insert inferencia TACTICA con los 3 formatos
        self.insert_inferencia(
            tipo_inferencia="tactica_alerta",
            resultado={
                "decision_origen": decision.get("decision"),
                "telegram": tg_msg,
                "whatsapp": wa_msg,
                "ics_xml": ics,
                "envio_real": self.envio_real,
            },
            zona_id=zona["zona_id"],
            confianza=0.99,
            trigger_emitido=True,
        )

        # Envío real (solo si activado en Etapa 0.POST tras MOU)
        await self.send_telegram(tg_msg)


async def run_watch(intervalo_s: float = 2.0) -> None:
    agent = AgenteTactica()
    agent.log.info("tactica_watch_started", intervalo_s=intervalo_s, envio_real=agent.envio_real)
    last_seen_inf_id = 0
    while True:
        zonas = {z["zona_id"]: z for z in agent.fetch_zonas_activas()}
        # Buscar nuevas decisiones IGNIS
        resp = (
            agent.sb.table("piro_inferencias")
            .select("inferencia_id, zona_id, resultado, ts")
            .eq("agente_codigo", "AG-IGNIS")
            .eq("tipo_inferencia", "ignis_decision")
            .gt("inferencia_id", last_seen_inf_id)
            .order("inferencia_id", desc=False)
            .limit(20)
            .execute()
        )
        for inf in (resp.data or []):
            last_seen_inf_id = max(last_seen_inf_id, inf["inferencia_id"])
            zona = zonas.get(inf["zona_id"])
            if not zona:
                continue
            try:
                await agent.procesar_decision_zona(zona, inf)
            except Exception as e:
                agent.log.error("procesar_decision_falló", err=str(e))
        await asyncio.sleep(intervalo_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="AG-TACTICA — Sprint M4 backend")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--intervalo", type=float, default=2.0)
    args = parser.parse_args()
    if args.watch:
        asyncio.run(run_watch(args.intervalo))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
