FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Flaskアプリのファイル名が app.py であれば "app:app"
# もし main.py なら "main:app" に書き換えてください
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
