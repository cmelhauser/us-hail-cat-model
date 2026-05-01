# CONUS Hail Catastrophe Model v2.1

A radar-based probabilistic hail hazard model for the Continental United States using NOAA MESH data, ERA5 reanalysis, and stochastic event simulation.

---

## Version

This repository implements **v2.1** of the CONUS Hail Catastrophe Model.

v2.1 is a **methodology hardening release** of v2.0 focused on:

- calibration robustness
- environmental filtering improvements
- event grouping quality
- extreme value threshold diagnostics
- sparse-safe stochastic simulation
- expanded testing and documentation

This is **not a structural redesign (v3.0)**. The 15-stage pipeline remains intact.

---

## Critical Implementation Rules (v2.1)

1. Sparse event storage is authoritative (rows, cols, vals)
2. Stage 13 must be sparse-safe (no dense event cubes)
3. Stage 05 must support deterministic fallback
4. SPC reports are validation only
5. Vulnerability is placeholder (not claims-calibrated)

---

## Quick Start (Safe Run)

python -m py_compile run_pipeline.py scripts/*.py
pytest -q tests
python run_pipeline.py --dry-run
python run_pipeline.py

---

## Stochastic (Stage 13)

python scripts/13_generate_stochastic_catalog.py --n-years 1000
python scripts/13_generate_stochastic_catalog.py --n-years 50000

---

## Validation

python run_pipeline.py --validate

---

## Known Limitations

- Long return periods extrapolated
- Spatial dependence simplified
- Vulnerability not calibrated
- No exposure layer

---

## License
MIT
