# CONUS Hail Catastrophe Model — v2.1
# Reproducible environment using micromamba (conda-compatible, minimal image)
#
# Build:
#   docker build -t hail-cat-model:2.1 .
#
# Run pipeline interactively:
#   docker run --rm -it \
#     -v $(pwd)/data:/app/data \
#     -v $(pwd)/logs:/app/logs \
#     -v $(pwd)/docs/figures:/app/docs/figures \
#     hail-cat-model:2.1 bash
#
# Run a single stage:
#   docker run --rm \
#     -v $(pwd)/data:/app/data \
#     -v $(pwd)/logs:/app/logs \
#     hail-cat-model:2.1 \
#     python run_pipeline.py --only 07
#
# NOTE: data/, logs/, and docs/figures/ are intentionally not baked into the
# image. Mount them as volumes so outputs persist outside the container.

FROM mambaorg/micromamba:1.5-jammy AS base

# --- OS-level dependencies (eccodes, GEOS, PROJ) ---
USER root
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        libeccodes-dev \
        libgeos-dev \
        libproj-dev \
        proj-bin \
        libhdf5-dev \
        libnetcdf-dev \
        git \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# --- Create a non-root user for running the pipeline ---
RUN useradd -m -u 1001 hailmodel
WORKDIR /app

# --- Conda environment ---
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml
RUN micromamba install -y -n base -f /tmp/environment.yml && \
    micromamba clean --all --yes

# Activate the base env for all subsequent RUN, CMD, ENTRYPOINT
ARG MAMBA_DOCKERFILE_ACTIVATE=1

# --- Python project (editable install for stage scripts) ---
COPY --chown=hailmodel:hailmodel . /app/
RUN pip install --no-deps -e ".[dev]" --quiet

# --- Ensure data dirs exist (will be volume-mounted at runtime) ---
RUN mkdir -p /app/data/historical /app/data/analysis /app/data/stochastic \
             /app/logs /app/docs/figures && \
    chown -R hailmodel:hailmodel /app

USER hailmodel

# --- Health check: syntax + dry-run ---
RUN python -m py_compile run_pipeline.py scripts/*.py && \
    python run_pipeline.py --dry-run

ENTRYPOINT ["python"]
CMD ["run_pipeline.py", "--help"]
