"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { DispositivoHealth } from "@/lib/types";

function pillSalud(s: DispositivoHealth["salud"]) {
  if (s === "ok") return "pill pill-ok";
  if (s === "lento" || s === "stale") return "pill pill-warn";
  return "pill pill-crit";
}

export default function DispositivosPanel() {
  const [items, setItems] = useState<DispositivoHealth[]>([]);

  useEffect(() => {
    const reload = async () => {
      const { data } = await supabase
        .from("v_piro_dispositivos_health")
        .select("*")
        .order("codigo");
      setItems((data as DispositivoHealth[]) ?? []);
    };
    reload();
    const i = setInterval(reload, 5000);
    return () => clearInterval(i);
  }, []);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">Dispositivos</h2>
        <span className="text-xs text-[var(--text-2)]">{items.length} registrados</span>
      </div>
      <div className="overflow-y-auto max-h-96">
        <table className="w-full text-xs">
          <thead className="text-left text-[var(--text-2)] border-b border-[var(--border)]">
            <tr>
              <th className="py-1.5">codigo</th>
              <th>tipo</th>
              <th>zona</th>
              <th>modo</th>
              <th>estado</th>
              <th>salud</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {items.map((d) => (
              <tr key={d.dispositivo_id} className="border-b border-[var(--border)]/50">
                <td className="py-1 pr-2">{d.codigo}</td>
                <td className="pr-2">{d.tipo}</td>
                <td className="pr-2">{d.zona_codigo ?? "—"}</td>
                <td className="pr-2">{d.modo}</td>
                <td className="pr-2">{d.estado}</td>
                <td><span className={pillSalud(d.salud)}>{d.salud}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
