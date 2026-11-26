# Reep coverage: top five leagues vs football-data

Register release: 2026-11-23.1. Football-data matches from 2020 onwards: **11,282**.

## Overall

| Link | Matches | Share |
|---|---|---|
| Matched to a Reep match | 11,281 | 100.0% |
| Has a FotMob match ID | 11,239 | 99.6% |
| Has a WhoScored match ID | 10,983 | 97.3% |
| Has an Understat match ID | 493 | 4.4% |
| Has a Sofascore match ID | 10,980 | 97.3% |

## By league

| league | matches | reep | fotmob | whoscored | understat |
|---|---|---|---|---|---|
| BUNDESLIGA | 1926 | 1926 | 1918 | 1872 | 0 |
| EPL | 2390 | 2390 | 2390 | 2330 | 493 |
| LALIGA | 2409 | 2409 | 2397 | 2349 | 0 |
| LIGUE1 | 2157 | 2157 | 2147 | 2103 | 0 |
| SERIEA | 2400 | 2399 | 2387 | 2329 | 0 |

## By season

| season | matches | reep | fotmob | whoscored | understat |
|---|---|---|---|---|---|
| 2020 | 1826 | 1826 | 1826 | 1826 | 0 |
| 2021 | 1826 | 1826 | 1826 | 1826 | 0 |
| 2022 | 1826 | 1826 | 1826 | 1826 | 0 |
| 2023 | 1752 | 1752 | 1752 | 1752 | 380 |
| 2024 | 1752 | 1752 | 1752 | 1752 | 27 |
| 2025 | 1752 | 1751 | 1750 | 1751 | 38 |
| 2026 | 548 | 548 | 507 | 250 | 48 |

## Method

- Join key: football-data `(date, home, away)` to Reep match label, allowing +/- 1 day.
- Team names mapped through Reep aliases, with a hand-checked 145-team map.
- No provider crawl was needed: IDs come from the register itself.
