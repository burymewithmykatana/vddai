FROM python:3.14.3

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip==26.1.2 \
    && pip install --no-cache-dir \
        --index-url ${PYTORCH_INDEX_URL} \
        torch==2.13.0 torchvision==0.28.0 \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
