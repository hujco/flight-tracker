import html
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import plotly.graph_objects as go

from . import config, stats


def _fmt_date(iso):
    """'2026-09-14' -> '14.09.2026' (EU)."""
    d = date.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


_LOCAL_TZ = "Europe/Bratislava"


def _to_local(iso):
    """observed_at -> aware datetime v našom pásme.

    Zber beží v UTC (GitHub Actions), ale report číta človek v CEST. Bez prevodu
    stránka ukazovala napr. 06:43, kým na hodinkách bolo 08:43 — vyzeralo to,
    že dáta sú o 2 h staršie, než v skutočnosti sú.
    Staré riadky bez offsetu boli tiež písané v UTC, tak ich tak aj berieme.
    """
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo(_LOCAL_TZ))
    except Exception:      # chýbajúca tz databáza → aspoň korektné UTC
        return dt.astimezone(timezone.utc)


def _fmt_dt(iso):
    """'2026-08-08T06:43+00:00' -> '08.08.2026 08:43' (náš čas)."""
    dt = _to_local(iso)
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year} {dt.hour:02d}:{dt.minute:02d}"


def _age_html(iso):
    """Vek dát slovom + varovanie, keď zber vypadol.

    Report sa pregeneruje aj po zlyhaní zberu, takže bez tohto vyzerá stará
    stránka úplne normálne.
    """
    age_h = (datetime.now(timezone.utc) - _to_local(iso)).total_seconds() / 3600.0
    if age_h < 0:
        return ""
    if age_h < 1:
        label = f"pred {max(1, int(age_h * 60))} min"
    elif age_h < 24:
        label = f"pred {age_h:.0f} h"
    else:
        label = f"pred {age_h / 24:.0f} d"
    # cron beží každé 2 h; GitHub ho vie oneskoriť, ale 6 h už je výpadok
    stale = " age-stale" if age_h >= 6 else ""
    return f"<span class='age{stale}'>{label}</span>"

# Brand palette (dark dashboard: blue data + amber highlight)
_COLORWAY = ["#3B82F6", "#F59E0B", "#60A5FA", "#FBBF24", "#93C5FD",
             "#FCD34D", "#2563EB", "#D97706", "#A5B4FC", "#FB923C"]
_AMBER = "#F59E0B"

# Počítadlo osôb v porovnávacej hlavičke (prepočíta spolu cenu za skupinu).
_PERSONS_OPTIONS = sorted({1, 2, 4, config.PERSONS})
# musí sedieť s config.PERSONS — inak najviditeľnejšie číslo na stránke („Spolu N os.")
# ukazuje iný počet ľudí než KPI karty nižšie, ktoré rátajú s config.PERSONS
_DEFAULT_PERSONS = config.PERSONS


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


def _chart_html(fig, height="380px"):
    # plotly.js sa načíta raz v <head>, takže tu nikdy nevkladáme knižnicu
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        default_width="100%",
        default_height=height,
        config={"displayModeBar": False, "responsive": True},
    )


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
* { box-sizing: border-box; min-width: 0; }
html, body { max-width: 100%; overflow-x: hidden; }
body {
  margin: 0; padding: 24px 16px 48px;
  background: #0B1120;
  background-image: radial-gradient(1200px 600px at 80% -10%, rgba(59,130,246,0.12), transparent),
                    radial-gradient(900px 500px at 0% 0%, rgba(245,158,11,0.06), transparent);
  color: #E2E8F0; font-family: 'Fira Sans', system-ui, sans-serif;
  line-height: 1.6; -webkit-text-size-adjust: 100%;
}
.wrap { width: 100%; max-width: 720px; margin: 0 auto; }
header { margin-bottom: 22px; }
.eyebrow { color: #60A5FA; font-weight: 600; letter-spacing: .08em;
  text-transform: uppercase; font-size: 12px; }
