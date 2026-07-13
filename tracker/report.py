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

# Počítadlo osôb v porovnávacej hlavičke (prepočíta spolu cenu za skupinu).
_PERSONS_OPTIONS = [1, 2, 4]
_DEFAULT_PERSONS = 4


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


def _origin_label(code):
    return {"VIE": "Viedeň", "BUD": "Budapešť"}.get(code, code)


def _dest_label(code):
    for d in config.DESTINATIONS:
        if d["code"] == code:
            return d["label"]
    return code


def _origin_from(code):
    """Genitív pre spojenie 'Z ...' (Z Viedne / Z Budapešti)."""
    return {"VIE": "Viedne", "BUD": "Budapešti"}.get(code, _origin_label(code))


def _dest_to(code):
    """Genitív pre spojenie 'do ...' (do Lefkady)."""
    gen = {"PVK": "Lefkady", "EFL": "Kefalonie", "ZTH": "Zakyntu"}
    return gen.get(code, _dest_label(code))


def _row_origin(r):
    """Origin riadku; staré/nezatagované dáta počítame ako hlavné odletisko."""
    return r.get("origin") or config.ORIGIN


def _all_origins():
    origins = [config.ORIGIN]
    if getattr(config, "BUD_TRIPS", None) and config.BUD_ORIGIN not in origins:
        origins.append(config.BUD_ORIGIN)
    return origins


def _origin_stay_presets(origin_code):
    if origin_code == getattr(config, "BUD_ORIGIN", None):
        return config.BUD_STAY_PRESETS
    return config.STAY_PRESETS


def _is_primary(origin_code, out_date, ret_date):
    """Je to presne náš let (odletisko + oba fixné dátumy)?"""
    t = config.PRIMARY_TRIP
    return (origin_code == t["origin"] and out_date == t["out"]
            and ret_date == t["ret"])


def _trip_chip(origin_code, out_date, ret_date):
    """Odznak pri každej cene: náš termín vs. iný termín (nikdy nie nejasné)."""
    if _is_primary(origin_code, out_date, ret_date):
        return "<span class='chip chip-our'>náš termín</span>"
    return "<span class='chip chip-alt'>iný termín</span>"


def _price_evolution_fig(rows, dest_code, origin_code):
    """Dve prehľadné čiary: najlacnejší odlet a najlacnejší návrat v čase."""
    fig = go.Figure()
    legs = (
        ("OUT", f"Najlacnejší odlet ({origin_code}→{dest_code})", "#3B82F6"),
        ("RET", f"Najlacnejší návrat ({dest_code}→{origin_code})", "#F59E0B"),
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
    if config.INCLUDE_EXTRAS:
        # reálny odhad pre PERSONS osôb + fixné doplnky → voči 301 €
        ys = [stats.total_with_extras(s[1], config.PERSONS, config.EXTRAS_EUR) for s in series]
        ref, name = config.REFERENCE_PRICE_EUR, f"Reálny odhad ({config.PERSONS} os.)"
    else:
        # default: čistá letenka za 1 os. → voči ~117 € spred 2 rokov
        ys = [s[1] for s in series]
        ref, name = config.REFERENCE_PER_PERSON_EUR, "Letenka / os."
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines+markers", name=name,
        line=dict(color=_AMBER, width=3),
        marker=dict(color=_AMBER, size=7),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.10)",
    ))
    fig = _style(fig)
    fig.update_layout(showlegend=False)
    if xs:
        fig.add_hline(
            y=ref, line_dash="dash", line_color="#94A3B8",
            annotation_text=f"pred 2 r.: ~{ref:.0f} €",
            annotation_position="top left",
            annotation_font_color="#CBD5E1")
    return fig


