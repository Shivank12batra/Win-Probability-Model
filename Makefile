PY ?= python3
export PYTHONPATH := src

.PHONY: help install test elo sample live

help:
	@echo "make install   - editable install of the package"
	@echo "make elo       - build Elo ratings from football-data.co.uk (2015-2025)"
	@echo "make sample    - fetch a sample FotMob match (shots + events)"
	@echo "make live      - list live top-5 matches right now"

install:
	$(PY) -m pip install -e .

elo:
	$(PY) -m wpm.cli fd-elo --start 2015 --end 2025 --out data/elo/elo_matches.csv

sample:
	$(PY) -m wpm.cli fotmob-match --id 4506349

live:
	$(PY) -m wpm.cli fotmob-live

test:
	$(PY) -m pytest -q
