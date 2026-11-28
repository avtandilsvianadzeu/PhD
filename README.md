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
publishers' own RSS feeds listed in `tools/news_sources.json`, and a Google News search for every EU country (one in English naming the country, one in the local edition with the local word for artificial intelligence), so national AI news comes in without adding sources by hand. Google News items keep the name of the outlet that published them. The feeds cover trade press, European technology
and research press, the European Commission and EU bodies. The job keeps items about AI, data centres and
compute, assigns them to EU27 countries by country and city names, drops items with future or old
dates, writes `news.json`, checks it and commits it. Each item keeps only the headline, date,
publisher and a link to the original article. The page reads `news.json` and
shows the items in the News tab and in each country factsheet. Run it by hand from the Actions tab
with "Run workflow".

Standard GitHub-hosted runners are free on public repositories, so this job uses none of the
minutes of private repositories on the same account. GitHub pauses scheduled workflows in a public
repository after 60 days without activity; if that happens, enable the workflow again from the
Actions tab.

The news job is scheduled twice an hour (GitHub may skip some runs) and the calls job four times a day. News covers the EU, Europe-wide items and every European country on the map. An item is kept when its headline or the first lines of its summary name
an EU country or the EU, and its text names AI, data centres or computing. `tools/news_cases.json` holds headlines
that must be kept or dropped; `python tools/fetch_news.py --selftest` checks them on every push and before every
read. Each run writes a report on the Actions page: feeds that did not answer, and on-topic headlines that were
left out because no EU place was found. Feeds are read side by side, so one slow publisher cannot hold up the job, and a feed with broken XML (a stray "&", control characters) is repaired and read instead of skipped. Links lose their tracking parameters, so the same story from two feeds is listed once. A headline counts as on topic when it names AI itself, not only AI data centres or compute, and a headline that names a European company without a place (for example "SAP plans job cuts") counts for the company's home country, from the `companies` list in `tools/news_sources.json`. Headlines that announce a call, a tender or an event (conference, summit, workshop, webinar, info day) get a small label on the page, from the `kinds` patterns in the same file, and the job report counts them. Each country keeps up to 20 items and the EU up to 60. To add a source, add its RSS address to `tools/news_sources.json`. To add a story the feeds no longer
hold, add it to `tools/news_pinned.json` (country code, date, headline in your own words, link, publisher); the
job keeps it until it is older than the age limit.

## Map views

The page opens in the satellite view. The switch at the foot of the map offers Satellite and Atlas
(the green Eurostat map). The MapLibre library sits in `vendor/` (BSD licence); the
base maps are OpenFreeMap, Mapzen terrain tiles on AWS and Esri World Imagery, credited in the map corner.
Country borders in every view are the Eurostat GISCO outlines in `data/eu-countries.geojson` (EU
conventions: Crimea within Ukraine, Abkhazia and South Ossetia within Georgia, Kosovo* as Eurostat draws
it); the outlines of the United Kingdom, Armenia and Azerbaijan come from Natural Earth. The OpenStreetMap border lines are switched off.
Every institution and site carries its address and coordinates, shown in its Location card; the automatic
check fails if one is missing.

## EU tenders

The calls job also searches the EU Funding and Tenders portal for open tenders on AI, data centres, high performance computing, cloud and digital twins, and lists them in the Calls tab with the label "EU tender". This pass is optional: if the portal answers differently, the grant calls are still published, and the job log says how many tenders were found.

## Projects tab

The Projects tab lists every running Horizon Europe project in `projects.json` (up to 400): filters by
engineering topic (structures and bridges, monitoring and digital twins, materials and testing, geotechnics and
transport infrastructure, building physics, energy and fire, sustainable built environment, metrology) or AI, by
the coordinator's country, and sorting by start, end or EU contribution. Each row links to the CORDIS project page.

## Calls on the built environment

Besides AI, computing and data, the calls job keeps calls and tenders on construction and buildings, transport
infrastructure, monitoring and inspection, fire safety, natural hazards and metrology, even when they do not name
AI. They carry their own topic labels in the Calls tab and appear on the Collaboration page under the matching topic.

## Collaboration page

The Collaboration page groups the entries by engineering topic (structures and bridges, monitoring and
digital twins, weigh-in-motion, materials, geotechnics, buildings, sustainability, metrology, computer
vision) and lists, for each topic, the groups and centres that work on it and the open EU calls whose
title fits. It is built in the browser from `data` already on the page and from `calls.json`.

## EU projects

`.github/workflows/projects.yml` runs `tools/fetch_projects.py` every Wednesday. It downloads the CORDIS open data
file of Horizon Europe projects (Publications Office of the European Union, CC BY 4.0), keeps running projects
that match an engineering topic of the atlas or name AI in their title, and writes `projects.json`. The
Collaboration page lists them per topic with a link to the CORDIS project page. The job reads the bulk file
only and does not query the CORDIS search pages.

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
