# Plan 3 will switch this FROM line to cosinabox/runtime:0.1.x.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e .

COPY . /app

CMD ["python", "main.py"]
