FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Required for building xero-python, regex, ratelimit (C extensions)
RUN apt-get update && apt-get install -y build-essential

WORKDIR /code/

COPY pyproject.toml .
COPY uv.lock .

ENV UV_PROJECT_ENVIRONMENT="/usr/local/"
RUN uv sync --all-groups --frozen

COPY src/ src
COPY tests/ tests
COPY scripts/ scripts
COPY deploy.sh .

CMD ["python", "-u", "src/component.py"]
