#!/usr/bin/env python3
"""
Weekly WC 2026 market pull + comparison.

Run on Sundays. Writes to:
  data/raw/<source>/<date>/        -- immutable raw snapshots
  data/derived/                    -- normalized CSVs per source
  results/elo-baseline/<date>/     -- Elo predictions
  results/comparisons/<date>/      -- comparison.csv, comparison.md, actionable.md

Requires only the standard library (httpx if installed for cleaner client; falls back to urllib).
No API keys required at v0 — Kalshi and Polymarket reads are unauthenticated.

Usage:
  python3 tools/weekly_pull.py [YYYY-MM-DD]   # default: today
"""
import csv, json, math, re, sys, time, urllib.request
from datetime import date as _date
from pathlib import Path
from collections import defaultdict

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

ROOT = Path(__file__).parent.parent
TODAY = sys.argv[1] if len(sys.argv) > 1 else _date.today().isoformat()

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_BASE = "https://gamma-api.polymarket.com"
MARTJ42_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
ELORATINGS_URL = "https://www.eloratings.net/World.tsv"

KALSHI_SERIES = [
    ("KXMENWORLDCUP", "outright_winner"),
    ("KXWCGAME", "match_1x2"),
    ("KXWCGROUPWIN", "group_winner"),
    ("KXFIFAADVANCE", "team_advances"),
    ("KXWCGOALLEADER", "top_scorer"),
]

ISO2_TO_FIFA3 = {
    "ES":"ESP","AR":"ARG","FR":"FRA","GB":"ENG","DE":"GER","BR":"BRA","PT":"POR","IT":"ITA",
    "NL":"NED","BE":"BEL","HR":"CRO","MX":"MEX","US":"USA","CA":"CAN","JP":"JPN","KR":"KOR",
    "AU":"AUS","MA":"MAR","SN":"SEN","TN":"TUN","DZ":"ALG","EG":"EGY","GH":"GHA","CM":"CMR",
    "ZA":"RSA","CI":"CIV","CV":"CPV","UY":"URU","CO":"COL","EC":"ECU","PY":"PAR",
    "NO":"NOR","CH":"SUI","AT":"AUT","SE":"SWE","TR":"TUR","UA":"UKR","RS":"SRB","CZ":"CZE",
    "NG":"NGA","JO":"JOR","UZ":"UZB","IR":"IRI","IQ":"IRQ","SA":"KSA","NZ":"NZL","KP":"PRK",
    "DK":"DEN","CD":"COD","HT":"HAI","PA":"PAN","CR":"CRC","HN":"HON","CU":"CUB",
    "WL":"WAL","BA":"BIH","QA":"QAT","CW":"CUW",
}

NAME_TO_FIFA3 = {
    "Argentina":"ARG","Australia":"AUS","Austria":"AUT","Belgium":"BEL","Brazil":"BRA",
    "Cameroon":"CMR","Canada":"CAN","Cape Verde":"CPV","Colombia":"COL","Costa Rica":"CRC",
    "Croatia":"CRO","Czech Republic":"CZE","Czechia":"CZE","Denmark":"DEN","DR Congo":"COD",
    "Congo DR":"COD","Ecuador":"ECU","Egypt":"EGY","England":"ENG","France":"FRA",
    "Germany":"GER","Ghana":"GHA","Haiti":"HAI","Honduras":"HON","Iran":"IRI","IR Iran":"IRI",
    "Iraq":"IRQ","Italy":"ITA","Ivory Coast":"CIV","Jamaica":"JAM","Japan":"JPN","Jordan":"JOR",
    "Mexico":"MEX","Morocco":"MAR","Netherlands":"NED","New Zealand":"NZL","Nigeria":"NGA",
    "Norway":"NOR","Panama":"PAN","Paraguay":"PAR","Portugal":"POR","Saudi Arabia":"KSA",
    "Senegal":"SEN","South Africa":"RSA","South Korea":"KOR","Korea Republic":"KOR",
    "Spain":"ESP","Sweden":"SWE","Switzerland":"SUI","Tunisia":"TUN","Turkey":"TUR",
    "Algeria":"ALG","United States":"USA","USA":"USA","Uruguay":"URU","Uzbekistan":"UZB",
    "Wales":"WAL","Cuba":"CUB","Curaçao":"CUW","North Korea":"PRK","Scotland":"SCO",
    "Serbia":"SRB","Bosnia and Herzegovina":"BIH","Ukraine":"UKR","Northern Ireland":"NIR",
    "North Macedonia":"MKD","Ireland":"IRL","Qatar":"QAT","Other":"OTHER","Bolivia":"BOL",
}


