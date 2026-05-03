"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { Briefing } from "@/lib/types";
import BriefingPanel from "./components/BriefingPanel";
import InferenciasStream from "./components/InferenciasStream";
import AccionesShadow from "./components/AccionesShadow";
import MatrizVidasPanel from "./components/MatrizVidasPanel";
import DispositivosPanel from "./components/DispositivosPanel";

export default function HomePage() {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const load = async () => {
      const { data } = await supabase
        .from("v_piro_briefing")
        .select("*")
        .single();
      if (data) setBriefing(data as Briefing);
    };
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [tick]);

  useEffect(() => {
    const channel = supabase
      .channel("piro_eventos_realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "piro_inferencias" },
        () => setTick((t) => t + 1),
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  return (
    <div className="space-y-6">
      <BriefingPanel briefing={briefing} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <InferenciasStream />
        <MatrizVidasPanel />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AccionesShadow />
        <DispositivosPanel />
      </div>
    </div>
  );
}
