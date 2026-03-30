FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY fixtures ./fixtures
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[dev]"

CMD ["uvicorn", "maintenance_copilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