def _chart_html(fig, height="380px"):
    # plotly.js sa načíta raz v <head>, takže tu nikdy nevkladáme knižnicu
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        default_width="100%",
        default_height=height,
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
        termin = (f"{_fmt_date(b['out_date'])} → {_fmt_date(b['ret_date'])} · "
                  f"{b['nights']} nocí")

        # Hlavná karta s verdiktom: letenka za 1 os. vs cena letenky spred 2 rokov
        diff_pp = round(base_pp - config.REFERENCE_PER_PERSON_EUR, 2)
        if diff_pp <= 0:
            tone, verdict = "good", (f"dobrá cena · {diff_pp:.0f} € vs "
                                     f"~{config.REFERENCE_PER_PERSON_EUR:.0f} € (pred 2 r.)")
        else:
            tone, verdict = "bad", (f"+{diff_pp:.0f} € oproti ~{config.REFERENCE_PER_PERSON_EUR:.0f} € "
                                    f"(pred 2 r.) · počkaj")
        cards.append(card("Letenka / os. (tam+späť)", f"{base_pp:.0f} €",
                          f"{verdict} · {termin}", tone=tone))

        # Spolu za všetkých cestujúcich (len letenky)
        cards.append(card(f"Spolu {config.PERSONS} osoby (letenky)",
                          f"{base_pp * config.PERSONS:.0f} €", termin))

        # Voliteľne: reálny odhad s batožinou + miestenkami (default vypnuté)
        if config.INCLUDE_EXTRAS:
            total_2p = stats.total_with_extras(base_pp, config.PERSONS, config.EXTRAS_EUR)
            cards.append(card(
                f"Reálny odhad ({config.PERSONS} os. + batožina)", f"{total_2p:.0f} €",
                f"+ doplnky {config.EXTRAS_EUR:.0f} € "
                f"(kufor {config.BAGGAGE_PER_LEG_EUR:.0f} € ×2 + miestenky {config.SEATS_EUR:.0f} €)",
                tone="accent"))

    cards.append(card("Záznamov / meraní", f"{len(rows)}", f"{runs} behov"))
    return f"<div class='kpi-grid'>{''.join(cards)}</div>"


def _combos_table_html(rows, min_nights, max_nights, dest_code, origin_code):
    combos = stats.cheapest_roundtrip_now(
        rows, min_nights=min_nights, max_nights=max_nights)
    head = (f"<tr><th>Odlet ({origin_code}→{dest_code})</th><th>Cena tam</th>"
            f"<th>Návrat ({dest_code}→{origin_code})</th><th>Cena späť</th><th>Nocí</th><th>Spolu</th></tr>")

    def row(i, c):
        ours = _is_primary(origin_code, c["out_date"], c["ret_date"])
        cls = " ".join(x for x in ("best" if i == 0 else "", "our" if ours else "") if x)
        mark = "<span class='chip chip-our'>náš termín</span>" if ours else ""
        return (f"<tr class='{cls}'>"
                f"<td>{_fmt_date(c['out_date'])}{mark}</td><td>{c['out_price']:.2f} €</td>"
                f"<td>{_fmt_date(c['ret_date'])}</td><td>{c['ret_price']:.2f} €</td>"
                f"<td>{c['nights']}</td>"
                f"<td class='total'>{c['total']:.2f} €</td></tr>")

    body = "".join(row(i, c) for i, c in enumerate(combos))
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
.dest-btn { cursor: pointer; border: 0; background: transparent; color: #94A3B8;
  font: 600 14px 'Fira Sans', sans-serif; padding: 8px 16px; border-radius: 9px;
  transition: background .2s, color .2s; }
