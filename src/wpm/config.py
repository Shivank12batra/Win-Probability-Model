"""Shared configuration: leagues, paths, tuning constants."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WPM_DATA_DIR", ROOT / "data"))

# Top five leagues, keyed by the canonical id used across the project.
LEAGUES = {
    "EPL": {"name": "Premier League", "country": "England", "espn": "eng.1", "fd": "E0"},
    "LALIGA": {"name": "La Liga", "country": "Spain", "espn": "esp.1", "fd": "SP1"},
    "BUNDESLIGA": {"name": "Bundesliga", "country": "Germany", "espn": "ger.1", "fd": "D1"},
    "SERIEA": {"name": "Serie A", "country": "Italy", "espn": "ita.1", "fd": "I1"},
    "LIGUE1": {"name": "Ligue 1", "country": "France", "espn": "fra.1", "fd": "F1"},
}

# Target window for the Poisson model, in minutes.
WINDOW_MINUTES = 5

# Elo defaults.
ELO_START = 1500.0
ELO_K = 20.0
ELO_HOME_ADVANTAGE = 65.0
ELO_SEASON_REGRESSION = 0.25


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
