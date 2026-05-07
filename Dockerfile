FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget gnupg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer uniquement Chromium (ton script n'utilise que Chromium)
RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "ton_script.py"]
