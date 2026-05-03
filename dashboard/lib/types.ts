export type Briefing = {
  zonas_activas: number;
  dispositivos_activos: number;
  dispositivos_perdidos: number;
  quemas_en_curso: number;
  quemas_planificadas: number;
  quemas_completadas: number;
  acciones_shadow_ult_24h: number;
  triggers_ult_hora: number;
  eventos_ult_5min: number;
  audit_entries_total: number;
  snapshot_ts: string;
};

export type Inferencia = {
  inferencia_id: number;
  ts: string;
  agente_codigo: string;
  tipo_inferencia: string;
  confianza: number | null;
  modelo_usado: string | null;
  latencia_ms: number | null;
  shadow_mode: boolean;
  trigger_emitido: boolean;
  zona_codigo: string | null;
  resultado: Record<string, unknown>;
  notas: string | null;
};

export type Accion = {
  accion_id: number;
  ts: string;
  agente_codigo: string;
  tipo_accion: string;
  objetivo: string | null;
  prioridad: string;
  ejecutada: boolean;
  shadow_mode: boolean;
  justificacion: string;
  zona_codigo: string | null;
  zona_nombre: string | null;
  quema_codigo: string | null;
};

export type MatrizVida = {
  matriz_id: number;
  ts: string;
  zona_id: number;
  zona_codigo: string;
  num_personas: number;
  personas: Array<{
    track_id: number;
    x_m: number;
    y_m: number;
    vx: number;
    vy: number;
    postura: string;
    certeza: number;
  }>;
  obscuracion_pct: number | null;
  temp_max_c: number | null;
  co_ppm: number | null;
  confianza_global: number;
  fuentes_consultadas: string[] | null;
};

export type DispositivoHealth = {
  dispositivo_id: number;
  codigo: string;
  tipo: string;
  modelo: string | null;
  modo: string;
  estado: string;
  ultimo_heartbeat: string | null;
  s_desde_heartbeat: number | null;
  rssi_dbm: number | null;
  bateria_pct: number | null;
  zona_codigo: string | null;
  zona_nombre: string | null;
  contexto: string | null;
  salud: "ok" | "lento" | "stale" | "sin_heartbeat" | "offline";
};