.dest-btn.active { background: #F59E0B; color: #0B1120; }
.dest-btn:hover:not(.active) { color: #E2E8F0; }
[hidden] { display: none !important; }
/* Náš hlavný let (zvýraznené navrchu) */
.hero { background: linear-gradient(180deg, rgba(245,158,11,0.15), rgba(15,23,42,0.55));
  border: 1px solid rgba(245,158,11,0.40); border-radius: 22px;
  padding: 22px 26px 24px; margin-bottom: 26px; }
.hero-eyebrow { color: #FBBF24; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; font-size: 12px; }
.hero-title { font-size: 22px; font-weight: 700; color: #F8FAFC; margin: 6px 0 2px;
  line-height: 1.3; }
.hero-card { display: flex; align-items: baseline; gap: 24px; flex-wrap: wrap;
  margin: 14px 0 10px; }
.hero-price { font-family: 'Fira Code', monospace; font-size: 44px; font-weight: 700;
  color: #FBBF24; }
.hero-price .cmp-unit { font-size: 16px; }
.hero-total { font-family: 'Fira Code', monospace; font-size: 18px; color: #CBD5E1; }
.hero-total b { color: #F8FAFC; font-size: 22px; }
.hero-legs { font-family: 'Fira Code', monospace; font-size: 13px; color: #94A3B8; }
.hero-legs b { color: #E2E8F0; }
.hero-low { font-family: 'Fira Code', monospace; font-size: 13px; color: #94A3B8;
  margin-bottom: 6px; }
.hero-low b { color: #E2E8F0; }
.hero-low-hit { color: #4ADE80; font-weight: 600; }
.hero-seats { font-size: 13px; line-height: 1.4; color: #FBBF24; font-weight: 600;
  background: rgba(245,158,11,0.10); border: 1px solid rgba(245,158,11,0.35);
  border-radius: 8px; padding: 8px 12px; margin: 8px 0 6px; }
.hero-chart { margin-top: 8px; }

/* Odznak termínu — pri každej cene je jasné, či je to náš dátum */
.chip { display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 999px;
  font: 600 11px 'Fira Sans', sans-serif; letter-spacing: .02em; vertical-align: 1px; }
.chip-our { background: rgba(245,158,11,0.18); color: #FBBF24;
  border: 1px solid rgba(245,158,11,0.45); }
.chip-alt { background: rgba(148,163,184,0.12); color: #94A3B8;
  border: 1px solid rgba(148,163,184,0.28); }

/* Iné termíny: potlačené do úzadia, ožijú až pri interakcii */
.secondary { opacity: .62; filter: saturate(.75);
  transition: opacity .25s ease, filter .25s ease; }
.secondary:hover, .secondary:focus-within { opacity: 1; filter: none; }
/* na dotykových zariadeniach niet hoveru → drž to čitateľné, len jemne stlmené */
@media (hover: none) { .secondary { opacity: .85; filter: saturate(.9); } }
.sep { display: flex; align-items: center; gap: 14px; margin: 34px 0 8px; }
.sep::before, .sep::after { content: ""; flex: 1; height: 1px;
  background: rgba(148,163,184,0.20); }
.sep-text { color: #94A3B8; font-size: 12px; font-weight: 600; letter-spacing: .1em;
  text-transform: uppercase; white-space: nowrap; }
.sep-note { color: #94A3B8; font-size: 13px; text-align: center; margin: 0 0 22px; }
.sep-note b { color: #CBD5E1; }
table.combos tr.our td { background: rgba(245,158,11,0.10);
  box-shadow: inset 3px 0 0 #F59E0B; }

/* Porovnávacia hlavička (odletiská) */
.cmp-section { background: linear-gradient(180deg, rgba(30,41,59,0.55), rgba(15,23,42,0.5));
  border: 1px solid rgba(148,163,184,0.14); border-radius: 20px;
  padding: 22px 24px 24px; margin-bottom: 26px; }
.cmp-section h2 { margin-bottom: 2px; }
.cmp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px; margin: 12px 0 4px; }
.cmp-card { position: relative; border-radius: 16px; padding: 18px 20px;
  background: rgba(15,23,42,0.5); border: 1px solid rgba(148,163,184,0.14); }
.cmp-vie { border-left: 4px solid #3B82F6; }
.cmp-bud { border-left: 4px solid #F59E0B; }
.cmp-win { border-color: rgba(34,197,94,0.45);
  box-shadow: 0 0 0 1px rgba(34,197,94,0.45), 0 10px 34px rgba(34,197,94,0.10); }
.cmp-org { font-size: 13px; color: #CBD5E1; font-weight: 600;
  display: flex; align-items: center; gap: 8px; }
.cmp-code { font-family: 'Fira Code', monospace; font-size: 11px; color: #94A3B8;
  border: 1px solid rgba(148,163,184,0.25); border-radius: 6px; padding: 1px 6px; }
.cmp-badge { margin-left: auto; font-size: 11px; font-weight: 700; color: #0B1120;
  background: #4ADE80; border-radius: 999px; padding: 2px 9px; letter-spacing: .02em; }
.cmp-price { font-family: 'Fira Code', monospace; font-size: 34px; font-weight: 700;
  color: #F8FAFC; margin: 10px 0 2px; }
.cmp-win .cmp-price { color: #4ADE80; }
.cmp-unit { font-size: 14px; font-weight: 500; color: #94A3B8; }
.cmp-sub { font-size: 13px; color: #94A3B8; font-family: 'Fira Code', monospace; }
.cmp-total { margin-top: 12px; padding-top: 10px; font-size: 14px; color: #CBD5E1;
  border-top: 1px solid rgba(148,163,184,0.12); font-family: 'Fira Code', monospace;
  min-height: 20px; }
.cmp-total b { color: #F8FAFC; font-size: 17px; }
.cmp-win .cmp-total b { color: #4ADE80; }
.pp-wrap { display: flex; align-items: center; gap: 12px; margin: 14px 0 2px; }
.pp-toggle .pp-btn { cursor: pointer; border: 0; background: transparent; color: #94A3B8;
  font: 600 13px 'Fira Code', monospace; padding: 7px 15px; border-radius: 9px;
  transition: background .2s, color .2s; }
.pp-toggle .pp-btn.active { background: #F59E0B; color: #0B1120; }
.pp-toggle .pp-btn:hover:not(.active) { color: #E2E8F0; }
.pp-note { font-size: 12px; line-height: 1.4; color: #94A3B8; margin: 4px 0 2px; max-width: 46ch; }
.cmp-verdict { margin: 14px 2px 2px; font-size: 15px; color: #E2E8F0; }
.cmp-verdict b { color: #FBBF24; }
.cmp-chart { margin-top: 14px; }
.cmp-chart h3 { font-size: 14px; font-weight: 600; color: #CBD5E1; margin: 6px 0 0; }

/* Detaily na plnú šírku, stohované pod porovnaním */
.origin-stack { display: flex; flex-direction: column; }
.origin-single, .origin-block { min-width: 0; }
.origin-stack > .origin-block + .origin-block {
  border-top: 1px solid rgba(148,163,184,0.12); padding-top: 22px; margin-top: 14px; }
.origin-title { font-size: 16px; font-weight: 700; margin: 0 0 10px; letter-spacing: .02em; }
.origin-stack > .origin-block:nth-child(1) .origin-title { color: #60A5FA; }
.origin-stack > .origin-block:nth-child(2) .origin-title { color: #FBBF24; }
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


def _preset_block(rows, preset, index, dest_code, origin_code):
    mn, mx = preset["min_nights"], preset["max_nights"]
    label = html.escape(preset["label"])
    kpis = _kpi_cards_html(rows, mn, mx)
    table = _combos_table_html(rows, mn, mx, dest_code, origin_code)
    best = _chart_html(_best_over_time_fig(rows, mn, mx))
    hidden = "" if index == 0 else " hidden"

    if config.INCLUDE_EXTRAS:
        table_cap = (f"Ceny za 1 osobu (samotná letenka), pobyt {label}. Doplnky "
                     f"(batožina + miestenky {config.EXTRAS_EUR:.0f} €) sa rátajú zvlášť hore.")
        chart_cap = (f"Reálny odhad pre {config.PERSONS} osoby vrátane doplnkov ({label}), "
                     f"oproti referencii {config.REFERENCE_PRICE_EUR:.0f} € spred 2 rokov.")
    else:
        table_cap = f"Ceny za 1 osobu (samotná letenka), pobyt {label}."
        chart_cap = (f"Cena letenky za 1 os. v čase ({label}), oproti "
                     f"~{config.REFERENCE_PER_PERSON_EUR:.0f} € spred 2 rokov.")

    return f"""<div class='preset' data-preset='{index}'{hidden}>
  {kpis}
  <section>
    <h2>Najlacnejší round-trip teraz</h2>
    <p class='caption'>{table_cap}</p>
    {table}
  </section>
  <section>
    <h2>Najlacnejší round-trip v čase</h2>
    <p class='caption'>{chart_cap}</p>
    {best}
  </section>
</div>"""


_PLOTLY_JS = "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js' charset='utf-8'></script>"

_TOGGLE_JS = """<script>
(function () {
  function resizeVisible() {
    if (!window.Plotly) return;
    document.querySelectorAll(".dest-panel:not([hidden]) .plotly-graph-div")
      .forEach(function (g) {
        if (!g.closest("[hidden]")) window.Plotly.Plots.resize(g);
      });
  }
  document.querySelectorAll(".dest-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var d = b.dataset.dest;
      document.querySelectorAll(".dest-btn").forEach(function (x) {
        x.classList.toggle("active", x.dataset.dest === d); });
      document.querySelectorAll(".dest-panel").forEach(function (p) {
        p.hidden = (p.dataset.dest !== d); });
      resizeVisible();
    });
  });
  document.querySelectorAll(".toggle-btn").forEach(function (b) {
    b.addEventListener("click", function () {
      var panel = b.closest(".origin-block");
      var t = b.dataset.target;
      panel.querySelectorAll(".toggle-btn").forEach(function (x) {
        x.classList.toggle("active", x.dataset.target === t); });
      panel.querySelectorAll(".preset").forEach(function (p) {
        p.hidden = (p.dataset.preset !== t); });
      resizeVisible();
    });
  });
  // Počítadlo osôb (globálne): prepočíta spolu cenu skupiny z ceny za 1 os. (data-pp)
  function applyPersons(n) {
    document.querySelectorAll(".pp-btn").forEach(function (x) {
      x.classList.toggle("active", +x.dataset.n === n); });
    document.querySelectorAll("[data-pp]").forEach(function (c) {
      var el = c.querySelector(".js-total");
      if (!el) return;
      var pp = parseFloat(c.dataset.pp);
      el.innerHTML = isNaN(pp) ? "" :
        "Spolu " + n + " os.: <b>" + Math.round(pp * n) + " €</b>";
    });
  }
  document.querySelectorAll(".pp-btn").forEach(function (b) {
    b.addEventListener("click", function () { applyPersons(+b.dataset.n); });
  });
})();
</script>"""


def _origin_block(dest_rows, dest_code, origin_code):
    """Jeden stĺpec porovnania: dáta jedného odletiska pre danú destináciu."""
    orows = [r for r in dest_rows if _row_origin(r) == origin_code]
    presets = _origin_stay_presets(origin_code)
    if len(presets) > 1:
        buttons = "".join(
            f"<button class='toggle-btn{' active' if i == 0 else ''}' data-target='{i}'>"
            f"{html.escape(p['label'])}</button>"
            for i, p in enumerate(presets)
        )
        toggle = (f"<div class='toggle-wrap'><span class='toggle-label'>Dĺžka pobytu:</span> "
                  f"<div class='toggle' role='tablist'>{buttons}</div></div>")
    else:
        toggle = ""  # jediná (fixná) dĺžka pobytu → prepínač netreba
    blocks = "".join(
        _preset_block(orows, p, i, dest_code, origin_code)
        for i, p in enumerate(presets)
    )
    evolution = _chart_html(_price_evolution_fig(orows, dest_code, origin_code))
    return f"""<div class='origin-block'>
  <h3 class='origin-title'>Z {html.escape(_origin_from(origin_code))} ({html.escape(origin_code)})</h3>
  {toggle}
  {blocks}
  <section class='evolution'>
    <h2>Vývoj ceny v čase</h2>
    <p class='caption'>Najnižšia cena odletu a návratu (za 1 os.) pri každom meraní — nezávislé od dĺžky pobytu.</p>
    {evolution}
  </section>
</div>"""


def _comparison_nights():
    """Spoločná báza pre porovnanie odletísk = dĺžka pobytu, ktorú sleduje BUD."""
    presets = config.BUD_STAY_PRESETS or config.STAY_PRESETS
    return presets[0]["min_nights"], presets[0]["max_nights"]


def _best_now(rows, origin_code, mn, mx):
    orows = [r for r in rows if _row_origin(r) == origin_code]
    combos = stats.cheapest_roundtrip_now(orows, min_nights=mn, max_nights=mx)
    return combos[0] if combos else None


def _combined_over_time_fig(rows, origins, mn, mx):
    """Jeden graf, čiara na odletisko: najlacnejší round-trip za 1 os. v čase."""
    colors = {"VIE": "#3B82F6", "BUD": "#F59E0B"}
    fig = go.Figure()
    for o in origins:
        orows = [r for r in rows if _row_origin(r) == o]
        series = stats.cheapest_roundtrip_over_time(orows, min_nights=mn, max_nights=mx)
        if not series:
            continue
        c = colors.get(o, "#93C5FD")
        fig.add_trace(go.Scatter(
            x=[s[0] for s in series], y=[s[1] for s in series],
            mode="lines+markers", name=f"Z {_origin_label(o)} ({o})",
            line=dict(width=3, color=c), marker=dict(size=6, color=c)))
    fig = _style(fig)
    if fig.data:
        fig.add_hline(
            y=config.REFERENCE_PER_PERSON_EUR, line_dash="dash", line_color="#94A3B8",
            annotation_text=f"pred 2 r.: ~{config.REFERENCE_PER_PERSON_EUR:.0f} €",
            annotation_position="top left", annotation_font_color="#CBD5E1")
    return fig


def _comparison_section_html(rows, dest_code, origins):
    """Hero porovnanie: karty na odletisko + verdikt + spoločný graf v čase."""
    mn, mx = _comparison_nights()
    nights_lbl = f"{mn}" if mn == mx else f"{mn}–{mx}"
    bests = {o: _best_now(rows, o, mn, mx) for o in origins}
    valid = {o: b for o, b in bests.items() if b}
    winner = min(valid, key=lambda o: valid[o]["total"]) if valid else None

    cards = []
    for o in origins:
        b = bests[o]
        accent = "cmp-vie" if o == config.ORIGIN else "cmp-bud"
        win = " cmp-win" if (winner == o and len(valid) > 1) else ""
        if b:
            price = f"{b['total']:.0f} €"
            sub = (f"{_fmt_date(b['out_date'])} → {_fmt_date(b['ret_date'])} · "
                   f"{b['nights']} nocí")
            chip = _trip_chip(o, b["out_date"], b["ret_date"])
            pp = b["total"]
            data_pp = f" data-pp='{pp:.2f}'"
            total = (f"<div class='cmp-total js-total'>Spolu {_DEFAULT_PERSONS} os.: "
                     f"<b>{pp * _DEFAULT_PERSONS:.0f} €</b></div>")
        else:
            price, sub, chip, data_pp, total = "—", "zatiaľ bez dát", "", "", \
                "<div class='cmp-total js-total'></div>"
        badge = "<span class='cmp-badge'>najlacnejšie</span>" if win else ""
        cards.append(
            f"<div class='cmp-card {accent}{win}'{data_pp}>"
            f"<div class='cmp-org'>Z {html.escape(_origin_from(o))} "
            f"<span class='cmp-code'>{html.escape(o)}</span>{badge}</div>"
            f"<div class='cmp-price'>{price}<span class='cmp-unit'> /os</span></div>"
            f"<div class='cmp-sub'>{html.escape(sub)}{chip}</div>"
            f"{total}</div>")

    verdict = ""
    if len(valid) == 2:
        srt = sorted(valid.items(), key=lambda kv: kv[1]["total"])
        diff = round(srt[1][1]["total"] - srt[0][1]["total"], 2)
        if diff == 0:
            verdict = "Rovnaká najlacnejšia cena z oboch miest."
        else:
            verdict = (f"<b>{html.escape(_origin_label(srt[0][0]))}</b> je teraz lacnejšia o "
                       f"<b>{diff:.0f} €/os</b> (pri {nights_lbl} nociach).")

    chart = _chart_html(_combined_over_time_fig(rows, origins, mn, mx))
    verdict_html = f"<p class='cmp-verdict'>{verdict}</p>" if verdict else ""
    return f"""<section class='cmp-section'>
  <h2>Odkiaľ sa oplatí letieť do {html.escape(_dest_to(dest_code))}?</h2>
  <p class='caption'>Najlacnejší {nights_lbl}-nocový round-trip za 1 os. naprieč <b>celým septembrom</b> —
    dátum môže byť iný než náš. Slúži len na porovnanie odletísk.</p>
  <div class='cmp-grid'>{''.join(cards)}</div>
  {verdict_html}
  <div class='cmp-chart'>
    <h3>Vývoj najlacnejšej ceny v čase</h3>
    {chart}
  </div>
</section>"""


def _primary_trip_series(rows):
    """Cena NÁŠHO fixného letu v čase (delegované do stats — jeden zdroj pravdy)."""
    return stats.primary_trip_over_time(rows, config.PRIMARY_TRIP, config.ORIGIN)


def _primary_trip_now(rows):
    """Cena nášho hlavného fixného letu (config.PRIMARY_TRIP) pri poslednom meraní."""
    series = _primary_trip_series(rows)
    if not series:
        return None
    t = config.PRIMARY_TRIP
    nights = (date.fromisoformat(t["ret"]) - date.fromisoformat(t["out"])).days
    return {**series[-1], "nights": nights,
            "low": min(s["total"] for s in series)}


def _primary_trip_fig(series):
    """Vývoj ceny nášho termínu — samostatný graf, aby hero nepotreboval nič nižšie."""
    xs = [s["observed_at"] for s in series]
    ys = [s["total"] for s in series]
    fig = go.Figure(go.Scatter(
        x=xs, y=ys, mode="lines+markers", name="Náš termín",
        line=dict(color=_AMBER, width=3), marker=dict(color=_AMBER, size=7),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.10)"))
    fig = _style(fig)
    fig.update_layout(showlegend=False, margin=dict(l=55, r=20, t=20, b=45))
    if xs:
        fig.add_hline(
            y=config.REFERENCE_PER_PERSON_EUR, line_dash="dash", line_color="#94A3B8",
            annotation_text=f"pred 2 r.: ~{config.REFERENCE_PER_PERSON_EUR:.0f} €",
            annotation_position="top left", annotation_font_color="#CBD5E1")
    return fig


def _persons_toggle_html():
    buttons = "".join(
        f"<button class='pp-btn{' active' if n == _DEFAULT_PERSONS else ''}' "
        f"data-n='{n}'>{n}</button>"
        for n in _PERSONS_OPTIONS
    )
    return (f"<div class='pp-wrap'><span class='toggle-label'>Počet osôb:</span>"
            f"<div class='toggle pp-toggle' role='tablist'>{buttons}</div></div>"
            f"<div class='pp-note'>{html.escape(config.PERSONS_HINT)}</div>")


def _primary_hero_html(rows):
    """Zvýraznený náš let navrchu: fixný termín + cena/os + počítadlo osôb.

    Ukazuje VÝHRADNE cenu nášho termínu (nikdy nie najlacnejšiu naprieč mesiacom),
    a má vlastný graf, aby sa dalo rozhodnúť bez pozerania na iné termíny nižšie.
    """
    series = _primary_trip_series(rows)
    info = _primary_trip_now(rows)
    if not info:
        return ""
    t = config.PRIMARY_TRIP
    pp, low = info["total"], info["low"]

    high = max(s["total"] for s in series)
    if high - low < 0.005:
        # cena sa ešte nikdy nepohla → žiadny zelený "kupuj teraz" signál
        low_html = (f"<div class='hero-low'>Cena sa zatiaľ nehla "
                    f"({len(series)} meraní)</div>")
    elif pp <= low + 0.005:
        low_html = ("<div class='hero-low hero-low-hit'>Teraz je najnižšie, čo sme videli"
                    f" · {low:.0f} €/os</div>"
                    f"<div class='hero-seats'>⚠️ {html.escape(config.SEATS_HINT)}</div>")
    else:
        low_html = (f"<div class='hero-low'>Najnižšie doteraz: <b>{low:.0f} €/os</b>"
                    f" · teraz +{pp - low:.0f} €</div>")

    chart = _chart_html(_primary_trip_fig(series), height="260px")
    return f"""<section class='hero'>
  <div class='hero-eyebrow'>Náš let</div>
  <h2 class='hero-title'>Z {html.escape(_origin_from(t['origin']))} do {html.escape(_dest_to(t['destination']))}
    · {_fmt_date(t['out'])} → {_fmt_date(t['ret'])}</h2>
  <p class='caption'>{info['nights']} nocí · fixný termín · Ryanair {html.escape(t['origin'])}↔{html.escape(t['destination'])}</p>
  {_persons_toggle_html()}
  <div class='hero-card' data-pp='{pp:.2f}'>
    <div class='hero-price'>{pp:.0f} €<span class='cmp-unit'> /os</span></div>
    <div class='hero-total js-total'>Spolu {_DEFAULT_PERSONS} os.: <b>{pp * _DEFAULT_PERSONS:.0f} €</b></div>
  </div>
  {low_html}
  <div class='hero-legs'>Odlet {_fmt_date(t['out'])}: <b>{info['out_price']:.0f} €</b>
    &nbsp;·&nbsp; Návrat {_fmt_date(t['ret'])}: <b>{info['ret_price']:.0f} €</b></div>
  <div class='hero-chart'>{chart}</div>
</section>"""


def _secondary_html(inner):
    """Všetko, čo NIE je náš termín — vizuálne aj textovo oddelené do úzadia."""
    t = config.PRIMARY_TRIP
    return f"""<div class='secondary'>
  <div class='sep'><span class='sep-text'>Iné termíny · len orientačne</span></div>
  <p class='sep-note'>Ceny nižšie sú za <b>iné dátumy</b> než náš let
    ({_fmt_date(t['out'])} → {_fmt_date(t['ret'])}). Môžu byť lacnejšie — ale nekupuj podľa nich.</p>
  {inner}
</div>"""


def _dest_panel(rows, dest, index):
    """Panel destinácie: hore porovnanie odletísk, pod tým detaily na plnú šírku."""
    origins = [o for o in _all_origins() if any(_row_origin(r) == o for r in rows)]
    if not origins:
        origins = [config.ORIGIN]
    hidden = "" if index == 0 else " hidden"
    # Náš hlavný let (fixný termín) navrchu, len na jeho destinácii
    hero = _primary_hero_html(rows) if dest["code"] == config.PRIMARY_TRIP.get("destination") else ""
    # Porovnávacia hlavička len keď je čo porovnávať (2+ odletiská)
    comparison = _comparison_section_html(rows, dest["code"], origins) if len(origins) > 1 else ""
    details = "".join(_origin_block(rows, dest["code"], o) for o in origins)
    rest = f"{comparison}<div class='origin-stack'>{details}</div>"
    # Keď hore stojí náš termín, všetko ostatné patrí pod oddeľovač do úzadia.
    # Bez hera (žiadne dáta pre náš let) niet od čoho oddeľovať → zobraz normálne.
    body = f"{hero}{_secondary_html(rest)}" if hero else rest
    return f"""<div class='dest-panel' data-dest='{html.escape(dest['code'])}'{hidden}>
  {body}
</div>"""


def build_report_html(rows):
    if not rows:
        return (f"<!DOCTYPE html><html lang='sk'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
                f"<title>Ryanair Lefkada tracker</title><style>{_CSS}</style></head>"
                f"<body><div class='wrap'><header><div class='eyebrow'>Ryanair price tracker</div>"
                f"<h1>Vývoj cien leteniek</h1></header>"
                f"<section><p class='empty'>Zatiaľ žiadne dáta</p></section></div></body></html>")

    updated = stats.latest_observed_at(rows)
    panels = "".join(
        _dest_panel([r for r in rows if r.get("destination") == d["code"]], d, i)
        for i, d in enumerate(config.DESTINATIONS)
    )
    # Prepínač destinácií má zmysel len pri viacerých destináciách; pri jednej
    # (Lefkada) by len zavadzal, tak ho vôbec nezobrazujeme.
    if len(config.DESTINATIONS) > 1:
        dest_buttons = "".join(
            f"<button class='dest-btn{' active' if i == 0 else ''}' data-dest='{html.escape(d['code'])}'>"
            f"{html.escape(d['label'])}</button>"
            for i, d in enumerate(config.DESTINATIONS)
        )
        dest_toggle = (f"<div class='toggle-wrap'><span class='toggle-label'>Destinácia:</span>"
                       f"<div class='toggle' role='tablist'>{dest_buttons}</div></div>")
    else:
        dest_toggle = ""

    return f"""<!DOCTYPE html>
<html lang='sk'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Ryanair Lefkada tracker</title>
{_PLOTLY_JS}
<style>{_CSS}</style>
</head>
<body>
<div class='wrap'>
  <header>
    <div class='eyebrow'>Ryanair price tracker · 6.–13.9.2026</div>
    <h1>Budapešť → Lefkada</h1>
    <div class='updated'>Posledná aktualizácia: {html.escape(_fmt_dt(updated))}</div>
  </header>
  {dest_toggle}
  {panels}
  <footer>Dáta: services-api.ryanair.com · generované lokálne, bez LLM</footer>
</div>
{_TOGGLE_JS}
</body>
</html>"""


def write_report(rows, path):
    Path(path).write_text(build_report_html(rows), encoding="utf-8")
