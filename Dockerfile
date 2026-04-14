FROM python:3.12-slim

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY schema.sql /app/
COPY poller/ /app/poller/

WORKDIR /app
EXPOSE 8000
CMD ["python", "-m", "poller.main"]
