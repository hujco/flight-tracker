import html
from datetime import date, datetime
from pathlib import Path

import plotly.graph_objects as go

from . import config, stats


def _fmt_date(iso):
    """'2026-09-14' -> '14.09.2026' (EU)."""
    d = date.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _fmt_dt(iso):
    """'2026-06-30T14:00' -> '30.06.2026 14:00' (EU)."""
    dt = datetime.fromisoformat(iso)
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year} {dt.hour:02d}:{dt.minute:02d}"

# Brand palette (dark dashboard: blue data + amber highlight)
_COLORWAY = ["#3B82F6", "#F59E0B", "#60A5FA", "#FBBF24", "#93C5FD",
             "#FCD34D", "#2563EB", "#D97706", "#A5B4FC", "#FB923C"]
_AMBER = "#F59E0B"


def _style(fig, title=None):
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=title or "", font=dict(size=17, family="Fira Sans")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Fira Sans, sans-serif", color="#CBD5E1", size=13),
        margin=dict(l=55, r=20, t=55, b=45),
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
        colorway=_COLORWAY,
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.12)", zeroline=False,
                     title_font=dict(size=12),
                     tickformat="%d.%m. %H:%M", hoverformat="%d.%m.%Y %H:%M")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.12)", zeroline=False,
                     ticksuffix=" €", title_font=dict(size=12))
    return fig


def _price_evolution_fig(rows):
    """Dve prehľadné čiary: najlacnejší odlet a najlacnejší návrat v čase."""
    fig = go.Figure()
    legs = (
        ("OUT", "Najlacnejší odlet (VIE→EFL)", "#3B82F6"),
        ("RET", "Najlacnejší návrat (EFL→VIE)", "#F59E0B"),
    )
    for direction, label, color in legs:
        series = stats.cheapest_leg_over_time(rows, direction)
        xs = [s[0] for s in series]
        ys = [s[1] for s in series]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers", name=label,
            line=dict(width=3, color=color), marker=dict(size=6, color=color)))
    return _style(fig)


def _best_over_time_fig(rows, min_nights, max_nights):
    series = stats.cheapest_roundtrip_over_time(
        rows, min_nights=min_nights, max_nights=max_nights)
    xs = [s[0] for s in series]
    # reálny odhad pre PERSONS osôb + fixné doplnky → porovnateľné s referenciou
    ys = [stats.total_with_extras(s[1], config.PERSONS, config.EXTRAS_EUR) for s in series]
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        name=f"Reálny odhad ({config.PERSONS} os.)",
        line=dict(color=_AMBER, width=3),
        marker=dict(color=_AMBER, size=7),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.10)",
    ))
    fig = _style(fig)
    fig.update_layout(showlegend=False)
    if xs:
        fig.add_hline(
            y=config.REFERENCE_PRICE_EUR, line_dash="dash", line_color="#94A3B8",
            annotation_text=f"pred 2 r.: {config.REFERENCE_PRICE_EUR:.0f} €",
            annotation_position="top left",
            annotation_font_color="#CBD5E1")
    return fig


def _chart_html(fig):
    # plotly.js sa načíta raz v <head>, takže tu nikdy nevkladáme knižnicu
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        default_width="100%",
        default_height="380px",
        config={"displayModeBar": False, "responsive": True},
    )


