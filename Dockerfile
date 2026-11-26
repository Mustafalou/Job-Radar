FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.cache/huggingface \
    JOBRADAR_DB=/data/jobs.db \
    PROFILE_PATH=/data/profile.md \
    CV_BASE_PATH=/data/cv_base.json
WORKDIR /app

# 1. Dépendances (PyTorch version CPU : environ 4 fois plus léger que la version GPU)
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# 2. Modèle d'embeddings téléchargé une seule fois, à la construction
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# 3. Le code en dernier : si tu changes juste le code, Docker réutilise les étapes 1 et 2
COPY src/ src/

EXPOSE 8000
CMD ["uvicorn", "jobradar.api:app", "--host", "0.0.0.0", "--port", "8000"]