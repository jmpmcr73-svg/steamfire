"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { MatrizVida } from "@/lib/types";

function ZonaCanvas({ matriz }: { matriz: MatrizVida }) {
  const w = 240, h = 180, lado = 3.0; // m del lab Jose
  const sx = w / lado, sy = h / lado;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-44 bg-[var(--bg-3)] rounded">
      <rect x="2" y="2" width={w - 4} height={h - 4} fill="none" stroke="#3a4554" strokeWidth="1" rx="4" />
      {matriz.personas.map((p) => (
        <g key={p.track_id}>
          <circle cx={p.x_m * sx} cy={p.y_m * sy} r="6" fill="#22c55e" opacity={0.6 + 0.4 * p.certeza} />
          <text
            x={p.x_m * sx + 8}
            y={p.y_m * sy + 3}
            fontSize="9"
            fill="#22c55e"
            fontFamily="ui-monospace"
          >
            #{p.track_id}
          </text>
          {(p.vx !== 0 || p.vy !== 0) && (
            <line
              x1={p.x_m * sx}
              y1={p.y_m * sy}
              x2={p.x_m * sx + p.vx * 8}
              y2={p.y_m * sy + p.vy * 8}
              stroke="#22c55e"
              strokeWidth="1.5"
              opacity="0.6"
            />
          )}
        </g>
      ))}
      <text x={6} y={h - 6} fontSize="9" fill="#97a2b1" fontFamily="ui-monospace">
        zona {matriz.zona_codigo}
      </text>
    </svg>
  );
}

export default function MatrizVidasPanel() {
  const [items, setItems] = useState<MatrizVida[]>([]);

  const reload = async () => {
    const { data } = await supabase
      .from("v_piro_matriz_vida_actual")
      .select("*");
    setItems((data as MatrizVida[]) ?? []);
  };

  useEffect(() => {
    reload();
    const i = setInterval(reload, 2000);
    return () => clearInterval(i);
  }, []);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">Matriz de vidas</h2>
        <span className="text-xs text-[var(--text-2)]">por zona, snapshot 5s</span>
      </div>
      {items.length === 0 ? (
        <div className="text-[var(--text-2)] py-8 text-center text-xs">
          Sin tracks recientes. Lanza un escenario sintético con personas (Q02, Q04, Q10…)
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {items.map((m) => (
            <div key={m.matriz_id} className="space-y-1">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-[var(--accent)]">{m.zona_codigo}</span>
                <span className="pill pill-info">
                  {m.num_personas} {m.num_personas === 1 ? "persona" : "personas"}
                </span>
                {m.obscuracion_pct !== null && m.obscuracion_pct > 30 && (
                  <span className="pill pill-warn">humo {m.obscuracion_pct.toFixed(0)}%</span>
                )}
                <span className="ml-auto text-[var(--text-2)]">
                  c={(m.confianza_global * 100).toFixed(0)}%
                </span>
              </div>
              <ZonaCanvas matriz={m} />
              <div className="text-[0.7rem] text-[var(--text-2)] flex gap-3">
                {m.temp_max_c !== null && <span>T={m.temp_max_c.toFixed(1)}°C</span>}
                {m.co_ppm !== null && <span>CO={m.co_ppm.toFixed(0)}ppm</span>}
                {m.fuentes_consultadas && <span>fuentes: {m.fuentes_consultadas.join(", ")}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
