#!/usr/bin/env python3
"""Generates dark-theme profile stat cards into ./assets using the GitHub GraphQL API.

Env:
  GITHUB_TOKEN  API token (a PAT in the STATS_TOKEN secret also counts private contributions)
  GH_USER       defaults to Dhruvagg5006
Without data, zeroed cards are written so the images never break.
"""
import os
import json
import datetime as dt
import urllib.request
from xml.sax.saxutils import escape as esc

USER = os.environ.get("GH_USER", "Dhruvagg5006")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
os.makedirs(OUT, exist_ok=True)

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
NS = 'xmlns="http://www.w3.org/2000/svg"'

QUERY = """
query($login:String!){
  user(login:$login){
    name
    contributionsCollection{
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
    }
    repositories(ownerAffiliations:OWNER, isFork:false, first:100, orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{ stargazerCount languages(first:8, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name color } } } }
    }
  }
}
"""


def fetch():
    if not TOKEN:
        return None
    try:
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
            headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "profile-stats"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["data"]["user"]
    except Exception as e:  # noqa: BLE001
        print("API error:", e)
        return None


def parse(u):
    today = dt.date.today()
    if not u:
        days = [(today - dt.timedelta(days=364 - i), 0) for i in range(365)]
        return dict(name="Dhruv Aggarwal", days=days, total=0, commits=0, private=0, prs=0, issues=0, stars=0, repos=0, langs={})
    cc = u["contributionsCollection"]
    days = sorted(
        (dt.date.fromisoformat(d["date"]), d["contributionCount"])
        for w in cc["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    )
    langs, stars = {}, 0
    for r in u["repositories"]["nodes"]:
        stars += r["stargazerCount"]
        for e in r["languages"]["edges"]:
            n = e["node"]
            size, color = langs.get(n["name"], (0, n["color"] or "#8b949e"))
            langs[n["name"]] = (size + e["size"], color)
    return dict(
        name=u["name"] or USER, days=days, total=cc["contributionCalendar"]["totalContributions"],
        commits=cc["totalCommitContributions"], private=cc["restrictedContributionsCount"],
        prs=cc["totalPullRequestContributions"], issues=cc["totalIssueContributions"],
        stars=stars, repos=u["repositories"]["totalCount"], langs=langs,
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
    defs = (
        '<linearGradient id="ln" gradientUnits="userSpaceOnUse" x1="60" y1="0" x2="820" y2="0">'
        '<stop offset="0" stop-color="#00e5ff"/><stop offset="0.55" stop-color="#8b5cf6"/><stop offset="1" stop-color="#ff2bd6"/></linearGradient>'
        '<linearGradient id="fl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8b5cf6" stop-opacity="0.35"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient>'
        '<filter id="gl" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="3"/></filter>'
        '<linearGradient id="tt" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#38bdf8"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>'
    )
    inner = (
        f'<text x="40" y="38" font-size="20" font-weight="700" fill="url(#tt)">{esc(s["name"])}\'s Contribution Graph</text>'
        f'<text x="820" y="36" text-anchor="end" font-size="11" fill="#8b949e">last 31 days · {s["total"]} this year · updated {fmt(dt.date.today())}</text>'
        f"{chip_svg}{grid}{xl}"
        f'<path d="{area}" fill="url(#fl)"/>'
        f'<path d="{path}" fill="none" stroke="url(#ln)" stroke-width="4" filter="url(#gl)" opacity="0.8"/>'
        f'<path d="{path}" fill="none" stroke="url(#ln)" stroke-width="2.5" stroke-linecap="round"/>'
        f"{dots}{peak}"
    )
    write("activity-graph.svg", card(W, H, inner, defs))


def stats(s):
    rows = [
        ("⭐", "Stars earned", s["stars"]),
        ("📝", "Commits (year)", s["commits"]),
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
