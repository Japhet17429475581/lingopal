FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и устанавливаем их (слой кэшируется)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Переменные окружения
ENV PYTHONUNBUFFERED=1

# Порт для FastAPI
EXPOSE 3000

# Запуск
CMD ["python", "run.py"]
