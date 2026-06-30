import html
from pathlib import Path

import plotly.graph_objects as go

from . import stats

# Brand palette (dark dashboard: blue data + amber highlight)
_COLORWAY = ["#3B82F6", "#F59E0B", "#60A5FA", "#FBBF24", "#93C5FD",
             "#FCD34D", "#2563EB", "#D97706", "#A5B4FC", "#FB923C"]
_AMBER = "#F59E0B"


def _style(fig, title):
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=title, font=dict(size=17, family="Fira Sans")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Fira Sans, sans-serif", color="#CBD5E1", size=13),
        margin=dict(l=55, r=20, t=55, b=45),
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
        colorway=_COLORWAY,
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.12)", zeroline=False,
                     title_font=dict(size=12))
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.12)", zeroline=False,
                     ticksuffix=" €", title_font=dict(size=12))
    return fig


def _price_evolution_fig(rows):
    fig = go.Figure()
    for direction, label in (("OUT", "VIE→EFL"), ("RET", "EFL→VIE")):
        for flight_date, points in sorted(stats.price_series(rows, direction).items()):
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers",
                                     name=f"{label} {flight_date}"))
    return _style(fig, "Vývoj ceny v čase")


def _best_over_time_fig(rows):
    series = stats.cheapest_roundtrip_over_time(rows)
    xs = [s[0] for s in series]
    ys = [s[1] for s in series]
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines+markers", name="Najlacnejší round-trip",
        line=dict(color=_AMBER, width=3),
        marker=dict(color=_AMBER, size=7),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.10)",
    ))
    fig = _style(fig, "Najlacnejší round-trip v čase")
    fig.update_layout(showlegend=False)
    return fig


def _chart_html(fig, with_js):
    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if with_js else False,
        default_width="100%",
        default_height="380px",
        config={"displayModeBar": False, "responsive": True},
    )


def _kpi_cards_html(rows):
    combos = stats.cheapest_roundtrip_now(rows)
    latest = stats.latest_observed_at(rows)
    latest_rows = [r for r in rows if r["observed_at"] == latest]
    out = [r for r in latest_rows if r["direction"] == "OUT"]
    ret = [r for r in latest_rows if r["direction"] == "RET"]
    runs = len({r["observed_at"] for r in rows})

    def card(label, value, sub, accent=False):
        cls = "kpi kpi-accent" if accent else "kpi"
        return (f"<div class='{cls}'><div class='kpi-label'>{html.escape(label)}</div>"
                f"<div class='kpi-value'>{value}</div>"
                f"<div class='kpi-sub'>{html.escape(sub)}</div></div>")

    cards = []
    if combos:
        b = combos[0]
        cards.append(card(
            "Najlacnejší round-trip", f"{b['total']:.0f} €",
            f"{b['out_date']} → {b['ret_date']}", accent=True))
    if out:
        co = min(out, key=lambda r: r["price"])
        cards.append(card("Najlacnejší odlet", f"{co['price']:.0f} €",
                          f"VIE→EFL · {co['flight_date']}"))
    if ret:
        cr = min(ret, key=lambda r: r["price"])
        cards.append(card("Najlacnejší návrat", f"{cr['price']:.0f} €",
                          f"EFL→VIE · {cr['flight_date']}"))
    cards.append(card("Záznamov / meraní", f"{len(rows)}", f"{runs} behov"))
    return f"<div class='kpi-grid'>{''.join(cards)}</div>"


def _combos_table_html(rows):
    combos = stats.cheapest_roundtrip_now(rows)
    head = ("<tr><th>Odlet (VIE→EFL)</th><th>Cena tam</th>"
            "<th>Návrat (EFL→VIE)</th><th>Cena späť</th><th>Spolu</th></tr>")
    body = "".join(
        f"<tr class='{ 'best' if i == 0 else '' }'>"
        f"<td>{html.escape(c['out_date'])}</td><td>{c['out_price']:.2f} €</td>"
        f"<td>{html.escape(c['ret_date'])}</td><td>{c['ret_price']:.2f} €</td>"
        f"<td class='total'>{c['total']:.2f} €</td></tr>"
        for i, c in enumerate(combos)
    )
    return f"<table class='combos'><thead>{head}</thead><tbody>{body}</tbody></table>"


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
* { box-sizing: border-box; }
body {
  margin: 0; padding: 32px 20px 64px;
  background: #0B1120;
  background-image: radial-gradient(1200px 600px at 80% -10%, rgba(59,130,246,0.12), transparent),
                    radial-gradient(900px 500px at 0% 0%, rgba(245,158,11,0.06), transparent);
  color: #E2E8F0; font-family: 'Fira Sans', system-ui, sans-serif;
  line-height: 1.6;
}
.wrap { max-width: 1080px; margin: 0 auto; }
header { margin-bottom: 28px; }
.eyebrow { color: #60A5FA; font-weight: 600; letter-spacing: .08em;
  text-transform: uppercase; font-size: 12px; }
