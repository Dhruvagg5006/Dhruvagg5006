#!/usr/bin/env python3
"""Generates dark-theme profile stat cards using the GitHub GraphQL API.

Env:
  GITHUB_TOKEN      API token (a PAT in the STATS_TOKEN secret also counts private contributions)
  GH_USER           defaults to Dhruvagg5006
  STATS_START_YEAR  first year to count contributions from (default 2024)

Without data, zeroed cards are written so the images never break.
"""
import os
import json
import datetime as dt
import urllib.request
from xml.sax.saxutils import escape as esc

USER = os.environ.get("GH_USER", "Dhruvagg5006")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
START_YEAR = int(os.environ.get("STATS_START_YEAR", "2024"))
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = ROOT
os.makedirs(OUT, exist_ok=True)

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
NS = 'xmlns="http://www.w3.org/2000/svg"'

# GitHub only allows a one-year window per contributionsCollection, so we query year by year.
QUERY_CAL = """
query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){
    name
    contributionsCollection(from:$from, to:$to){
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
    }
  }
}
"""
QUERY_REPOS = """
query($login:String!){
  user(login:$login){
    name
    repositories(ownerAffiliations:OWNER, isFork:false, first:100, orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{ stargazerCount languages(first:8, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name color } } } }
    }
  }
}
"""


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["user"]


def fetch():
    if not TOKEN:
        return None
    try:
        repos = gql(QUERY_REPOS, {"login": USER})
        now = dt.datetime.now(dt.timezone.utc)
        days, tot = {}, dict(commits=0, private=0, prs=0, issues=0)
        for year in range(START_YEAR, now.year + 1):
            frm = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
            to = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now)
            u = gql(QUERY_CAL, {"login": USER, "from": frm.isoformat(), "to": to.isoformat()})
            cc = u["contributionsCollection"]
            for w in cc["contributionCalendar"]["weeks"]:
                for d in w["contributionDays"]:
                    days[dt.date.fromisoformat(d["date"])] = d["contributionCount"]
            tot["commits"] += cc["totalCommitContributions"]
            tot["private"] += cc["restrictedContributionsCount"]
            tot["prs"] += cc["totalPullRequestContributions"]
            tot["issues"] += cc["totalIssueContributions"]
        return dict(name=repos["name"], repos=repos["repositories"], days=days, tot=tot)
    except Exception as e:  # noqa: BLE001
        print("API error:", e)
        return None


def parse(raw):
    today = dt.date.today()
    start = dt.date(START_YEAR, 1, 1)
    if not raw:
        n = (today - start).days + 1
        days = [(start + dt.timedelta(days=i), 0) for i in range(n)]
        return dict(name="Dhruv Aggarwal", days=days, total=0, commits=0, private=0, prs=0, issues=0, stars=0, repos=0, langs={})
    days = sorted((d, c) for d, c in raw["days"].items() if start <= d <= today)
    langs, stars = {}, 0
    for r in raw["repos"]["nodes"]:
        stars += r["stargazerCount"]
        for e in r["languages"]["edges"]:
            n = e["node"]
            size, color = langs.get(n["name"], (0, n["color"] or "#8b949e"))
            langs[n["name"]] = (size + e["size"], color)
    t = raw["tot"]
    return dict(
        name=raw["name"] or USER, days=days, total=sum(c for _, c in days),
        commits=t["commits"], private=t["private"], prs=t["prs"], issues=t["issues"],
        stars=stars, repos=raw["repos"]["totalCount"], langs=langs,
    )


def fmt(d):
    return f"{d.strftime('%b')} {d.day}"


def streaks(days):
    run, longest, run_start, lrange = 0, 0, None, None
    for d, c in days:
        if c > 0:
            if run == 0:
                run_start = d
            run += 1
            if run > longest:
                longest, lrange = run, (run_start, d)
        else:
            run = 0
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1
    end = days[i][0] if i >= 0 else None
    cur = 0
    while i >= 0 and days[i][1] > 0:
        cur += 1
        i -= 1
    crange = (days[i + 1][0], end) if cur else None
    return cur, crange, longest, lrange


def card(w, h, inner, defs=""):
    return (
        f'<svg {NS} width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{FONT}">\n'
        f"<defs>{defs}</defs>\n"
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="#0d1117" stroke="#30363d"/>\n{inner}</svg>\n'
    )


def write(name, s):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(s)


