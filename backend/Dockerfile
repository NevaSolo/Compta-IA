# Image backend Compta-IA — FastAPI + pipeline OCR/NLP/ML
FROM python:3.10-slim

# Dépendances système :
# - libgl1/libglib2.0-0 : runtime OpenCV headless
# - tesseract-ocr(+fra) : moteur OCR de repli
# - default-mysql-client : utile pour diagnostiquer la connexion DB en exploitation
# - curl : healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    tesseract-ocr tesseract-ocr-fra \
    default-mysql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Couche dépendances Python isolée du code applicatif : évite de tout
# réinstaller (dont EasyOCR/PyTorch, les plus lourdes) à chaque modification
# du code source.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download fr_core_news_md

COPY . .

RUN mkdir -p storage/uploads storage/models

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -f http://localhost:9000/docs || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