h1 { font-size: 30px; font-weight: 700; margin: 6px 0 4px; color: #F8FAFC; }
.updated { color: #94A3B8; font-size: 13px; font-family: 'Fira Code', monospace; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 16px; margin: 24px 0 32px; }
.kpi { background: rgba(30,41,59,0.55); border: 1px solid rgba(148,163,184,0.12);
  border-radius: 16px; padding: 18px 20px; backdrop-filter: blur(6px); }
.kpi-accent { border-color: rgba(245,158,11,0.45);
  background: linear-gradient(180deg, rgba(245,158,11,0.12), rgba(30,41,59,0.55)); }
.kpi-label { font-size: 12px; color: #94A3B8; text-transform: uppercase;
  letter-spacing: .05em; }
.kpi-value { font-size: 30px; font-weight: 700; font-family: 'Fira Code', monospace;
  color: #F8FAFC; margin: 6px 0 2px; }
.kpi-accent .kpi-value { color: #FBBF24; }
.kpi-sub { font-size: 13px; color: #CBD5E1; font-family: 'Fira Code', monospace; }
section { background: rgba(15,23,42,0.55); border: 1px solid rgba(148,163,184,0.12);
  border-radius: 18px; padding: 20px 22px; margin-bottom: 24px; }
h2 { font-size: 16px; font-weight: 600; color: #F1F5F9; margin: 0 0 14px;
  letter-spacing: .02em; }
table.combos { width: 100%; border-collapse: collapse; font-size: 14px; }
table.combos th { text-align: left; color: #94A3B8; font-weight: 600;
  font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
  padding: 10px 12px; border-bottom: 1px solid rgba(148,163,184,0.18); }
table.combos td { padding: 11px 12px; border-bottom: 1px solid rgba(148,163,184,0.08);
  font-family: 'Fira Code', monospace; color: #E2E8F0; }
table.combos tr.best td { background: rgba(245,158,11,0.10); }
table.combos td.total { font-weight: 600; color: #FBBF24; }
table.combos tbody tr:hover td { background: rgba(59,130,246,0.08); }
.empty { text-align: center; color: #94A3B8; padding: 60px 0; font-size: 16px; }
footer { color: #64748B; font-size: 12px; text-align: center; margin-top: 32px;
  font-family: 'Fira Code', monospace; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""


def build_report_html(rows):
    if not rows:
        return (f"<!DOCTYPE html><html lang='sk'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
                f"<title>Ryanair VIE↔EFL tracker</title><style>{_CSS}</style></head>"
                f"<body><div class='wrap'><header><div class='eyebrow'>Ryanair price tracker</div>"
                f"<h1>Vývoj ceny VIE↔EFL</h1></header>"
                f"<section><p class='empty'>Zatiaľ žiadne dáta</p></section></div></body></html>")

    updated = stats.latest_observed_at(rows)
    kpis = _kpi_cards_html(rows)
    evolution = _chart_html(_price_evolution_fig(rows), with_js=True)
    best = _chart_html(_best_over_time_fig(rows), with_js=False)
    table = _combos_table_html(rows)

    return f"""<!DOCTYPE html>
<html lang='sk'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Ryanair VIE↔EFL tracker</title>
<style>{_CSS}</style>
</head>
<body>
<div class='wrap'>
  <header>
    <div class='eyebrow'>Ryanair price tracker · september 2026</div>
    <h1>Viedeň ↔ Kefalonia</h1>
    <div class='updated'>Posledná aktualizácia: {html.escape(str(updated))}</div>
  </header>
  {kpis}
  <section>
    <h2>Najlacnejší round-trip teraz</h2>
    {table}
  </section>
  <section>
    <h2>Vývoj ceny v čase</h2>
    {evolution}
  </section>
  <section>
    <h2>Najlacnejší round-trip v čase</h2>
    {best}
  </section>
  <footer>Dáta: services-api.ryanair.com · generované lokálne, bez LLM</footer>
</div>
</body>
</html>"""


def write_report(rows, path):
    Path(path).write_text(build_report_html(rows), encoding="utf-8")
