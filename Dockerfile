FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ZoneInfo is used for the store's local date, even on a minimal Linux image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 emporio \
    && useradd --uid 1000 --gid emporio --create-home emporio

COPY requirements-lock.txt requirements.txt pyproject.toml ./
RUN python -m pip install -r requirements-lock.txt

COPY src/ ./src/
RUN python -m pip install --no-build-isolation --no-deps -e .

COPY data/ ./data/
COPY evaluation/cases.json ./evaluation/cases.json
COPY docker/entrypoint.sh /usr/local/bin/emporio-entrypoint

RUN chmod 755 /usr/local/bin/emporio-entrypoint \
    && mkdir -p runtime evaluation/runs examples \
    && chown -R emporio:emporio runtime evaluation/runs examples

USER emporio
ENTRYPOINT ["emporio-entrypoint"]
CMD ["chat"]

# Optional build target: runs the same offline suite inside Linux.
FROM base AS test
COPY tests/ ./tests/
COPY scripts/prepare_public.py ./scripts/prepare_public.py
RUN python -m pytest -q -o cache_dir=/tmp/pytest-cache

FROM base AS runtime
