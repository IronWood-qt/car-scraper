FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install poetry

# Install dependencies only first (better layer caching) - --no-root skips
# installing this project as a package, since main.py's own sys.path setup
# is how it finds src/, not a pip install.
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --without dev --no-root --no-interaction

# Now the actual code.
COPY main.py ./
COPY src/ ./src/

ENTRYPOINT ["python", "main.py"]
