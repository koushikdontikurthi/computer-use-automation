FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY . .
CMD ["python", "-m", "app.legacy_app.app"]
