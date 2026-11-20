# External heat-health dataset source

**Circadian Timing and Heat Stress in Firefighters** (Mendeley Data, version 1)
- DOI: 10.17632/7ghxcsd9sz.1
- Source: https://data.mendeley.com/datasets/7ghxcsd9sz/1
- Licence: CC BY 4.0
- Study: 21 male professional firefighters, standardized live-fire exposure in AM and PM sessions.
- Variables include core temperature, heart rate, perceived exertion, body mass / total body water, skin temperature, under-PPE temperature/humidity and environmental temperature.
- Citation: Mauvieux B., Markov A., Besnard S., Touitou Y., Edwards B.J. (2025). Circadian modulation of core temperature and thermoregulatory strain during live-fire compartment exposure in firefighters. Mendeley Data, 7ghxcsd9sz.1.

Run from `backend/`:

```bash
python scripts/download_heat_health_dataset.py
```

The current runtime integration automatically detects the CSV files after download and includes compact cohort summaries in the LLM context. If download is unavailable, the user's existing project physiological and Prospie datasets are still integrated. These research datasets do not provide validated disease diagnoses or individual disease-risk labels.
