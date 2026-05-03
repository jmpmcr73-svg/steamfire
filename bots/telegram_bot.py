"""
SteamFire — Bot Telegram BCBRP

Comandos disponibles:
  /briefing  — estado actual del sistema PIRO (v_piro_briefing)
  /zonas     — listado de zonas activas con estado
  /quemas    — quemas planificadas y en curso
  /alertas   — últimas 5 acciones shadow
  /help      — ayuda

Este bot también RECIBE alertas push desde AG-TACTICA cuando se setea
PIRO_TACTICA_ENVIO_REAL=true en .env.

Uso:
    python -m bots.telegram_bot
"""
from __future__ import annotations

import os

import structlog
from dotenv import load_dotenv
from supabase import Client, create_client

try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        ContextTypes,
    )
    TG_OK = True
except ImportError:
    TG_OK = False

load_dotenv()
log = structlog.get_logger()

sb: Client | None = None


def get_supabase() -> Client:
    global sb
    if sb is None:
        sb = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return sb


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "SteamFire BCBRP bot. Comandos: /briefing /zonas /quemas /alertas /help"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/briefing  estado general\n"
        "/zonas     listado zonas\n"
        "/quemas    quemas planificadas/en curso\n"
        "/alertas   últimas 5 acciones shadow\n"
    )
    await update.message.reply_text(text)


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sb = get_supabase()
    r = sb.table("v_piro_briefing").select("*").single().execute()
    b = r.data or {}
    msg = (
        f"SteamFire briefing\n"
        f"  zonas activas: {b.get('zonas_activas', 0)}\n"
        f"  dispositivos: {b.get('dispositivos_activos', 0)} ({b.get('dispositivos_perdidos', 0)} perdidos)\n"
        f"  quemas: {b.get('quemas_planificadas', 0)} planif · {b.get('quemas_en_curso', 0)} en curso · {b.get('quemas_completadas', 0)} hechas\n"
        f"  eventos / 5min: {b.get('eventos_ult_5min', 0)}\n"
        f"  triggers / 1h: {b.get('triggers_ult_hora', 0)}\n"
        f"  audit: {b.get('audit_entries_total', 0)} entries"
    )
    await update.message.reply_text(msg)


async def cmd_zonas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sb = get_supabase()
    r = sb.table("piro_zonas").select("codigo,nombre,tipo,contexto,activo").order("codigo").execute()
    lines = ["zonas registradas:"]
    for z in r.data or []:
        flag = "ON" if z["activo"] else "OFF"
        lines.append(f"  [{flag}] {z['codigo']}  {z['tipo']:<12}  {z['contexto']}")
    await update.message.reply_text("\n".join(lines)[:3500])


async def cmd_quemas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sb = get_supabase()
    r = (
        sb.table("piro_quemas")
        .select("codigo,tipo,fase,estado")
        .eq("proyecto", "steamfire")
        .order("codigo")
        .limit(20)
        .execute()
    )
    lines = ["quemas:"]
    for q in r.data or []:
        lines.append(f"  {q['codigo']:<22} {q['tipo']:<22} fase={q['fase']:<14} {q['estado']}")
    await update.message.reply_text("\n".join(lines)[:3500])


async def cmd_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sb = get_supabase()
    r = (
        sb.table("v_piro_acciones_recientes")
        .select("ts,tipo_accion,objetivo,prioridad,zona_codigo,justificacion")
        .limit(5)
        .execute()
    )
    if not r.data:
        await update.message.reply_text("Sin acciones shadow recientes.")
        return
    lines = ["últimas 5 acciones shadow:"]
    for a in r.data:
        lines.append(f"\n[{a['prioridad'].upper()}] {a['tipo_accion']} -> {a['objetivo']}")
        lines.append(f"  zona={a['zona_codigo']}  {a['ts'][:19]}")
        lines.append(f"  {a['justificacion']}")
    await update.message.reply_text("\n".join(lines)[:3500])


def main() -> None:
    if not TG_OK:
        log.error("telegram_lib_missing", hint="pip install python-telegram-bot")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN no seteado")
        return
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("zonas", cmd_zonas))
    app.add_handler(CommandHandler("quemas", cmd_quemas))
    app.add_handler(CommandHandler("alertas", cmd_alertas))
    log.info("steamfire_bot_started")
    app.run_polling()


if __name__ == "__main__":
    main()
