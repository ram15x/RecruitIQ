FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY recruitiq ./recruitiq
COPY data ./data
COPY assets ./assets
COPY portal ./portal
RUN useradd -m app && mkdir /data && chown app /data
USER app
ENV RECRUITIQ_DB_URL=sqlite:////data/recruitiq.db
EXPOSE 8000 8501
