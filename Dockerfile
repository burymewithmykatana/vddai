ARG PYTHON_IMAGE=python:3.14.3@sha256:9234c2fd80143741d28153f66dc306f0448c477a7d965df83107373411509357

FROM ${PYTHON_IMAGE} AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

COPY requirements.txt .

RUN python -m venv "${VIRTUAL_ENV}" \
    && pip install --no-cache-dir --upgrade pip==26.2 \
    && pip install --no-cache-dir \
        --index-url "${PYTORCH_INDEX_URL}" \
        torch==2.13.0 torchvision==0.28.0 \
    && pip install --no-cache-dir -r requirements.txt

FROM ${PYTHON_IMAGE} AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

ARG SOURCE_REPOSITORY
ARG SOURCE_REVISION
ARG IMAGE_VERSION

LABEL org.opencontainers.image.source="${SOURCE_REPOSITORY}" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="${IMAGE_VERSION}"

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY ml ./ml
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