def _kpi_cards_html(rows, min_nights, max_nights):
    combos = stats.cheapest_roundtrip_now(
        rows, min_nights=min_nights, max_nights=max_nights)
    runs = len({r["observed_at"] for r in rows})

    def card(label, value, sub, tone=""):
        cls = "kpi" + (f" kpi-{tone}" if tone else "")
        return (f"<div class='{cls}'><div class='kpi-label'>{html.escape(label)}</div>"
                f"<div class='kpi-value'>{value}</div>"
                f"<div class='kpi-sub'>{html.escape(sub)}</div></div>")

    cards = []
    if combos:
        b = combos[0]
        base_pp = b["total"]
        total_2p = stats.total_with_extras(base_pp, config.PERSONS, config.EXTRAS_EUR)
        diff = round(total_2p - config.REFERENCE_PRICE_EUR, 2)

        # Hlavná karta: reálny odhad pre 2 os. + verdikt voči referencii
        if diff <= 0:
            tone, verdict = "good", f"dobrá cena · {diff:.0f} € vs {config.REFERENCE_PRICE_EUR:.0f} €"
        else:
            tone, verdict = "bad", f"+{diff:.0f} € oproti {config.REFERENCE_PRICE_EUR:.0f} € (pred 2 r.) · počkaj"
        cards.append(card(
            f"Reálny odhad ({config.PERSONS} os. + batožina)", f"{total_2p:.0f} €",
            verdict, tone=tone))

        # Pohľad za 1 osobu (čistá letenka) vs referencia za 1 os.
        cards.append(card(
            "Letenka / os. (tam+späť)", f"{base_pp:.0f} €",
            f"pred 2 r. ~{config.REFERENCE_PER_PERSON_EUR:.0f} € · "
            f"{_fmt_date(b['out_date'])} → {_fmt_date(b['ret_date'])} · {b['nights']} nocí",
            tone="accent"))

        cards.append(card(
            "Doplnky (fixné)", f"{config.EXTRAS_EUR:.0f} €",
            f"kufor {config.BAGGAGE_PER_LEG_EUR:.0f} € ×2 + miestenky {config.SEATS_EUR:.0f} €"))

    cards.append(card("Záznamov / meraní", f"{len(rows)}", f"{runs} behov"))
    return f"<div class='kpi-grid'>{''.join(cards)}</div>"


