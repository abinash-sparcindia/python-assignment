FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .

COPY alembic.ini ./
COPY migrations ./migrations
COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "utility_assets.main:app", "--host", "0.0.0.0", "--port", "8000"]
