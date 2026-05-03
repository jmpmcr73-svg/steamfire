import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SteamFire — Mando PIRO",
  description: "Dashboard tiempo real Etapa 0 — Alejandría Steam Labs",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="border-b border-[var(--border)] px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold">
              SteamFire <span className="text-[var(--accent)]">/ PIRO</span>
            </h1>
            <p className="text-xs text-[var(--text-2)]">
              Mando táctico — rama PIRO bajo MOVE — Etapa 0.PRE shadow mode
            </p>
          </div>
          <div className="text-xs text-[var(--text-2)] font-mono">
            Kronos: zsmlntktqisiclzaxoky
          </div>
        </header>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}