# ----------------------------------------------------------------------------- activity graph
def seg_lengths(pts, steps=60):
    """Arc length of each cubic segment of the smoothed path (used to time the travelling pointer)."""
    out = []
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        xm = (xa + xb) / 2
        p = [(xa, ya), (xm, ya), (xm, yb), (xb, yb)]
        prev, ln = p[0], 0.0
        for k in range(1, steps + 1):
            t = k / steps
            mt = 1 - t
            x = mt**3 * p[0][0] + 3 * mt * mt * t * p[1][0] + 3 * mt * t * t * p[2][0] + t**3 * p[3][0]
            y = mt**3 * p[0][1] + 3 * mt * mt * t * p[1][1] + 3 * mt * t * t * p[2][1] + t**3 * p[3][1]
            ln += ((x - prev[0]) ** 2 + (y - prev[1]) ** 2) ** 0.5
            prev = (x, y)
        out.append(ln)
    return out


def windows_to_anim(windows, dur, begin):
    """Discrete 0/1 opacity animation for a list of (start, end) windows in 0..1 of the cycle."""
    ev = {0.0: 0}
    for s, e in sorted(windows):
        ev[max(0.0, s)] = 1
        ev[min(1.0, e)] = 0
    ev[1.0] = 0
    times = sorted(ev)
    return (
        f'<animate attributeName="opacity" calcMode="discrete" values="{";".join(str(ev[t]) for t in times)}" '
        f'keyTimes="{";".join(f"{t:.5f}" for t in times)}" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
    )


