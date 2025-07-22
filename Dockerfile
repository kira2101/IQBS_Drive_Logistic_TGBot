# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код приложения
COPY . .

# Создаем директории для данных
RUN mkdir -p /app/photos /app/reports /app/user_logs

# Создаем пользователя для запуска приложения (безопасность)
RUN adduser --disabled-password --gecos '' --uid 1000 botuser
RUN chown -R botuser:botuser /app
USER botuser

# Порт для healthcheck (если понадобится)
EXPOSE 8000

# Команда для запуска приложения
CMD ["python", "bot.py"]