def _combos_table_html(rows, min_nights, max_nights):
    combos = stats.cheapest_roundtrip_now(
        rows, min_nights=min_nights, max_nights=max_nights)
    head = ("<tr><th>Odlet (VIE→EFL)</th><th>Cena tam</th>"
            "<th>Návrat (EFL→VIE)</th><th>Cena späť</th><th>Nocí</th><th>Spolu</th></tr>")
    body = "".join(
        f"<tr class='{ 'best' if i == 0 else '' }'>"
        f"<td>{_fmt_date(c['out_date'])}</td><td>{c['out_price']:.2f} €</td>"
        f"<td>{_fmt_date(c['ret_date'])}</td><td>{c['ret_price']:.2f} €</td>"
        f"<td>{c['nights']}</td>"
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
.toggle-wrap { display: flex; align-items: center; gap: 12px; margin: 22px 0 4px; }
.toggle-label { color: #94A3B8; font-size: 13px; }
.toggle { display: inline-flex; gap: 4px; background: rgba(30,41,59,0.6);
  border: 1px solid rgba(148,163,184,0.15); border-radius: 12px; padding: 4px; }
.toggle-btn { cursor: pointer; border: 0; background: transparent; color: #94A3B8;
  font: 600 13px 'Fira Sans', sans-serif; padding: 8px 16px; border-radius: 9px;
  transition: background .2s, color .2s; }
.toggle-btn.active { background: #3B82F6; color: #fff; }
.toggle-btn:hover:not(.active) { color: #E2E8F0; }
[hidden] { display: none !important; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 16px; margin: 24px 0 32px; }
.kpi { background: rgba(30,41,59,0.55); border: 1px solid rgba(148,163,184,0.12);
  border-radius: 16px; padding: 18px 20px; backdrop-filter: blur(6px); }
.kpi-accent { border-color: rgba(245,158,11,0.45);
  background: linear-gradient(180deg, rgba(245,158,11,0.12), rgba(30,41,59,0.55)); }
.kpi-good { border-color: rgba(34,197,94,0.5);
  background: linear-gradient(180deg, rgba(34,197,94,0.14), rgba(30,41,59,0.55)); }
.kpi-bad { border-color: rgba(239,68,68,0.5);
  background: linear-gradient(180deg, rgba(239,68,68,0.14), rgba(30,41,59,0.55)); }
.kpi-label { font-size: 12px; color: #94A3B8; text-transform: uppercase;
  letter-spacing: .05em; }
.kpi-value { font-size: 30px; font-weight: 700; font-family: 'Fira Code', monospace;
  color: #F8FAFC; margin: 6px 0 2px; }
.kpi-accent .kpi-value { color: #FBBF24; }
.kpi-good .kpi-value { color: #4ADE80; }
.kpi-bad .kpi-value { color: #F87171; }
.kpi-sub { font-size: 13px; color: #CBD5E1; font-family: 'Fira Code', monospace; }
section { background: rgba(15,23,42,0.55); border: 1px solid rgba(148,163,184,0.12);
  border-radius: 18px; padding: 20px 22px; margin-bottom: 24px; }
h2 { font-size: 16px; font-weight: 600; color: #F1F5F9; margin: 0 0 4px;
  letter-spacing: .02em; }
.caption { color: #94A3B8; font-size: 13px; margin: 0 0 14px; }
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


def _preset_block(rows, preset, index):
    mn, mx = preset["min_nights"], preset["max_nights"]
    kpis = _kpi_cards_html(rows, mn, mx)
    table = _combos_table_html(rows, mn, mx)
    best = _chart_html(_best_over_time_fig(rows, mn, mx))
    hidden = "" if index == 0 else " hidden"
    return f"""<div class='preset' data-preset='{index}'{hidden}>
  {kpis}
  <section>
    <h2>Najlacnejší round-trip teraz</h2>
    <p class='caption'>Ceny za 1 osobu (samotná letenka), pobyt {html.escape(preset['label'])}. Doplnky (batožina + miestenky {config.EXTRAS_EUR:.0f} €) sa rátajú zvlášť v reálnom odhade hore.</p>
    {table}
  </section>
  <section>
    <h2>Najlacnejší round-trip v čase</h2>
    <p class='caption'>Reálny odhad pre {config.PERSONS} osoby vrátane doplnkov ({html.escape(preset['label'])}), oproti referencii {config.REFERENCE_PRICE_EUR:.0f} € spred 2 rokov.</p>
    {best}
  </section>
</div>"""


_PLOTLY_JS = "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js' charset='utf-8'></script>"

_TOGGLE_JS = """<script>
(function () {
  var btns = document.querySelectorAll('.toggle-btn');
  var panels = document.querySelectorAll('.preset');
  btns.forEach(function (b) {
    b.addEventListener('click', function () {
      var t = b.dataset.target;
      btns.forEach(function (x) { x.classList.toggle('active', x.dataset.target === t); });
      panels.forEach(function (p) { p.hidden = (p.dataset.preset !== t); });
      if (window.Plotly) {
        document.querySelectorAll("[data-preset='" + t + "'] .plotly-graph-div")
          .forEach(function (g) { window.Plotly.Plots.resize(g); });
      }
    });
  });
})();
</script>"""


def build_report_html(rows):
    if not rows:
        return (f"<!DOCTYPE html><html lang='sk'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
                f"<title>Ryanair VIE↔EFL tracker</title><style>{_CSS}</style></head>"
                f"<body><div class='wrap'><header><div class='eyebrow'>Ryanair price tracker</div>"
                f"<h1>Vývoj ceny VIE↔EFL</h1></header>"
                f"<section><p class='empty'>Zatiaľ žiadne dáta</p></section></div></body></html>")

    updated = stats.latest_observed_at(rows)
    evolution = _chart_html(_price_evolution_fig(rows))

    buttons = "".join(
        f"<button class='toggle-btn{' active' if i == 0 else ''}' data-target='{i}'>"
        f"{html.escape(p['label'])}</button>"
        for i, p in enumerate(config.STAY_PRESETS)
    )
    toggle = f"<div class='toggle' role='tablist'>{buttons}</div>"
    blocks = "".join(
        _preset_block(rows, p, i) for i, p in enumerate(config.STAY_PRESETS))

    return f"""<!DOCTYPE html>
<html lang='sk'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Ryanair VIE↔EFL tracker</title>
{_PLOTLY_JS}
<style>{_CSS}</style>
</head>
<body>
<div class='wrap'>
  <header>
    <div class='eyebrow'>Ryanair price tracker · september 2026</div>
    <h1>Viedeň ↔ Kefalonia</h1>
    <div class='updated'>Posledná aktualizácia: {html.escape(_fmt_dt(updated))}</div>
  </header>
  <div class='toggle-wrap'><span class='toggle-label'>Dĺžka pobytu:</span> {toggle}</div>
  {blocks}
  <section>
    <h2>Vývoj ceny v čase</h2>
    <p class='caption'>Najnižšia cena odletu a návratu (za 1 os.) pri každom meraní — nezávislé od dĺžky pobytu.</p>
    {evolution}
  </section>
  <footer>Dáta: services-api.ryanair.com · generované lokálne, bez LLM</footer>
</div>
{_TOGGLE_JS}
</body>
</html>"""


def write_report(rows, path):
    Path(path).write_text(build_report_html(rows), encoding="utf-8")
