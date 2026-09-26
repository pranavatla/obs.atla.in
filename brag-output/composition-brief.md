# Hyperframes Composition Brief: obs.atla.in

- Composition: `brag-output/composition/` → render `brag-output/brag.mp4`, 1920x1080, 11s
- Source: `index.html` (KPI strip, service health, Incident Simulator, Incident RCA), `app1.py` (service names, RCA copy)
- Verbatim copy: "obs.atla.in", "SLO Compliance", "Active Alarms", "DB Error Burst", "Incident RCA",
  "Checkout path degradation driven by database timeouts.", "Enable circuit-breaker behavior for failing DB dependencies.",
  chips "Real-time Metrics", "Incident Simulation", "AI-Powered RCA"
- Motto (must read clearly): "See it. Break it. Explain it."
- Tone: app-store / polished, fast cuts with readable holds
- Palette: bg #f4f7fb, text #0f172a, accent #2563eb→#0f766e, danger #dc2626; font Inter (local woff2)
- Scenes: Hook 0–2.2 · Dashboard see/break 2.2–5.2 · RCA explain 5.2–7.9 · Motto outro 7.9–11
- Audio: vol-10 at 0.35 with data-media-start=15; cues 3.55 / 5.19 / 7.92; SFX mouseclick1, impactSoft_medium_001, error_005, drop_001, impactBell_heavy_000
- Audio-reactive: skipped (duration too short); documented
- Gate: `npx hyperframes check` clean
