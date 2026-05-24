FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
EXPOSE 8200
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8200"]
