# Hugging Face Space: pulls the code from GitHub and runs the API and the dashboard in one container.
# The dashboard is the public page (port 7860). The API stays inside the container.
# The database is SQLite in /tmp, so the demo data is rebuilt whenever the Space restarts.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
RUN git clone --depth 1 https://github.com/ram15x/RecruitIQ.git .
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONPATH=/home/user/app \
    RECRUITIQ_DB_URL=sqlite:////tmp/recruitiq.db \
    RECRUITIQ_MEDIA_DIR=/tmp/media \
    RECRUITIQ_DEMO=1 \
    RECRUITIQ_BOOTSTRAP_USER=demo \
    RECRUITIQ_BOOTSTRAP_PASSWORD=recruiter-demo-2026 \
    RECRUITIQ_RETENTION_DAYS=7 \
    RECRUITIQ_API_URL=http://127.0.0.1:8000 \
    RECRUITIQ_DEMO_HINT="Demo login: username demo, password recruiter-demo-2026"
EXPOSE 7860
CMD ["sh", "-c", "export RECRUITIQ_JWT_SECRET=$(python -c 'import secrets;print(secrets.token_hex(32))') && uvicorn recruitiq.api.app:app_factory --factory --host 127.0.0.1 --port 8000 & sleep 3 && exec streamlit run recruitiq/ui/app.py --server.port 7860 --server.address 0.0.0.0 --server.headless true"]
