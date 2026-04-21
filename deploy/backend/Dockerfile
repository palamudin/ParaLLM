FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-ci.txt /tmp/requirements-ci.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements-ci.txt

COPY . /app

CMD ["python", "-m", "backend.app", "--host", "0.0.0.0", "--port", "8787"]
