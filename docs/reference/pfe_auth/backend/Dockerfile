# syntax=docker/dockerfile:1
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
