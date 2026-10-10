# QTick reproducible environment (Python 3.12 slim; CPU-only, no GPU needed)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

WORKDIR /qtick
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY webapp/ ./webapp/
COPY tests/ ./tests/
COPY traces/ ./traces/
COPY results/ ./results/

EXPOSE 5000
CMD ["python", "scripts/reproduce.py"]
