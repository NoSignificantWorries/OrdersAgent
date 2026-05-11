FROM astral/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ./mail-client/pyproject.toml ./mail-client/uv.lock* ./mail-client/

RUN cd ./mail-client && uv sync --frozen --no-dev --no-install-project

COPY . /app
COPY ./mail-client/ /app/mail-client/

RUN cd /app/mail-client && uv sync --frozen --no-dev

# RUN chown -R appuser:appuser /app

WORKDIR /app/mail-client

ENV PATH="/app/mail-client/.venv/bin:$PATH"
ENV PYTHONPATH="/app/mail-client"

# USER appuser

# EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
