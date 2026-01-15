 FROM python:3.11-slim
 
 WORKDIR /app
 
 ENV PYTHONDONTWRITEBYTECODE=1 \
     PYTHONUNBUFFERED=1
 
 COPY pyproject.toml README.md /app/
 COPY src /app/src
 
RUN mkdir -p /app/data \
 && pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -e .
 
 EXPOSE 8000
 
 CMD ["automatos-unified-adapter"]
