FROM python:3.11-slim
WORKDIR /app

COPY dashboard/requirements.txt dashboard/requirements.txt
RUN pip install --no-cache-dir -r dashboard/requirements.txt

# Preserve the repo's dashboard/ + src/ layout so 🚗_Dashboard.py's sys.path
# fix (repo root = parent of dashboard/) resolves identically here and locally.
COPY dashboard/ dashboard/
COPY src/target_store.py src/target_store.py

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "dashboard/🚗_Dashboard.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--browser.gatherUsageStats=false"]
