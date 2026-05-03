"use client";

import type { Briefing } from "@/lib/types";

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="card flex flex-col">
      <span className="text-[0.7rem] uppercase tracking-wide text-[var(--text-2)]">
        {label}
      </span>
      <span className="text-3xl font-semibold mt-1">{value}</span>
      {sub && (
        <span className="text-[0.7rem] text-[var(--text-2)] mt-1">{sub}</span>
      )}
    </div>
  );
}

export default function BriefingPanel({ briefing }: { briefing: Briefing | null }) {
  if (!briefing) {
    return (
      <div className="card text-[var(--text-2)]">Cargando briefing…</div>
    );
  }
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <Stat label="zonas activas" value={briefing.zonas_activas} />
      <Stat
        label="dispositivos"
        value={briefing.dispositivos_activos}
        sub={`${briefing.dispositivos_perdidos} perdidos`}
      />
      <Stat
        label="quemas"
        value={briefing.quemas_planificadas}
        sub={`${briefing.quemas_en_curso} en curso · ${briefing.quemas_completadas} hechas`}
      />
      <Stat
        label="eventos / 5min"
        value={briefing.eventos_ult_5min}
      />
      <Stat
        label="triggers / 1h"
        value={briefing.triggers_ult_hora}
      />
      <Stat
        label="audit log"
        value={briefing.audit_entries_total}
        sub="hash-chained inmutable"
      />
    </div>
  );
}
