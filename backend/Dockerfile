FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY research/ /app/research/
WORKDIR /app/backend
ENV PYTHONPATH=/app/backend
EXPOSE 8099
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8099"]
