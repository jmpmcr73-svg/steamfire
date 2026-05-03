.PHONY: help install simulate piroia anima ignis tactica all-agents bot dashboard-dev dashboard-build verify

help:
	@echo "SteamFire — Etapa 0.PRE — comandos disponibles"
	@echo ""
	@echo "  make install            crear venv + instalar deps Python"
	@echo "  make verify             chequear estado Kronos (briefing, audit, agentes)"
	@echo ""
	@echo "  make simulate-list      listar escenarios disponibles"
	@echo "  make simulate s=Q01-VELA-BASELINE    correr escenario sintetico (rapido)"
	@echo "  make simulate-rt s=Q12-FULL-LAB      correr escenario en tiempo real"
	@echo ""
	@echo "  make piroia             AG-PIROIA en bucle (--watch)"
	@echo "  make anima              AG-ANIMA en bucle (--watch)"
	@echo "  make ignis              AG-IGNIS en bucle (--watch)"
	@echo "  make tactica            AG-TACTICA en bucle (--watch)"
	@echo "  make all-agents         lanza los 4 agentes en paralelo"
	@echo ""
	@echo "  make bot                Telegram bot polling"
	@echo "  make dashboard-dev      dashboard Next.js dev mode"
	@echo "  make dashboard-build    build production"

install:
	python -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Activa el venv: source .venv/bin/activate"
	@echo "Copia .env.example -> .env y rellena las claves"

verify:
	@./.venv/bin/python -c "from supabase import create_client; import os; from dotenv import load_dotenv; load_dotenv(); sb=create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY']); r=sb.table('v_piro_briefing').select('*').single().execute(); print(r.data)"

simulate-list:
	./.venv/bin/python -m simulator.synthetic_generator --list

# Uso: make simulate s=Q01-VELA-BASELINE
simulate:
	./.venv/bin/python -m simulator.synthetic_generator --scenario $(s)

simulate-rt:
	./.venv/bin/python -m simulator.synthetic_generator --scenario $(s) --realtime

piroia:
	./.venv/bin/python -m agents.piroia --watch

anima:
	./.venv/bin/python -m agents.anima --watch

ignis:
	./.venv/bin/python -m agents.ignis --watch

tactica:
	./.venv/bin/python -m agents.tactica --watch

all-agents:
	@echo "Lanzando los 4 agentes en paralelo..."
	./.venv/bin/python -m agents.piroia --watch & \
	./.venv/bin/python -m agents.anima --watch & \
	./.venv/bin/python -m agents.ignis --watch & \
	./.venv/bin/python -m agents.tactica --watch & \
	wait

bot:
	./.venv/bin/python -m bots.telegram_bot

dashboard-dev:
	cd dashboard && npm run dev

dashboard-build:
	cd dashboard && npm run build

dashboard-install:
	cd dashboard && npm install
