FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root inside the container.
#
# uid 1000 deliberately, matching the host account that owns /srv/lab: the
# pictures directory is bind-mounted read-write so the calendar can accept an
# uploaded background, and rsync from the workspace writes those same files as
# uid 1000. Any other uid means one of the two cannot write. This is not the
# dashboard, which runs as 65534 precisely so it CANNOT read uid 1000's files
# (see homelab ADR notes); here the container is trusted with the database
# password already, and the only thing mounted is a folder of wallpapers.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
