# Results

One rider's ten outdoor rides with a power meter, Corsica, August to October
2026: 24.7 hours of riding, from dawn rides on a 58 km loop to a long day in
the north. Every number here is from rides the models had not seen, and every
check that failed is here too.

Times are minutes and seconds, wind speeds are at 10 m above the ground unless
said otherwise, and there are no watts (a power, a speed and a grade on the
same stretch are enough to work out the rider's mass).

## 1. The wind, rebuilt and checked

`tools/wind_check.py`: the wind rebuilt from the model grids at measuring
stations within 15 km of each ride, hour by hour, from one hour before the
start to one hour after the end. Stations: Météo-France hourly data (mean wind
over 10 minutes at 10 m) and the METAR of Ajaccio airport (LFKJ).

| Model | Where | Hours | Measured (m/s) | Model (m/s) | Mean error | r | Vector error (m/s) | Direction error, wind ≥ 2 m/s |
|---|---|---|---|---|---|---|---|---|
| AROME HD | all stations | 210 | 2.5 | 1.7 | 1.2 | 0.65 | 1.9 | 25° (129 h) |
| AROME HD | LFKJ (METAR) | 62 | 2.5 | 1.6 | 1.0 | 0.50 | 1.5 | 18° (47 h) |
| ECMWF IFS | all stations | 210 | 2.5 | 1.3 | 1.5 | 0.36 | 2.6 | 48° (129 h) |
| ECMWF IFS | LFKJ (METAR) | 62 | 2.5 | 1.0 | 1.5 | 0.51 | 2.3 | 50° (47 h) |

AROME gets the direction right to about 25° and follows the ups and downs of
the wind (r 0.65), but **it is a third too weak** on these rides: 1.7 m/s
where the stations measured 2.5. IFS, at 9 km, is weaker still and often wrong
about the direction. AROME is the headline; IFS is the second opinion, one
line of the range. The model's low bias is not corrected: the rider is not on
a mast in an open field (section 3).

<details><summary>Station by station</summary>

| Model | Station | Hours | Measured | Model | Mean error | r | Vector error | Direction error |
|---|---|---|---|---|---|---|---|---|
| AROME HD | AJACCIO | 31 | 2.4 | 1.6 | 1.0 | 0.42 | 1.5 | 17° (22 h) |
| AROME HD | AJACCIO-PARATA | 31 | 2.5 | 1.5 | 1.3 | 0.38 | 2.0 | 34° (19 h) |
| AROME HD | BOCOGNANO | 8 | 2.9 | 0.8 | 2.1 | 0.92 | 2.9 | 59° (5 h) |
| AROME HD | CAGNANO | 8 | 5.0 | 3.1 | 2.0 | 0.84 | 2.2 | 10° (8 h) |
| AROME HD | CAP CORSE | 8 | 2.7 | 1.8 | 1.5 | 0.70 | 2.3 | 50° (4 h) |
| AROME HD | CAP SAGRO | 8 | 6.8 | 4.1 | 2.7 | 0.91 | 3.0 | 10° (8 h) |
| AROME HD | MOCA-CROCE | 15 | 1.8 | 0.8 | 1.1 | 0.40 | 1.9 | 50° (9 h) |
| AROME HD | OLETTA | 8 | 1.6 | 3.0 | 1.6 | 0.70 | 2.5 | 20° (2 h) |
| AROME HD | PILA-CANALE | 15 | 0.9 | 1.1 | 0.6 | 0.47 | 1.3 | 55° (1 h) |
| AROME HD | SAMPOLO | 8 | 0.9 | 1.0 | 0.6 | 0.36 | 1.1 | 60° (1 h) |
| AROME HD | SANTO PIETRO DI TENDA | 8 | 2.1 | 2.1 | 0.6 | 0.32 | 1.8 | 36° (3 h) |
| ECMWF IFS | AJACCIO | 31 | 2.4 | 1.0 | 1.4 | 0.48 | 2.2 | 53° (22 h) |
| ECMWF IFS | AJACCIO-PARATA | 31 | 2.5 | 1.5 | 1.2 | 0.61 | 1.8 | 17° (19 h) |
| ECMWF IFS | BOCOGNANO | 8 | 2.9 | 0.4 | 2.5 | −0.03 | 3.1 | 30° (5 h) |
| ECMWF IFS | CAGNANO | 8 | 5.0 | 2.5 | 2.6 | 0.56 | 3.3 | 31° (8 h) |
| ECMWF IFS | CAP CORSE | 8 | 2.7 | 3.6 | 2.2 | −0.03 | 4.4 | 85° (4 h) |
| ECMWF IFS | CAP SAGRO | 8 | 6.8 | 1.6 | 5.1 | 0.61 | 6.0 | 59° (8 h) |
| ECMWF IFS | MOCA-CROCE | 15 | 1.8 | 0.8 | 1.3 | −0.04 | 2.3 | 90° (9 h) |
| ECMWF IFS | OLETTA | 8 | 1.6 | 1.7 | 1.8 | −0.35 | 2.5 | 64° (2 h) |
| ECMWF IFS | PILA-CANALE | 15 | 0.9 | 0.8 | 0.5 | 0.49 | 0.9 | 37° (1 h) |
| ECMWF IFS | SAMPOLO | 8 | 0.9 | 0.8 | 0.4 | 0.86 | 1.9 | 136° (1 h) |
| ECMWF IFS | SANTO PIETRO DI TENDA | 8 | 2.1 | 1.8 | 0.7 | 0.77 | 1.9 | 27° (3 h) |

</details>

## 2. Does the wind help predict the speed?

`tools/validate.py`, leave one ride out: each ride's 30-second speeds are
predicted by models that only saw the nine other rides (2 889 pieces in all).
The same model is run with and without the wind columns.

| Model | AROME wind | IFS wind | Without the wind |
|---|---|---|---|
| TabPFN v2 | **0.687 m/s** | 0.706 m/s | 0.718 m/s |
| Linear regression | 1.213 m/s | 1.191 m/s | 1.183 m/s |
| Constant | | | 2.287 m/s |

Mean absolute error on the speed. TabPFN predicts the speed with 40 % less
error than a linear regression, and it is the only one the wind helps: 4 %
less error with AROME's wind, 2 % with IFS's (the weather model that matched
the stations better helps more). A straight line does better *without* the
wind. TabPFN's 80 % interval holds the true speed 76 % of the time: a little
too narrow.

## 3. Flat roads ridden both ways

`tools/both_ways.py`: stretches of at least 400 m, nearly flat (grade within
2 %), ridden one way on one ride and the other way on the same or another ride
(within 25 m), at powers within 15 % of each other. 38 such pairs, 61 km in
all, on four rides along the west coast; on average the wind was 0.92 m/s
stronger in the face on the first way.

| | Way into the wind, slower by |
|---|---|
| Raw speed | 3.8 % |
| At the same power and grade (physics, no wind) | 3.6 % |
| Wind taken out: 0.54 of the 10 m wind reaches the rider | **0.1 %** |
| … 0.29 of it | 1.6 % |
| … all of it | −2.3 % (too much taken out) |
| TabPFN: at the same power and grade, headwind turned both ways | 1.7 % |
| TabPFN: wind taken out (its ghost) | 1.8 % (the gap stays) |

At the same power and grade, the way into the wind is 3.6 % slower; once the
wind is taken out with the share a textbook log wind profile gives for a rider
1.2 m above open country (0.54, chosen before looking), **the gap melts to
0.1 %**. The physics here has its drag and rolling resistance fitted on the
rider's steady stretches (kept in memory, never printed). Each pair is
noisy (6.6 % apart on average either way), so this is an average over 38
pairs, not a measurement. One ride (4 October) was partly ridden on a
friend's wheel, which no file records.

**TabPFN fails this test.** Its ghost (section 4) barely reacts to the
headwind on these flat roads: taking the wind out moves the gap from 1.7 to
1.8 %, where the physics takes out all of it. Whatever TabPFN learned about
the headwind from these ten rides, mostly in light wind and with a model wind
a third too weak, is too faint to show here.

## 4. The ghost

### The first ghost lied

The first version asked TabPFN for each 30-second piece twice: with the wind
of that moment, and with the wind set to zero. Its ghost beat the rider on
**every ride**, by 1.5 to 8.6 %, as if the wind had always helped, the two
calmest days included (0.4 and 0.6 m/s on average). The physics, given the
same wind, said a few seconds either way on most rides.

The model had learned the kind of day from the wind. These rides come in two
kinds: windier mornings on the west coast road, flat and fast, and calm days
inland, with climbs. A strong crosswind meant "coast", no wind meant
"inland". Asked for a ride with no wind at all, TabPFN answered for an inland
day, and the ghost slowed down. It also explains part of section 2: the wind
columns helped TabPFN most on one calm inland ride (16 August: 0.69 against
1.01 m/s), where they told it what kind of day it was, not what the air did.

`tools/counterfactuals.py` then tried, ride by ride, what moves the ghost (AROME, gap
as a share of the ghost's time; positive: the wind cost time):

| Ride | Wind | Physics, 0.54 | All wind to zero (first version) | Crosswind to zero | Headwind to zero | Model without crosswind, headwind to zero | **Headwind turned around** |
|---|---|---|---|---|---|---|---|
| 14 Aug | 0.6 m/s | −0.06 % | −3.28 % | −3.05 % | −0.68 % | −0.47 % | **+0.35 %** |
| 16 Aug | 0.4 m/s | −0.09 % | −1.52 % | −1.49 % | −0.00 % | −0.04 % | **−0.02 %** |
| 19 Aug | 2.7 m/s | −1.88 % | −8.63 % | −3.76 % | −4.13 % | −4.39 % | **−0.96 %** |
| 24 Aug | 0.9 m/s | +0.35 % | −2.97 % | −2.69 % | −0.13 % | −0.07 % | **+0.00 %** |
| 29 Aug | 2.0 m/s | +0.71 % | −7.11 % | −6.10 % | −2.38 % | −1.65 % | **+0.03 %** |
| 31 Aug | 0.9 m/s | +0.15 % | −3.37 % | −3.29 % | −0.36 % | −0.14 % | **+0.02 %** |
| 13 Sep | 1.1 m/s | +0.13 % | −4.20 % | −3.09 % | −0.68 % | −0.58 % | **+0.09 %** |
| 20 Sep | 0.8 m/s | +0.15 % | −3.51 % | −3.09 % | −0.25 % | +0.10 % | **−0.10 %** |
| 27 Sep | 1.4 m/s | +0.29 % | −4.27 % | −4.77 % | +0.74 % | +0.61 % | **+0.33 %** |
| 4 Oct | 1.6 m/s | +0.19 % | −3.57 % | −3.46 % | −0.57 % | +0.14 % | **−0.07 %** |
| *Mean distance to the physics* | | | *4.2 points* | *3.5* | *0.9* | *0.7* | ***0.3*** |

Zeroing the crosswind did most of the damage. Dropping the crosswind from the
model was not enough: a headwind of zero still meant "calm day" (29 August:
the rider had the wind slightly in the face on average, and the ghost still
won). What worked is to never ask for a day without wind: the ghost now keeps
the crosswind and takes the mean of two answers, with the headwind as it was
and turned around. Whatever the model learned from the *strength* of the wind
(the kind of day) is the same in both and cancels out; what is left is what
the wind did by blowing one way rather than the other. On loops, that is a
few seconds; on the one long ride with a tailwind (19 August), a minute or
more.

The physics column uses a textbook bike (drag area 0.40 m², rolling
resistance 0.005) and the rider's mass; it is a cross-check, not the truth,
but section 3 says its 0.54 share is about right.

### The ghost of every ride

Each ride judged with TabPFN learned from the nine others, the headwind
turned around, against the physics. Moving time; the gap is the rider's time
minus the ghost's (positive: the wind cost time; negative: it gave some).

| Ride | Moving | Wind | **TabPFN, AROME** (headline) | TabPFN, IFS | Physics, AROME, 0.54 / 0.29 | Physics, IFS, 0.54 / 0.29 | Linear regression, AROME, same ghost | First ghost (TabPFN, wind to zero) |
|---|---|---|---|---|---|---|---|---|
| 14 Aug, inland | 88 min | 0.6 m/s | **+0:20** | −0:17 | −0:03 / −0:02 | −0:04 / −0:02 | +0:32 | −3:20 |
| 16 Aug, inland | 110 min | 0.4 m/s | **−0:01** | −0:07 | −0:07 / −0:04 | −0:13 / −0:07 | +1:04 | −1:55 |
| 19 Aug, the north, one way | 340 min | 2.7 m/s | **−3:34** | −1:05 | −7:05 / −3:52 | −2:16 / −1:18 | −0:36 | −34:53 |
| 24 Aug, west coast | 63 min | 0.9 m/s | **+0:00** | −0:59 | +0:13 / +0:07 | +0:09 / +0:05 | +0:09 | −1:56 |
| 29 Aug, west coast | 89 min | 2.0 m/s | **+0:02** | −0:11 | +0:39 / +0:21 | +0:08 / +0:04 | +4:52 | −7:05 |
| 31 Aug, west coast | 62 min | 0.9 m/s | **+0:01** | −0:21 | +0:06 / +0:03 | +0:12 / +0:07 | +0:03 | −2:11 |
| 13 Sep, the loop | 188 min | 1.1 m/s | **+0:10** | −0:33 | +0:15 / +0:07 | −1:23 / −0:45 | +0:41 | −8:30 |
| 20 Sep, the loop | 180 min | 0.8 m/s | **−0:11** | −0:18 | +0:16 / +0:09 | −1:19 / −0:43 | +0:24 | −6:43 |
| 27 Sep, the loop | 169 min | 1.4 m/s | **+0:35** | −0:34 | +0:30 / +0:16 | −0:36 / −0:20 | +0:08 | −7:55 |
| 4 Oct, west coast | 191 min | 1.6 m/s | **−0:08** | −1:40 | +0:23 / +0:12 | +0:06 / +0:02 | +10:34 | −7:40 |

**On these rides, it wasn't the wind.** They were mostly dawn rides in light
wind (0.4 to 2 m/s at 10 m on average), and on a loop what the wind takes on
the way out it mostly gives back on the way home: on every loop, the AROME
lines (TabPFN and physics) stay within 40 seconds, and every line within
1:40. The one
exception is the long one-way day in the north (19 August), with the wind
mostly at the back: it gave between 1 and 7 minutes, depending on the
weather model and on how much of it reached the rider.

TabPFN and the physics agree on the loops. On the one-way day, TabPFN's
ghost (−3:34) sits with the physics at 0.29 (−3:52), half the 0.54 one; with
section 3, this says TabPFN's headwind effect is on the weak side. The IFS
lines lean towards "the wind helped" on several loops where AROME and the
physics see nothing: IFS gets the direction wrong by 48° on average
(section 1), and a wrong direction turns a headwind into a tailwind. They
stay in the range; the headline is AROME.

## 5. Did TabPFN earn its place?

- **As a model of the rider: yes.** On rides it never saw, it predicts the
  speed of each 30-second piece with 40 % less error than a linear regression
  on the same columns (0.69 against 1.21 m/s), with no tuning, in a minute on
  a small CPU. That is what the ghost's legs are made of.
- **As a ghost: better than a line.** The same ghost made with the linear
  regression strays far from the physics on two rides (+4:52 on 29 August,
  +10:34 on 4 October, where the physics says +0:39 and +0:23): 1.4 points
  from the physics on average, against 0.3 for TabPFN.
- **As a judge of the wind: not on its own.** Its first ghost was fooled by
  what the wind says about the kind of day, and said so with confidence on
  every ride. Turned around, the headwind gives an honest ghost that agrees
  with the physics on the loops, but its effect is too faint on flat roads
  ridden both ways, where the physics gets it right.
- So the verdict never rests on TabPFN alone: the page gives TabPFN's ghost
  as the headline and every other line (the other weather model, the physics
  in open country and among trees and houses) as its range. On these rides
  they all say the same thing: it wasn't the wind.

## Reproduce

```bash
wasitthewind prepare rides/*.fit --out prepared/ --tracks
python tools/wind_check.py prepared/ --meteofrance H_20_latest-2025-2026.csv.gz --metar LFKJ:41.9236:8.8029 --markdown wind.md
WASITTHEWIND_RIDER_KG=... python tools/validate.py prepared/ --out validate.json   # sections 2 and 4
python tools/counterfactuals.py prepared/ --out counterfactuals.json                 # section 4, the first ghost
WASITTHEWIND_RIDER_KG=... python tools/both_ways.py prepared/ --validate validate.json  # section 3
```

The rider's mass is read from the environment, for the physics lines only,
and is never written or printed.