def http_get_json(url, params=None):
    """GET and return JSON. Uses httpx if available, else urllib."""
    if HAS_HTTPX:
        with httpx.Client(timeout=30) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            return r.json()
    if params:
        from urllib.parse import urlencode
        url = url + "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent":"weekly-pull/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def http_get_text(url):
    if HAS_HTTPX:
        with httpx.Client(timeout=30) as c:
            r = c.get(url); r.raise_for_status(); return r.text
    req = urllib.request.Request(url, headers={"User-Agent":"weekly-pull/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def pull_kalshi():
    out = ROOT / "data" / "raw" / "kalshi" / TODAY
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for series, _ in KALSHI_SERIES:
        events = http_get_json(f"{KALSHI_BASE}/events",
            params={"series_ticker":series,"limit":200,"with_nested_markets":"true"})
        (out / f"{series}_events.json").write_text(json.dumps(events, indent=2))
        all_markets, cursor = [], ""
        while True:
            params = {"series_ticker":series,"limit":1000}
            if cursor: params["cursor"] = cursor
            md = http_get_json(f"{KALSHI_BASE}/markets", params=params)
            all_markets.extend(md.get("markets",[]))
            cursor = md.get("cursor","")
            if not cursor: break
            time.sleep(0.3)
        (out / f"{series}_markets.json").write_text(json.dumps({"markets":all_markets}, indent=2))
        summary.append((series, len(events.get("events",[])), len(all_markets)))
        time.sleep(0.5)
    print(f"[kalshi] pulled {sum(m for _,_,m in summary)} markets across {len(KALSHI_SERIES)} series")
    return summary


def normalize_kalshi():
    raw = ROOT / "data" / "raw" / "kalshi" / TODAY
    out = ROOT / "data" / "derived" / f"kalshi_snapshot_{TODAY}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    months = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06","JUL":"07"}

    for m in json.loads((raw/"KXMENWORLDCUP_markets.json").read_text())["markets"]:
        rows.append(dict(match_id="OUTRIGHT-WC2026", market_type="outright_winner",
            outcome=m.get("yes_sub_title",""), team_code=m["ticker"].split("-")[-1],
            ticker=m["ticker"], last_price=m.get("last_price_dollars",""),
            volume=m.get("volume",0), kickoff=""))

    for m in json.loads((raw/"KXWCGAME_markets.json").read_text())["markets"]:
        et = m["event_ticker"]
        mt = re.match(r"KXWCGAME-26([A-Z]{3})(\d{2})([A-Z]{3})([A-Z]{3})", et)
        if not mt: continue
        mon, day, h3, a3 = mt.groups()
        kickoff = f"2026-{months[mon]}-{day}"
        suffix = m["ticker"].split("-")[-1]
        outcome = "home" if suffix == h3 else "away" if suffix == a3 else "draw"
        rows.append(dict(match_id=f"WC26-{h3}-{a3}-{kickoff}", market_type="match_1x2",
            outcome=outcome, team_code=suffix, ticker=m["ticker"],
            last_price=m.get("last_price_dollars",""), volume=m.get("volume",0), kickoff=kickoff))

    for m in json.loads((raw/"KXWCGROUPWIN_markets.json").read_text())["markets"]:
        et = m["event_ticker"]; g = et[-1] if et else "?"
        rows.append(dict(match_id=f"GROUP-{g}-WC2026", market_type="group_winner",
            outcome=m.get("yes_sub_title",""), team_code=m["ticker"].split("-")[-1],
            ticker=m["ticker"], last_price=m.get("last_price_dollars",""),
            volume=m.get("volume",0), kickoff=""))

    for m in json.loads((raw/"KXWCGOALLEADER_markets.json").read_text())["markets"]:
        rows.append(dict(match_id="GOLDENBOOT-WC2026", market_type="top_scorer",
            outcome=m.get("yes_sub_title",""), team_code="",
            ticker=m["ticker"], last_price=m.get("last_price_dollars",""),
            volume=m.get("volume",0), kickoff=""))

    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
        for r in rows: w.writerow(r)
    print(f"[kalshi] wrote {len(rows)} rows to {out.relative_to(ROOT)}")


def pull_polymarket():
    out = ROOT / "data" / "raw" / "polymarket" / TODAY
    out.mkdir(parents=True, exist_ok=True)
    queries = [{"slug":"2026-fifa-world-cup"}, {"tag_slug":"world-cup"}, {"tag_slug":"soccer"}]
    found = {}
    for q in queries:
        r = http_get_json(f"{POLYMARKET_BASE}/events",
            params={**q, "limit":100, "active":"true", "closed":"false"})
        (out / f"events_{list(q.keys())[0]}_{list(q.values())[0]}.json").write_text(json.dumps(r, indent=2))
        for e in r: found[e["id"]] = e
    print(f"[polymarket] pulled {len(found)} active events ({sum(1 for e in found.values() if 'world cup' in (e.get('title','')+e.get('slug','')).lower() or 'fifa' in (e.get('title','')+e.get('slug','')).lower())} WC-related)")
    return found


def normalize_polymarket():
    raw = ROOT / "data" / "raw" / "polymarket" / TODAY
    out = ROOT / "data" / "derived" / f"polymarket_snapshot_{TODAY}.csv"
    rows = []
    seen = set()
    for fp in raw.glob("events_*.json"):
        for e in json.loads(fp.read_text()):
            if e["id"] in seen: continue
            seen.add(e["id"])
            slug, title = e.get("slug",""), e.get("title","")
            if "world-cup" not in slug.lower() and "world cup" not in title.lower(): continue
            if "group" in slug and "winner" in slug:
                m = re.search(r"group-([a-z])", slug)
                match_id = f"GROUP-{(m.group(1).upper() if m else '?')}-WC2026"
                mtype = "group_winner"
            elif "winner" in slug:
                match_id, mtype = "OUTRIGHT-WC2026", "outright_winner"
            else:
                match_id, mtype = f"POLY-EVT-{e['id']}", "other"
            for mkt in e.get("markets", []):
                team = mkt.get("groupItemTitle","") or mkt.get("question","")
                try:
                    prices = json.loads(mkt.get("outcomePrices","[]"))
                    outcomes = json.loads(mkt.get("outcomes","[]"))
                    yes_idx = outcomes.index("Yes") if "Yes" in outcomes else 0
                    yes_price = float(prices[yes_idx])
                except Exception: yes_price = ""
                rows.append(dict(match_id=match_id, market_type=mtype, outcome=team,
                    slug=mkt.get("slug",""), yes_price=yes_price,
                    volume_24h=mkt.get("volume24hr",""), volume=mkt.get("volume",""),
                    liquidity=mkt.get("liquidity","")))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
        for r in rows: w.writerow(r)
    print(f"[polymarket] wrote {len(rows)} rows to {out.relative_to(ROOT)}")


def pull_supporting_data():
    elo_dir = ROOT / "data" / "raw" / "elo" / TODAY
    elo_dir.mkdir(parents=True, exist_ok=True)
    (elo_dir / "World.tsv").write_text(http_get_text(ELORATINGS_URL))
    print(f"[elo] saved World.tsv")

    martj_path = ROOT / "data" / "raw" / "martj42" / TODAY / "results.csv"
    martj_path.parent.mkdir(parents=True, exist_ok=True)
    martj_path.write_text(http_get_text(MARTJ42_URL))
    print(f"[martj42] saved {martj_path.stat().st_size} bytes")


def build_elo_baseline():
    elo = {}
    for line in (ROOT / "data" / "raw" / "elo" / TODAY / "World.tsv").read_text().splitlines():
        parts = line.split("\t")
        if len(parts) < 4: continue
        try: elo[parts[2]] = int(parts[3])
        except: pass
    fifa3_to_elo = {ISO2_TO_FIFA3[k]: v for k, v in elo.items() if k in ISO2_TO_FIFA3}

    fixtures = []
    with open(ROOT / "data" / "raw" / "martj42" / TODAY / "results.csv") as f:
        for row in csv.DictReader(f):
            if row["tournament"] == "FIFA World Cup" and row["date"] >= "2026-01-01" and row["home_score"] == "NA":
                fixtures.append(row)

    HOME_ADV = 65
    def elo_1x2(home, away, country):
        eh, ea = fifa3_to_elo.get(home), fifa3_to_elo.get(away)
        if eh is None or ea is None: return None
        ha = HOME_ADV if (country == "United States" and home == "USA") or \
             (country == "Mexico" and home == "MEX") or (country == "Canada" and home == "CAN") else 0
        diff = eh - ea + ha
        p_h = 1.0 / (1 + 10**(-diff/400))
        p_d = max(0.15, 0.30 - 0.6 * abs(p_h - 0.5))
        ph, pa = p_h * (1-p_d), (1-p_h) * (1-p_d)
        s = ph + p_d + pa
        return ph/s, p_d/s, pa/s

    out_dir = ROOT / "results" / "elo-baseline" / TODAY
    out_dir.mkdir(parents=True, exist_ok=True)
    preds, missing = [], []
    for fx in fixtures:
        h = NAME_TO_FIFA3.get(fx["home_team"]); a = NAME_TO_FIFA3.get(fx["away_team"])
        if not h or not a: missing.append((fx["home_team"], fx["away_team"])); continue
        res = elo_1x2(h, a, fx["country"])
        if res is None: missing.append((h, a)); continue
        ph, pd, pa = res
        mid = f"WC26-{h}-{a}-{fx['date']}"
        for o, p in [("home",ph),("draw",pd),("away",pa)]:
            preds.append(dict(as_of_date=TODAY, match_id=mid, market_type="match_1x2",
                outcome=o, p_model=round(p,4), confidence="low",
                model_version="elo-baseline-v0.1",
                notes=f"Elo: {fx['home_team']} {fifa3_to_elo[h]} vs {fx['away_team']} {fifa3_to_elo[a]}"))

    top_elo = sorted(fifa3_to_elo.items(), key=lambda x: -x[1])[:32]
    weights = [math.exp((r-top_elo[0][1])/200) for _,r in top_elo]
    total = sum(weights)
    for (code, _), w in zip(top_elo, weights):
        preds.append(dict(as_of_date=TODAY, match_id="OUTRIGHT-WC2026",
            market_type="outright_winner", outcome=code, p_model=round(w/total,4),
            confidence="low", model_version="elo-baseline-v0.1",
            notes="Softmax over Elo top-32; placeholder until tournament Monte Carlo lands"))

    with open(out_dir/"predictions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["as_of_date","match_id","market_type","outcome","p_model","confidence","model_version","notes"])
        w.writeheader()
        for p in preds: w.writerow(p)
    print(f"[elo-baseline] wrote {len(preds)} predictions ({len(missing)} fixtures missing teams)")


def canon(name):
    if name in NAME_TO_FIFA3: return NAME_TO_FIFA3[name]
    if len(name) == 3 and name.isupper(): return name
    return name


def _load_model_preds(model_dir, date):
    path = ROOT / "results" / model_dir / date / "predictions.csv"
    if not path.exists():
        return {}
    out = {}
    for r in csv.DictReader(open(path)):
        if r["market_type"] != "match_1x2": continue
        try: out[(r["match_id"], r["market_type"], r["outcome"])] = float(r["p_model"])
        except ValueError: pass
    return out


def build_comparison():
    out = ROOT / "results" / "comparisons" / TODAY
    out.mkdir(parents=True, exist_ok=True)

    elo_preds    = _load_model_preds("elo-baseline",  TODAY)
    poi_preds    = _load_model_preds("poisson-goals", TODAY)
    form_preds   = _load_model_preds("form-last-10",  TODAY)
    e3_preds     = _load_model_preds("ensemble-e3",   TODAY)

    kalshi = {}
    for r in csv.DictReader(open(ROOT/"data"/"derived"/f"kalshi_snapshot_{TODAY}.csv")):
        if not r["last_price"]: continue
        o = canon(r["outcome"]) if r["market_type"] in ("outright_winner","group_winner") else r["outcome"]
        kalshi[(r["match_id"], r["market_type"], o)] = (float(r["last_price"]), float(r["volume"] or 0))

    poly = {}
    for r in csv.DictReader(open(ROOT/"data"/"derived"/f"polymarket_snapshot_{TODAY}.csv")):
        if not r["yes_price"]: continue
        poly[(r["match_id"], r["market_type"], canon(r["outcome"]))] = (float(r["yes_price"]), float(r["volume_24h"] or 0))

    # Pre-compute golden_zone per match: all 3 base models agree on same favourite
    match_ids = {k[0] for k in set(elo_preds)|set(poi_preds)|set(form_preds) if k[0].startswith("WC26-")}
    golden_zones = {}
    for mid in match_ids:
        favs = []
        for preds in (elo_preds, poi_preds, form_preds):
            probs = {o: preds.get((mid,"match_1x2",o)) for o in ("home","draw","away")}
            probs = {o: v for o, v in probs.items() if v is not None}
            if probs: favs.append(max(probs, key=probs.__getitem__))
        golden_zones[mid] = 1 if len(favs) == 3 and len(set(favs)) == 1 else 0

    all_keys = set(elo_preds) | set(poi_preds) | set(form_preds) | set(e3_preds) | set(kalshi) | set(poly)

    rows = []
    for k in sorted(all_keys):
        mid, mt, o = k
        pe   = elo_preds.get(k)
        pp   = poi_preds.get(k)
        pf   = form_preds.get(k)
        pe3  = e3_preds.get(k)
        pk, vk = kalshi.get(k, (None, 0))
        ppm, vp = poly.get(k, (None, 0))

        base = [v for v in (pe, pp, pf) if v is not None]
        pv2 = round(sum(base)/len(base), 4) if len(base) == 3 else None

        gz = golden_zones.get(mid, 0) if mt == "match_1x2" else ""
        edge = round(pv2 - pk, 4) if (pv2 is not None and pk is not None) else ""
        opportunity = "✅" if (gz == 1 and isinstance(edge, float) and edge > 0.03) else ""

        rows.append(dict(
            match_id=mid, market_type=mt, outcome=o,
            p_elo=round(pe,3) if pe else "",
            p_poisson=round(pp,3) if pp else "",
            p_form=round(pf,3) if pf else "",
            p_ensemble_e3=round(pe3,3) if pe3 else "",
            p_ensemble_v2=pv2 if pv2 else "",
            p_kalshi=round(pk,3) if pk else "", v_kalshi=int(vk),
            p_polymarket=round(ppm,3) if ppm else "", v_polymarket=int(vp),
            golden_zone=gz, edge=edge, opportunity=opportunity,
        ))

    cols = ["match_id","market_type","outcome",
            "p_elo","p_poisson","p_form","p_ensemble_e3","p_ensemble_v2",
            "p_kalshi","v_kalshi","p_polymarket","v_polymarket",
            "golden_zone","edge","opportunity"]
    with open(out/"comparison.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({c: r.get(c,"") for c in cols})

    opps = sum(1 for r in rows if r.get("opportunity") == "✅")
    print(f"[compare] wrote {len(rows)} rows to comparison.csv  ({opps} opportunity flags)")
    print(f"[compare] (regenerate comparison.md and actionable.md from comparison.csv)")


def main():
    print(f"Weekly pull for {TODAY}")
    pull_supporting_data()
    pull_kalshi(); normalize_kalshi()
    pull_polymarket(); normalize_polymarket()
    build_elo_baseline()
    build_comparison()
    print(f"\nDone. Inspect:")
    print(f"  results/comparisons/{TODAY}/comparison.csv")
    print(f"  results/comparisons/{TODAY}/comparison.md  (run renderer separately)")


if __name__ == "__main__":
    main()
