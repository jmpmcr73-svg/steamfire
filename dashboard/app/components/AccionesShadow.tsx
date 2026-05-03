"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { Accion } from "@/lib/types";

function pillForPrioridad(p: string) {
  if (p === "info") return "pill pill-info";
  if (p === "warning") return "pill pill-warn";
  if (p === "urgent") return "pill pill-warn";
  if (p === "critical") return "pill pill-crit";
  return "pill pill-info";
}

export default function AccionesShadow() {
  const [items, setItems] = useState<Accion[]>([]);

  const reload = async () => {
    const { data } = await supabase
      .from("v_piro_acciones_recientes")
      .select("*")
      .limit(40);
    setItems((data as Accion[]) ?? []);
  };

  useEffect(() => {
    reload();
    const ch = supabase
      .channel("acc_stream")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "piro_acciones_simuladas" },
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
        <h2 className="font-semibold">Acciones shadow (últimas 24h)</h2>
        <span className="pill pill-info">SHADOW MODE</span>
      </div>
      <div className="space-y-2 max-h-96 overflow-y-auto text-sm">
        {items.length === 0 && (
          <div className="text-[var(--text-2)] py-4 text-center text-xs">
            Sin acciones recomendadas. Esperando triggers IGNIS…
          </div>
        )}
        {items.map((a) => (
          <div key={a.accion_id} className="border border-[var(--border)] rounded-md p-2.5">
            <div className="flex items-center gap-2 mb-1">
              <span className={pillForPrioridad(a.prioridad)}>{a.prioridad}</span>
              <span className="font-mono font-semibold text-[var(--accent)]">{a.tipo_accion}</span>
              <span className="text-[var(--text-2)] text-xs">{a.objetivo}</span>
              <span className="ml-auto text-[var(--text-2)] text-xs">
                {new Date(a.ts).toLocaleTimeString()}
              </span>
            </div>
            <div className="text-xs text-[var(--text-2)] leading-snug">
              {a.justificacion}
            </div>
            <div className="flex items-center gap-2 mt-1.5 text-[0.7rem] text-[var(--text-2)]">
              <span>zona: {a.zona_codigo ?? "—"}</span>
              {a.quema_codigo && <span>quema: {a.quema_codigo}</span>}
              <span>ejecutada: {a.ejecutada ? "sí" : "no (shadow)"}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
