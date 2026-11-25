# PhD Repository

## European AI atlas

`index.html` is the interactive atlas of European AI research and compute, published at
https://avtandilsvianadzeu.github.io/PhD/ (`europe-ai-atlas.html` is an identical copy).

Layers: EuroHPC AI Factories, EuroHPC supercomputers, private AI campuses, research centres,
industry labs, thinkers and EU projects. Every dated item links to its source.

## Automatic checks

`tools/check_atlas.py` runs on every push through GitHub Actions (`.github/workflows/check-atlas.yml`):

- every entry has its fields, a valid layer and a marker inside the map
- every news item has a year and a source link
- plain dashes and straight quotes only
- the counts on the tabs and the country shading match the data
- `index.html` and `europe-ai-atlas.html` stay identical

Every Monday it also checks that all source links still answer. Run it locally with
`python tools/check_atlas.py` (add `--links` for the link check).

## Daily news

`.github/workflows/news.yml` runs `tools/fetch_news.py` every day at 05:23 UTC. It reads the
publishers' own RSS feeds listed in `tools/news_sources.json` (trade press, European technology
and research press, the European Commission and EU bodies), keeps items about AI, data centres and
compute, assigns them to EU27 countries by country and city names, drops items with future or old
dates, writes `news.json`, checks it and commits it. Each item keeps only the headline, date,
publisher and a link to the original article. The page reads `news.json` and
shows the items in the News tab and in each country factsheet. Run it by hand from the Actions tab
with "Run workflow".

Standard GitHub-hosted runners are free on public repositories, so this job uses none of the
minutes of private repositories on the same account. GitHub pauses scheduled workflows in a public
repository after 60 days without activity; if that happens, enable the workflow again from the
Actions tab.

## Map views

The page opens in the satellite view. The switch at the foot of the map offers Satellite and Atlas
(the green Eurostat map). The MapLibre library sits in `vendor/` (BSD licence); the
base maps are OpenFreeMap, Mapzen terrain tiles on AWS and Esri World Imagery, credited in the map corner.
Country borders in every view are the Eurostat GISCO outlines in `data/eu-countries.geojson` (EU
conventions: Crimea within Ukraine, Abkhazia and South Ossetia within Georgia, Kosovo* as Eurostat draws
it); the United Kingdom outline comes from Natural Earth. The OpenStreetMap border lines are switched off.
Every institution and site carries its address and coordinates, shown in its Location card; the automatic
check fails if one is missing.

## Collaboration page

The Collaboration page groups the entries by engineering topic (structures and bridges, monitoring and
digital twins, weigh-in-motion, materials, geotechnics, buildings, sustainability, metrology, computer
vision) and lists, for each topic, the groups and centres that work on it and the open EU calls whose
title fits. It is built in the browser from `data` already on the page and from `calls.json`.

## Open data and sharing

`data/atlas.json` holds every entry (name, kind, status, address, coordinates, website, summary, topics,
news with links) and is rebuilt with the page. The Browse tab downloads the current view as CSV or JSON,
and every entry, country and view has its own link (Copy link). Keyboard: `/` jumps to search, `Esc`
clears filters. Latest gathers every dated item on the atlas in one timeline; Saved keeps chosen entries in
the browser and compares up to four side by side; the overview shows an entry of the day and the status
and country figures.

## Content and data

Facts in each entry come from the linked sources and are written in our own words. People are named
only with their public professional role, as published by their own institution. To correct or
remove an entry, open an issue in this repository.