h1 { font-size: clamp(22px, 6vw, 30px); font-weight: 700; margin: 6px 0 4px;
  color: #F8FAFC; overflow-wrap: anywhere; }
.updated { color: #94A3B8; font-size: 13px; font-family: 'Fira Code', monospace; }
.age { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px;
  font: 600 11px 'Fira Sans', sans-serif; background: rgba(148,163,184,0.14);
  color: #CBD5E1; border: 1px solid rgba(148,163,184,0.28); }
.age-stale { background: rgba(248,113,113,0.16); color: #F87171;
  border-color: rgba(248,113,113,0.45); }
.caption { color: #94A3B8; font-size: 13px; margin: 2px 0 0; }
.empty { color: #94A3B8; }

/* Náš let — jediná karta na stránke */
.hero { background: linear-gradient(180deg, rgba(245,158,11,0.15), rgba(15,23,42,0.55));
  border: 1px solid rgba(245,158,11,0.40); border-radius: 20px;
  padding: 20px 18px 22px; }
.hero-eyebrow { color: #FBBF24; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; font-size: 12px; }
.hero-title { font-size: clamp(17px, 4.6vw, 22px); font-weight: 700; color: #F8FAFC;
  margin: 6px 0 2px; line-height: 1.3; overflow-wrap: anywhere; }
.hero-card { display: flex; align-items: baseline; gap: 8px 24px; flex-wrap: wrap;
  margin: 14px 0 10px; }
.hero-price { font-family: 'Fira Code', monospace; font-size: clamp(34px, 11vw, 44px);
  font-weight: 700; color: #FBBF24; line-height: 1.1; }
.hero-price .cmp-unit { font-size: 16px; }
.hero-total { font-family: 'Fira Code', monospace; font-size: 17px; color: #CBD5E1; }
.hero-total b { color: #F8FAFC; font-size: 21px; }
.hero-legs { font-family: 'Fira Code', monospace; font-size: 13px; color: #94A3B8;
  margin-top: 12px; overflow-wrap: anywhere; }
.hero-legs b { color: #E2E8F0; }
.hero-low { font-family: 'Fira Code', monospace; font-size: 13px; color: #94A3B8;
  margin-bottom: 6px; overflow-wrap: anywhere; }
.hero-low b { color: #E2E8F0; }
.hero-low-hit { color: #4ADE80; font-weight: 600; }
.hero-seats { font-size: 13px; line-height: 1.4; color: #FBBF24; font-weight: 600;
  background: rgba(245,158,11,0.10); border: 1px solid rgba(245,158,11,0.35);
  border-radius: 8px; padding: 8px 12px; margin: 8px 0 6px; }
.hero-chart { margin-top: 12px; }
/* Plotly si inak drží šírku z prvého renderu → na mobile pretekalo */
.hero-chart .plotly-graph-div, .hero-chart .js-plotly-plot,
.hero-chart .svg-container { width: 100% !important; max-width: 100%; }

/* Verdikt + čísla na rozhodnutie */
.verdict { display: inline-block; font-weight: 700; font-size: 13px;
  letter-spacing: .04em; text-transform: uppercase; border-radius: 999px;
  padding: 5px 14px; margin: 10px 0 12px; }
.verdict-good { background: rgba(74,222,128,0.14); color: #4ADE80;
  border: 1px solid rgba(74,222,128,0.45); }
.verdict-mid { background: rgba(148,163,184,0.14); color: #CBD5E1;
  border: 1px solid rgba(148,163,184,0.35); }
.verdict-bad { background: rgba(248,113,113,0.14); color: #F87171;
  border: 1px solid rgba(248,113,113,0.45); }
/* auto-fit grid = zalomí sa sám, nikdy nevznikne vodorovný scroll */
.vstats { display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin-bottom: 4px; }
.vstat { background: rgba(15,23,42,0.45); border: 1px solid rgba(148,163,184,0.14);
  border-radius: 12px; padding: 10px 12px; }
.vstat-label { color: #94A3B8; font-size: 11px; letter-spacing: .06em;
  text-transform: uppercase; }
.vstat-value { font-family: 'Fira Code', monospace; font-size: 16px; font-weight: 600;
  color: #F8FAFC; overflow-wrap: anywhere; }
.vstat-sub { color: #94A3B8; font-size: 11px; overflow-wrap: anywhere; }

/* Počítadlo osôb */
.pp-wrap { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin: 14px 0 2px; }
.toggle-label { color: #94A3B8; font-size: 13px; }
.toggle { display: inline-flex; gap: 4px; background: rgba(30,41,59,0.6);
  border: 1px solid rgba(148,163,184,0.15); border-radius: 12px; padding: 4px; }
.pp-btn { cursor: pointer; border: 0; background: transparent; color: #94A3B8;
  font: 600 13px 'Fira Sans', sans-serif; padding: 8px 16px; border-radius: 9px;
  min-width: 44px; min-height: 40px; transition: background .2s, color .2s; }
.pp-btn.active { background: #F59E0B; color: #0B1120; }
.pp-btn:hover:not(.active) { color: #E2E8F0; }
.pp-note { color: #94A3B8; font-size: 12px; line-height: 1.45; margin-top: 6px; }

footer { margin-top: 28px; color: #64748B; font-size: 12px; }

@media (max-width: 420px) {
  body { padding: 18px 12px 40px; }
  .hero { padding: 16px 14px 18px; border-radius: 16px; }
  .vstats { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
}
"""


_PLOTLY_JS = "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js' charset='utf-8'></script>"

_TOGGLE_JS = """<script>
(function () {
  // Počítadlo osôb: prepočíta spolu cenu skupiny z ceny za 1 os. (data-pp)
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
  // Plotly si drží šírku z prvého renderu — po otočení/zmene okna ju prepočítaj,
  // inak graf preteká cez okraj a stránka sa scroluje do strany.
  var t;
  window.addEventListener("resize", function () {
    clearTimeout(t);
    t = setTimeout(function () {
      if (!window.Plotly) return;
      document.querySelectorAll(".plotly-graph-div").forEach(function (g) {
        window.Plotly.Plots.resize(g);
      });
    }, 150);
  });
})();
</script>"""


def _out_bought():
    return getattr(config, "OUT_LEG_BOUGHT", False)


def _primary_trip_series(rows):
    """Séria, o ktorej sa ešte rozhodujeme (súčet, alebo len návrat po kúpe odletu)."""
    return stats.decision_series(rows, config.PRIMARY_TRIP, config.ORIGIN,
                                 _out_bought())


def _primary_trip_now(rows):
    """Aktuálny stav toho, o čom sa rozhodujeme + ceny oboch nôh na kontext."""
    series = _primary_trip_series(rows)
    if not series:
        return None
    t = config.PRIMARY_TRIP
    nights = (date.fromisoformat(t["ret"]) - date.fromisoformat(t["out"])).days
    legs = stats.primary_trip_over_time(rows, t, config.ORIGIN)
    info = {**series[-1], "nights": nights, "low": min(s["total"] for s in series)}
    if legs:                       # ceny nôh sú stále sledované, aj tá kúpená
        info.setdefault("out_price", legs[-1]["out_price"])
        info.setdefault("ret_price", legs[-1]["ret_price"])
    return info


def _primary_trip_fig(series):
    """Vývoj ceny nášho termínu — samostatný graf, aby hero nepotreboval nič nižšie."""
    # os X tiež v našom čase — inak graf tvrdí niečo iné než hlavička nad ním
    # (a miešanie naivných a +00:00 reťazcov si Plotly vykladá nekonzistentne)
    xs = [_to_local(s["observed_at"]).replace(tzinfo=None).isoformat() for s in series]
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


def _verdict_html(series, price):
    """Čísla, podľa ktorých sa dá rozhodnúť „kúpiť alebo čakať".

    Holá cena nestačí — bez percentilu a trendu používateľ nevie, či je 222 €
    dobré alebo zlé. Rovnaké čísla posiela aj denný Telegram súhrn.
    """
    if len(series) < 2:
        return ""
    values = [s["total"] for s in series]
    pct = stats.percentile_of(values, price)
    week = [s["total"] for s in stats.window_series(series, 7)]
    day = stats.window_series(series, 1)
    change = None
    if len(day) > 1 and day[0]["total"]:
        change = 100.0 * (price - day[0]["total"]) / day[0]["total"]
    days_left = stats.days_until(config.PRIMARY_TRIP["out"])

    if pct is None:
        tone, verdict = "", "—"
    elif pct >= 75:
        tone, verdict = "bad", "Drahé oproti histórii"
    elif pct <= 25:
        tone, verdict = "good", "Lacné oproti histórii"
    else:
        tone, verdict = "mid", "Bežná cena"

    def stat(label, value, sub=""):
        return (f"<div class='vstat'><div class='vstat-label'>{html.escape(label)}</div>"
                f"<div class='vstat-value'>{value}</div>"
                f"<div class='vstat-sub'>{html.escape(sub)}</div></div>")

    cells = [stat("Voči histórii", f"{pct:.0f}. percentil",
                  f"{len(series)} meraní · min {min(values):.0f} €")]
    if week:
        cells.append(stat("Za 7 dní", f"{min(week):.0f} – {max(week):.0f} €", "rozsah /os"))
    if change is not None:
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "▬")
        cells.append(stat("Za 24 h", f"{arrow} {change:+.1f} %", "zmena ceny"))
    if days_left >= 0:
        cells.append(stat("Do odletu", f"{days_left} dní", "okno sa zatvára"))

    return (f"<div class='verdict verdict-{tone}'>{html.escape(verdict)}</div>"
            f"<div class='vstats'>{''.join(cells)}</div>")


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

    if _out_bought():
        paid = config.OUT_LEG_PAID_EUR
        eyebrow = "Ostáva kúpiť návrat"
        headline = (f"Návrat z {_dest_to(t['destination'])} do "
                    f"{_origin_from(t['origin'])} · {_fmt_date(t['ret'])}")
        sub = (f"{info['nights']} nocí · odlet {_fmt_date(t['out'])} už kúpený "
               f"za {paid:.0f} €/os")
        # Spolu = zaplatený odlet + aktuálny návrat, aby bolo vidno reálnu sumu
        legs_html = (f"<div class='hero-legs'>Odlet {_fmt_date(t['out'])}: "
                     f"<b>✓ kúpené {paid:.0f} €</b>"
                     f"&nbsp;·&nbsp; Spolu za osobu by vyšlo <b>{paid + pp:.0f} €</b>"
                     f"&nbsp;·&nbsp; {_DEFAULT_PERSONS} os.: "
                     f"<b>{(paid + pp) * _DEFAULT_PERSONS:.0f} €</b></div>")
    else:
        eyebrow = "Náš let"
        headline = (f"Z {_origin_from(t['origin'])} do {_dest_to(t['destination'])}"
                    f" · {_fmt_date(t['out'])} → {_fmt_date(t['ret'])}")
        sub = (f"{info['nights']} nocí · fixný termín · Ryanair "
               f"{t['origin']}↔{t['destination']}")
        legs_html = (f"<div class='hero-legs'>Odlet {_fmt_date(t['out'])}: "
                     f"<b>{info['out_price']:.0f} €</b>&nbsp;·&nbsp; "
                     f"Návrat {_fmt_date(t['ret'])}: <b>{info['ret_price']:.0f} €</b></div>")

    return f"""<section class='hero'>
  <div class='hero-eyebrow'>{html.escape(eyebrow)}</div>
  <h2 class='hero-title'>{html.escape(headline)}</h2>
  <p class='caption'>{html.escape(sub)}</p>
  {_persons_toggle_html()}
  <div class='hero-card' data-pp='{pp:.2f}'>
    <div class='hero-price'>{pp:.0f} €<span class='cmp-unit'> /os</span></div>
    <div class='hero-total js-total'>Spolu {_DEFAULT_PERSONS} os.: <b>{pp * _DEFAULT_PERSONS:.0f} €</b></div>
  </div>
  {low_html}
  {_verdict_html(series, pp)}
  {legs_html}
  <div class='hero-chart'>{chart}</div>
</section>"""


def build_report_html(rows):
    if not rows:
        return (f"<!DOCTYPE html><html lang='sk'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
                f"<title>Ryanair Lefkada tracker</title><style>{_CSS}</style></head>"
                f"<body><div class='wrap'><header><div class='eyebrow'>Ryanair price tracker</div>"
                f"<h1>Vývoj cien leteniek</h1></header>"
                f"<section><p class='empty'>Zatiaľ žiadne dáta</p></section></div></body></html>")

    updated = stats.latest_observed_at(rows)
    # Sledujeme JEDINÝ fixný let (ubytovanie je zaplatené na 6.9.), takže report
    # je len o ňom. Žiadne iné termíny, žiadne iné odletisko — Viedeň na náš
    # termín nelieta a porovnávať ju s fixným Budapešťou bolo zavádzajúce.
    body = _primary_hero_html(rows)
    if not body:
        body = "<section><p class='empty'>Pre náš termín zatiaľ žiadne dáta</p></section>"

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
    <div class='updated'>Posledná aktualizácia: {html.escape(_fmt_dt(updated))} {_age_html(updated)}</div>
  </header>
  {body}
  <footer>Dáta: services-api.ryanair.com · generované lokálne, bez LLM</footer>
</div>
{_TOGGLE_JS}
</body>
</html>"""


def write_report(rows, path):
    Path(path).write_text(build_report_html(rows), encoding="utf-8")
