# StartupIQ backend image. The SAME image runs both the API (uvicorn) and the
# worker (arq) - only the command differs (see docker/docker-compose.yml).

FROM python:3.11-slim

# Don't write .pyc files; flush stdout/stderr immediately so container logs are
# live rather than buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install the package + its dependencies. We copy pyproject and the app together
# because setuptools needs the package source present to build it.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# Migration files (not part of the installed `app` package) so we can run
# `alembic upgrade head` inside the container when needed.
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

# Default = the API. The worker service overrides this command in compose.
# --proxy-headers tells uvicorn to trust X-Forwarded-* from the nginx proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
