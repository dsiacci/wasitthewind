# wasitthewind

*Was it really the wind?* After a ride, this tool rebuilds the wind along the track, replays the ride with the wind taken out at the same power, and races you against that ghost: segment by segment and at the finish, how much time the wind cost or gave.

Work in progress (Hacktoberfest Open-Source AI Challenge, week 4, "Ghost in the Machine").

- The wind comes from open weather-model grids (Open-Meteo: Météo-France AROME, ECMWF IFS), asked for on a fixed lattice of points around the ride, never for the track itself, and checked against measuring stations (Météo-France, Licence Ouverte 2.0) and airport reports (METAR, Iowa Environmental Mesonet).
- `tools/wind_check.py` compares the rebuilt wind with the stations and METAR at the hours of your rides.

License: Apache 2.0. See `NOTICE` for the data sources and third-party licenses.
