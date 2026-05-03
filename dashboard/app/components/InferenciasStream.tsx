"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { Inferencia } from "@/lib/types";

const AGENTE_COLOR: Record<string, string> = {
  "AG-IGNIS": "text-orange-400",
  "AG-PIROIA": "text-sky-400",
  "AG-ANIMA": "text-emerald-400",
  "AG-PIROCHEM": "text-violet-400",
  "AG-PIROACT": "text-rose-400",
  "AG-TACTICA": "text-amber-300",
};

function pillForDecision(decision?: string) {
  if (!decision) return "pill pill-info";
  if (decision === "monitoreo") return "pill pill-ok";
  if (decision === "pre_alerta") return "pill pill-info";
  if (decision === "alerta") return "pill pill-warn";
  if (decision === "critica" || decision === "evacuacion") return "pill pill-crit";
  return "pill pill-info";
}

export default function InferenciasStream() {
  const [items, setItems] = useState<Inferencia[]>([]);

  const reload = async () => {
    const { data } = await supabase
      .from("v_piro_inferencias_recientes")
      .select("*")
      .limit(40);
    setItems((data as Inferencia[]) ?? []);
  };

  useEffect(() => {
    reload();
    const ch = supabase
      .channel("inf_stream")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "piro_inferencias" },
        reload,
      )
      .subscribe();
    return () => {
      supabase.removeChannel(ch);
    };
  }, []);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">Stream de inferencias</h2>
        <span className="text-xs text-[var(--text-2)]">
          últimas {items.length}
        </span>
      </div>
      <div className="space-y-1.5 max-h-96 overflow-y-auto font-mono text-xs">
        {items.length === 0 && (
          <div className="text-[var(--text-2)] py-4 text-center">
            Esperando inferencias…
          </div>
        )}
        {items.map((i) => {
          const decision = (i.resultado as { decision?: string })?.decision;
          return (
            <div key={i.inferencia_id} className="flex items-center gap-2 py-1 border-b border-[var(--border)]/50">
              <span className="text-[var(--text-2)] w-20 shrink-0">
                {new Date(i.ts).toLocaleTimeString()}
              </span>
              <span className={`${AGENTE_COLOR[i.agente_codigo] ?? "text-white"} w-24 shrink-0 font-semibold`}>
                {i.agente_codigo}
              </span>
              <span className="w-32 shrink-0">{i.tipo_inferencia}</span>
              {decision && <span className={pillForDecision(decision)}>{decision}</span>}
              <span className="text-[var(--text-2)] ml-auto">
                {i.confianza !== null ? `c=${(i.confianza * 100).toFixed(0)}%` : ""}
                {i.latencia_ms !== null ? ` · ${i.latencia_ms}ms` : ""}
                {i.trigger_emitido && <span className="ml-1 pill pill-crit">TRIGGER</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