def activity(s):
    last = s["days"][-31:]
    vals = [c for _, c in last]
    n = len(vals)
    total31, mx = sum(vals), max(vals)
    top = max(4, ((mx + 3) // 4) * 4)
    W, H, x0, x1, y0, y1 = 860, 300, 60, 820, 135, 255
    pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * v / top) for i, v in enumerate(vals)]
    path = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        xm = (xa + xb) / 2
        path += f" C{xm:.1f} {ya:.1f} {xm:.1f} {yb:.1f} {xb:.1f} {yb:.1f}"
    area = f"{path} L{x1} {y1} L{x0} {y1} Z"
    grid = ""
    for k in range(5):
        v = top * k / 4
        y = y1 - (y1 - y0) * k / 4
        grid += f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#ffffff" stroke-opacity="0.06" stroke-dasharray="2 4"/>'
        grid += f'<text x="{x0 - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="10" fill="#8b949e">{v:g}</text>'
    xl = "".join(
        f'<text x="{pts[i][0]:.1f}" y="{y1 + 18}" text-anchor="middle" font-size="10" fill="#8b949e">{fmt(last[i][0])}</text>'
        for i in range(0, n, 6)
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#0d1117" stroke="#e6edf3" stroke-width="1.4"/>' for x, y in pts if y < y1 - 0.1
    )
    best_i = vals.index(mx)
    peak = ""
    if mx > 0:
        px, py = pts[best_i]
        peak = (
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="8" fill="none" stroke="#ff2bd6" stroke-opacity="0.6"/>'
            f'<rect x="{px - 30:.1f}" y="{py - 30:.1f}" width="60" height="18" rx="9" fill="#ff2bd6"/>'
            f'<text x="{px:.1f}" y="{py - 17:.1f}" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">peak · {mx}</text>'
        )
    chips = [
        (f"{total31} contributions", "#00e5ff"),
        (f"{mx} best day · {fmt(last[best_i][0])}", "#ffd60a"),
        (f"{total31 / n:.1f} avg / day", "#3b82f6"),
        (f"{sum(1 for v in vals if v)}/{n} active days", "#ff2bd6"),
    ]
    cx, chip_svg = 40, ""
    for text, col in chips:
        w = 28 + len(text) * 6.4
        chip_svg += (
            f'<rect x="{cx}" y="58" width="{w:.0f}" height="26" rx="13" fill="{col}" fill-opacity="0.08" stroke="{col}" stroke-opacity="0.55"/>'
            f'<text x="{cx + w / 2:.0f}" y="75" text-anchor="middle" font-size="11.5" fill="#e6edf3">{esc(text)}</text>'
        )
        cx += w + 12

    # ---- travelling pointer: glides along the curve, pausing exactly on every day, with a tooltip --------
    BEGIN, STEP = 2.2, 0.38                       # start after the line has drawn in; seconds per day
    seg = seg_lengths(pts)
    total_len = sum(seg) or 1.0
    frac = [0.0]
    for ln in seg:
        frac.append(frac[-1] + ln / total_len)
    frac[-1] = 1.0
    fwd = frac
    kp = fwd + fwd[::-1][1:]                      # forward then back (ping-pong) => seamless loop
    m = len(kp)
    kt = [i / (m - 1) for i in range(m)]
    DUR = round(STEP * (m - 1), 2)
    kp_s = ";".join(f"{v:.5f}" for v in kp)
    kt_s = ";".join(f"{v:.5f}" for v in kt)
    motion = (
        f'<animateMotion dur="{DUR}s" begin="{{b}}s" repeatCount="indefinite" calcMode="linear" '
        f'path="{path}" keyPoints="{kp_s}" keyTimes="{kt_s}"/>'
    )
    trail = ""
    for k, (r, op) in enumerate([(3.4, 0.55), (2.8, 0.38), (2.2, 0.24), (1.6, 0.12)], start=1):
        trail += (
            f'<circle r="{r}" fill="#c4b5fd" opacity="{op}" cx="0" cy="0">'
            f'{motion.format(b=round(BEGIN + 0.1 * k, 2))}</circle>'
        )
    pointer = (
        f'<g opacity="0"><set attributeName="opacity" to="1" begin="{BEGIN}s"/>{trail}'
        f'<g><circle r="13" fill="#8b5cf6" opacity="0.45" filter="url(#gl)">'
        f'<animate attributeName="r" values="11;16;11" dur="1.6s" repeatCount="indefinite"/></circle>'
        f'<circle r="8.5" fill="none" stroke="#ff2bd6" stroke-width="1.6">'
        f'<animate attributeName="r" values="7;11;7" dur="1.6s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="1;0.3;1" dur="1.6s" repeatCount="indefinite"/></circle>'
        f'<circle r="4.6" fill="#ffffff" stroke="#00e5ff" stroke-width="2"/>'
        f'{motion.format(b=BEGIN)}</g></g>'
    )
    # tooltip pills (one per day, shown while the pointer is on that day)
    tips = ""
    half = 0.5 / (m - 1)
    for i, ((d, v), (px, py)) in enumerate(zip(last, pts)):
        label = f"{fmt(d)} · {v} contribution{'s' if v != 1 else ''}"
        wd = 24 + len(label) * 6.1
        tx = min(max(px, 40 + wd / 2), 820 - wd / 2)
        ty = py - 50
        wins = [(kt[i] - half, kt[i] + half)]
        if i not in (0, n - 1):
            wins.append((kt[m - 1 - i] - half, kt[m - 1 - i] + half))
        elif i == 0:
            wins.append((1 - half, 1.0))
        tips += (
            f'<g opacity="0">{windows_to_anim(wins, DUR, BEGIN)}'
            f'<rect x="{tx - wd / 2:.1f}" y="{ty:.1f}" width="{wd:.1f}" height="22" rx="11" fill="#0d1117" stroke="#8b5cf6" stroke-opacity="0.8"/>'
            f'<text x="{tx:.1f}" y="{ty + 15:.1f}" text-anchor="middle" font-size="11" fill="#e6edf3">{esc(label)}</text>'
            f'<path d="M{px - 4:.1f} {ty + 22:.1f} L{px:.1f} {ty + 28:.1f} L{px + 4:.1f} {ty + 22:.1f} Z" fill="#8b5cf6" fill-opacity="0.8"/></g>'
        )

    defs = (
        '<linearGradient id="ln" gradientUnits="userSpaceOnUse" x1="60" y1="0" x2="820" y2="0">'
        '<stop offset="0" stop-color="#00e5ff"/><stop offset="0.55" stop-color="#8b5cf6"/><stop offset="1" stop-color="#ff2bd6"/></linearGradient>'
        '<linearGradient id="fl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8b5cf6" stop-opacity="0.35"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient>'
        '<filter id="gl" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>'
        '<linearGradient id="tt" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#38bdf8"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>'
    )
    draw = '<animate attributeName="stroke-dashoffset" from="1" to="0" dur="2s" fill="freeze"/>'
    inner = (
        f'<text x="40" y="38" font-size="20" font-weight="700" fill="url(#tt)">{esc(s["name"])}\'s Contribution Graph</text>'
        f'<text x="820" y="36" text-anchor="end" font-size="11" fill="#8b949e">last 31 days · {s["total"]} since {START_YEAR} · updated {fmt(dt.date.today())}</text>'
        f"{chip_svg}{grid}{xl}"
        f'<path d="{area}" fill="url(#fl)" opacity="0"><animate attributeName="opacity" from="0" to="1" begin="0.6s" dur="1.6s" fill="freeze"/></path>'
        f'<path d="{path}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="0" fill="none" stroke="url(#ln)" stroke-width="4" filter="url(#gl)" opacity="0.8">{draw}</path>'
        f'<path d="{path}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="0" fill="none" stroke="url(#ln)" stroke-width="2.5" stroke-linecap="round">{draw}</path>'
        f"{dots}{peak}{tips}{pointer}"
    )
    write("activity-graph.svg", card(W, H, inner, defs))


