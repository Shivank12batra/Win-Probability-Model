import re
import unicodedata

import duckdb
import pandas as pd

con = duckdb.connect("data/raw/reep/reep-register.duckdb", read_only=True)

teams = con.execute(
    """
    SELECT e.reep_id, e.canonical_name, e.gender, e.country, count(b.reep_id) AS nb
    FROM entities e LEFT JOIN bridges b ON b.reep_id = e.reep_id
    WHERE e.entity_type = 'team'
    GROUP BY 1, 2, 3, 4
    """
).df()
aliases = con.execute(
    """
    SELECT p.reep_id, p.alias
    FROM provider_aliases p
    JOIN entities e ON e.reep_id = p.reep_id
    WHERE e.entity_type = 'team'
    """
).df()

print("teams", len(teams), "aliases", len(aliases))


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


teams["norm"] = teams["canonical_name"].map(norm)
aliases["norm"] = aliases["alias"].map(norm)
team_idx = teams.set_index("reep_id")

canon_ids = {}
for row in teams.itertuples(index=False):
    canon_ids.setdefault(row.norm, set()).add(row.reep_id)

alias_ids = {}
for row in aliases.itertuples(index=False):
    if row.reep_id in team_idx.index:
        alias_ids.setdefault(row.norm, set()).add(row.reep_id)

fd = pd.read_csv("data/processed/football_data/matches.csv")
recent = fd[fd.season >= 2020]
team_league = {}
for row in recent.itertuples(index=False):
    team_league.setdefault(row.home, row.league)
    team_league.setdefault(row.away, row.league)

league_country = {
    "EPL": "England",
    "LALIGA": "Spain",
    "BUNDESLIGA": "Germany",
    "SERIEA": "Italy",
    "LIGUE1": "France",
}

overrides = {
    "Ajaccio": "AC Ajaccio",
    "Ath Bilbao": "Athletic Club",
    "Ath Madrid": "Atletico Madrid",
    "Augsburg": "FC Augsburg",
    "Betis": "Real Betis",
    "Bielefeld": "Arminia Bielefeld",
    "Clermont": "Clermont Foot",
    "Dortmund": "Borussia Dortmund",
    "Ein Frankfurt": "Eintracht Frankfurt",
    "Espanol": "Espanyol",
    "Getafe": "Getafe CF",
    "Girona": "Girona FC",
    "Heidenheim": "1. FC Heidenheim",
    "Hertha": "Hertha BSC",
    "La Coruna": "Deportivo La Coruna",
    "Leverkusen": "Bayer Leverkusen",
    "Lorient": "FC Lorient",
    "M'gladbach": "Borussia M'gladbach",
    "Mainz": "Mainz 05",
    "Mallorca": "RCD Mallorca",
    "Monaco": "AS Monaco",
    "Paderborn": "SC Paderborn 07",
    "Salernitana": "US Salernitana",
    "Santander": "Racing Santander",
    "Schalke 04": "Schalke 04",
    "Sociedad": "Real Sociedad",
    "St Etienne": "Saint-Etienne",
    "St Pauli": "St Pauli",
    "Vallecano": "Rayo Vallecano",
}

BAD = re.compile(r"(?:under \d+|u\d{2}| ii$|\(w\)|women|youth|academy|reserves)", re.I)


def choose(candidates: pd.DataFrame, country: str):
    viable = candidates[
        candidates["gender"].isin(["men", None])
        & ~candidates["canonical_name"].str.contains(BAD, regex=True, na=False)
    ]
    if viable.empty:
        viable = candidates
    same_country = viable[viable["country"] == country]
    pool = same_country if not same_country.empty else viable
    return pool.sort_values("nb", ascending=False).iloc[0]


rows = []
unresolved = []
for team, league in sorted(team_league.items()):
    target = overrides.get(team, team)
    key = norm(target)
    ids = canon_ids.get(key, set()) | alias_ids.get(key, set())
    if not ids:
        unresolved.append(team)
        continue
    candidates = team_idx.loc[sorted(ids)].reset_index()
    best = choose(candidates, league_country.get(league))
    rows.append(
        {
            "fd_name": team,
            "league": league,
            "reep_id": best["reep_id"],
            "reep_name": best["canonical_name"],
            "country": best["country"],
            "bridges": int(best["nb"]),
        }
    )

mapping = pd.DataFrame(rows)
print("mapped", len(mapping), "unresolved", len(unresolved))
print("UNRESOLVED:", unresolved)

suspicious = mapping[
    mapping["reep_name"].str.contains(BAD)
    | (mapping["bridges"] < 5)
]
print("SUSPICIOUS:", len(suspicious))
if not suspicious.empty:
    print(suspicious.to_string(index=False))

print()
print(mapping.sort_values(["league", "fd_name"]).to_string(index=False))
mapping.to_csv("config/team_map.csv", index=False)
