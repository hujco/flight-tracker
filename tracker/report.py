from pathlib import Path

import plotly.graph_objects as go

from . import stats


def _price_evolution_fig(rows):
    fig = go.Figure()
    for direction, label in (("OUT", "VIE→EFL"), ("RET", "EFL→VIE")):
        for flight_date, points in sorted(stats.price_series(rows, direction).items()):
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers",
                                     name=f"{label} {flight_date}"))
    fig.update_layout(title="Vývoj ceny v čase",
                      xaxis_title="Čas merania", yaxis_title="Cena (EUR)")
    return fig


def _best_over_time_fig(rows):
    series = stats.cheapest_roundtrip_over_time(rows)
    xs = [s[0] for s in series]
    ys = [s[1] for s in series]
    fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines+markers",
                               name="Najlacnejší round-trip"))
    fig.update_layout(title="Najlacnejší round-trip v čase",
                      xaxis_title="Čas merania", yaxis_title="Total (EUR)")
    return fig


def _combos_table_html(rows):
    combos = stats.cheapest_roundtrip_now(rows)
    head = ("<tr><th>Odlet (VIE→EFL)</th><th>Cena tam</th>"
            "<th>Návrat (EFL→VIE)</th><th>Cena späť</th><th>Spolu</th></tr>")
    body = "".join(
        f"<tr><td>{c['out_date']}</td><td>{c['out_price']:.2f}</td>"
        f"<td>{c['ret_date']}</td><td>{c['ret_price']:.2f}</td>"
        f"<td><b>{c['total']:.2f}</b></td></tr>"
        for c in combos
    )
    return f"<table border='1' cellpadding='6'>{head}{body}</table>"


def build_report_html(rows):
    if not rows:
        return ("<html><head><meta charset='utf-8'></head>"
                "<body><h1>Vývoj ceny</h1><p>Zatiaľ žiadne dáta</p></body></html>")

    updated = stats.latest_observed_at(rows)
    evolution = _price_evolution_fig(rows).to_html(full_html=False, include_plotlyjs="cdn")
    best = _best_over_time_fig(rows).to_html(full_html=False, include_plotlyjs=False)
    table = _combos_table_html(rows)

    return f"""<html>
<head><meta charset='utf-8'><title>Ryanair VIE↔EFL tracker</title></head>
<body>
<h1>Ryanair VIE↔EFL — september 2026</h1>
<p>Posledná aktualizácia: {updated}</p>
<h2>Vývoj ceny v čase</h2>
{evolution}
<h2>Najlacnejší round-trip teraz</h2>
{table}
<h2>Najlacnejší round-trip v čase</h2>
{best}
</body>
</html>"""


def write_report(rows, path):
    Path(path).write_text(build_report_html(rows), encoding="utf-8")