# ----------------------------------------------------------------------------- other cards
def stats(s):
    rows = [
        ("⭐", "Stars earned", s["stars"]),
        ("📝", f"Commits (since {START_YEAR})", s["commits"]),
        ("🔒", "Private contribs", s["private"]),
        ("🔀", "Pull requests", s["prs"]),
        ("🐞", "Issues", s["issues"]),
        ("📦", "Repositories", s["repos"]),
    ]
    body = ""
    for i, (ic, label, v) in enumerate(rows):
        y = 78 + i * 24
        body += (
            f'<text x="28" y="{y}" font-size="13" fill="#e6edf3">{ic}</text>'
            f'<text x="52" y="{y}" font-size="13" fill="#c9d1d9">{label}</text>'
            f'<text x="236" y="{y}" text-anchor="end" font-size="13" font-weight="700" fill="#e6edf3">{v}</text>'
        )
    defs = '<linearGradient id="rg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#00e5ff"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient>'
    inner = (
        f'<text x="28" y="40" font-size="18" font-weight="700" fill="#e6edf3">{esc(s["name"])}\'s GitHub Stats</text>{body}'
        '<circle cx="340" cy="120" r="46" fill="none" stroke="#21262d" stroke-width="10"/>'
        '<circle cx="340" cy="120" r="46" fill="none" stroke="url(#rg)" stroke-width="10" stroke-linecap="round"/>'
        f'<text x="340" y="123" text-anchor="middle" font-size="26" font-weight="700" fill="#e6edf3">{s["total"]}</text>'
        '<text x="340" y="142" text-anchor="middle" font-size="10" fill="#8b949e">contributions</text>'
    )
    write("stats.svg", card(420, 210, inner, defs))


def languages(s):
    items = sorted(s["langs"].items(), key=lambda kv: -kv[1][0])[:6]
    tot = sum(v[0] for _, v in items) or 1
    x, bar, leg = 28, "", ""
    for i, (name, (size, color)) in enumerate(items):
        w = 364 * size / tot
        bar += f'<rect x="{x:.1f}" y="62" width="{w:.1f}" height="10" fill="{color}"/>'
        x += w
        cx, cy = 28 + (i % 2) * 190, 106 + (i // 2) * 28
        leg += (
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>'
            f'<text x="{cx + 18}" y="{cy}" font-size="12.5" fill="#c9d1d9">{esc(name)} <tspan fill="#8b949e" font-size="11">{100 * size / tot:.1f}%</tspan></text>'
        )
    if not items:
        leg = '<text x="28" y="110" font-size="12.5" fill="#8b949e">Waiting for the first workflow run…</text>'
    defs = '<clipPath id="c"><rect x="28" y="62" width="364" height="10" rx="5"/></clipPath>'
    inner = (
        '<text x="28" y="40" font-size="18" font-weight="700" fill="#e6edf3">Most Used Languages</text>'
        f'<g clip-path="url(#c)"><rect x="28" y="62" width="364" height="10" fill="#21262d"/>{bar}</g>{leg}'
    )
    write("languages.svg", card(420, 210, inner, defs))


def streak(s):
    cur, crange, longest, lrange = streaks(s["days"])
    first = s["days"][0][0]
    rng = lambda r: f"{fmt(r[0])} – {fmt(r[1])}" if r else "—"  # noqa: E731
    inner = (
        '<line x1="287" y1="30" x2="287" y2="140" stroke="#30363d"/><line x1="573" y1="30" x2="573" y2="140" stroke="#30363d"/>'
        f'<text x="143" y="88" text-anchor="middle" font-size="40" font-weight="700" fill="#00e5ff">{s["total"]}</text>'
        '<text x="143" y="122" text-anchor="middle" font-size="15" font-weight="600" fill="#8b949e">Total Contributions</text>'
        f'<text x="143" y="142" text-anchor="middle" font-size="11" fill="#6e7681">{first.strftime("%b")} {first.day}, {first.year} – Present</text>'
        '<circle cx="430" cy="68" r="38" fill="none" stroke="#ff9500" stroke-width="5" opacity="0.9"/>'
        f'<text x="430" y="80" text-anchor="middle" font-size="34" font-weight="700" fill="#ff9500">{cur}</text>'
        '<text x="430" y="132" text-anchor="middle" font-size="15" font-weight="600" fill="#8b949e">Current Streak</text>'
        f'<text x="430" y="150" text-anchor="middle" font-size="11" fill="#6e7681">{rng(crange)}</text>'
        f'<text x="717" y="88" text-anchor="middle" font-size="40" font-weight="700" fill="#8b5cf6">{longest}</text>'
        '<text x="717" y="122" text-anchor="middle" font-size="15" font-weight="600" fill="#8b949e">Longest Streak</text>'
        f'<text x="717" y="142" text-anchor="middle" font-size="11" fill="#6e7681">{rng(lrange)}</text>'
    )
    write("streak.svg", card(860, 170, inner))


if __name__ == "__main__":
    data = parse(fetch())
    activity(data)
    stats(data)
    languages(data)
    streak(data)
    print("stat cards written to", OUT)
