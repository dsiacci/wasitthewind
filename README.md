# wasitthewind

Was it really the wind?

After a slow ride, the wind is the easy culprit. wasitthewind rebuilds the
wind along your track, then replays the same ride with the wind taken out, at
the same power: your **ghost**. You race it on a map. The gap at the finish is
what the wind cost you, or gave you, with a range. It also points to the
stretches where the wind weighed most, and compares the ride with an earlier
one on the same road.

It is a small web app you run on your own machine: open it, start a new
analysis, drop the FIT file of your bike computer, and the race comes a few
minutes later. Every analysis stays in the list. A command line does the same for
scripts.

It looks back at a ride already ridden. It does not plan routes, pick a start
time or give training advice.

## How it works

**The wind along the ride.** Weather models give the wind on a grid, every
15 minutes for Météo-France AROME (1.3 km), every hour for ECMWF IFS. The tool
asks [Open-Meteo](https://open-meteo.com)'s archive of past forecasts for a
fixed lattice of points every 0.025° in 0.1° blocks around the ride, never for
the track itself, and interpolates in space and time. Each second gets a
headwind and a crosswind at 10 m above the ground. `tools/wind_check.py`
checks that rebuilt wind against measuring stations (Météo-France) and airport
reports (METAR) at the hours of your rides.

**The ghost.** The ride is cut into 30-second pieces. A speed model learned
from your other rides predicts each piece's speed with the wind of that
moment, at the same power, grade, temperature and time in the saddle, and
again with the headwind turned around; the mean of the two is the speed with
no wind. The ghost rides each piece in your time × (speed with the wind ÷
speed without). Stops are the same for both. (Why not just set the wind to
zero? Because the model then answers for a calm day, and calm days are other
roads: see [the first ghost](docs/results.md#the-first-ghost-lied).) The
speed model is [TabPFN](https://github.com/PriorLabs/TabPFN) v2, a tabular
foundation model that takes your rides as context and answers in one pass,
with no training run.

**The range.** What is uncertain becomes lines of the range: the other weather
model, and plain physics instead of TabPFN, with the share of the 10 m wind
that reaches a rider 1.2 m above the road (0.54 in open country, 0.29 among
trees and houses: a log wind profile). The physics fits your drag and rolling
resistance on the steady pieces of your other rides, and needs your mass; it
is read from the environment and never stored or printed.

## Usage

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu  # optional: the CPU build, a much smaller download
pip install "wasitthewind[model] @ git+https://github.com/dsiacci/wasitthewind"

# Your older rides → one-second series with the wind along them, without positions
wasitthewind prepare rides/*.fit --out prepared/

# The web app, at http://127.0.0.1:8766/
export WASITTHEWIND_RIDER_KG=...   # optional, for the physics lines of the range
wasitthewind serve --library prepared/

# The same from the command line
wasitthewind ghost ride.fit --library prepared/ --page ride.html [--compare earlier.fit]
```

The ghost needs at least two other rides with power to learn you from; the
more, the better. Indoor rides and rides without power are refused. The
analyses are kept in `./wasitthewind-data` (`--data`): for each one, the file
you dropped, its series, its verdict as JSON and its page. The app listens on
this machine only; `--host` opens it to a private network (your phone over
Tailscale, say). It has no accounts: never open it to the internet.

Outputs are minutes, seconds, percentages and wind speeds. No watts: a power,
a speed and a grade on the same stretch are enough to work out the rider's
mass.

## What leaves your machine

- **No ride file and no track.** FIT files are read locally; prepared rides
  keep no positions.
- **Wind**: the 0.1° blocks around a ride (about 11 km) and its dates, sent to
  Open-Meteo. The answers are cached on disk.
- **TabPFN**: the weights are downloaded once from Hugging Face; it runs on the
  CPU, with no account, no API and no cost per analysis.
- The pages load nothing from anywhere: their fonts travel inside them and
  there are no map tiles (a tile server would learn which area you looked at).
  Their figures leave out the first and last 2 km, so a screenshot doesn't show
  where you start; the numbers still count the whole ride.

## Data

| What | Source | Licence |
|---|---|---|
| Wind, past forecasts | [Open-Meteo](https://open-meteo.com) historical forecast API, Météo-France AROME HD and ECMWF IFS | CC BY 4.0 |
| Wind measured, to check | Météo-France, [hourly climatological data](https://meteo.data.gouv.fr) | Licence Ouverte 2.0 (Etalab) |
| Airport reports, to check | METAR from the [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu), Iowa State University | free use, credited |
| Model | TabPFN v2 regressor, [Prior-Labs/TabPFN-v2-reg](https://huggingface.co/Prior-Labs/TabPFN-v2-reg) | Prior Labs License 1.1 |
| FIT files | read with [fitdecode](https://github.com/polyvertex/fitdecode) 0.10.0 | MIT |
| Fonts of the pages | Chakra Petch, embedded in each page | SIL Open Font License 1.1 |

Built with PriorLabs-TabPFN.

## Results

On one rider's ten outdoor rides with a power meter (Corsica, August to
October 2026, 24.7 hours), each judged with TabPFN learned from the nine
others: **it wasn't the wind.** On every loop, the headline ghost finishes
within 40 seconds of the rider; only the long one-way day with the wind at
the back moved by minutes (1 to 6, depending on the line of the range).

- The rebuilt wind (AROME) gets the direction within 25° but is a third too
  weak against the stations; ECMWF IFS is worse.
- On flat roads ridden both ways, the way into the wind is 3.6 % slower at
  the same power and grade; with 0.54 of the 10 m wind taken out (the
  textbook share for a rider 1.2 m above open country), the gap melts to
  0.1 %.
- TabPFN predicts the speed on rides it never saw with 40 % less error than
  a linear regression (0.69 against 1.21 m/s). Its **first ghost lied**: with
  the wind set to zero, it beat the rider on every ride, because the model
  had learned the kind of day from the wind. The ghost now turns the
  headwind around instead; it agrees with the physics on the loops, but its
  headwind effect is too faint on the flat roads ridden both ways, so the
  physics stays in the range.

Every table, and what failed: [docs/results.md](docs/results.md).

## Limits

- The wind is rebuilt from weather models, not measured on the bike. On the
  rides it was checked on, AROME was a third weaker than the stations measured,
  its direction within 25°.
- A road between walls, trees or cliffs feels less of the wind than the grid
  says; a gap between two hills, more. The range covers part of that, not all.
- Drafting behind another rider looks like a tailwind to no one: the tool does
  not know you were sheltered.
- The ghost knows you only through your rides: outside their conditions
  (stronger wind, steeper grade, longer ride) it is less sure. On rides in
  light wind, as here, TabPFN learns a faint headwind effect: the physics
  lines of the range matter.

## License

Apache 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Some modules started
from [z2analyzer](https://github.com/dsiacci/z2analyzer), by the same author.
