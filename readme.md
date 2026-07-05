# Visual Defect AI Backend

Production-style AI backend for visual defect detection.

This project is designed as a production-oriented backend system for AI image inference.  
The goal is not only to train a model, but to build a deployable, testable, observable backend around AI inference.

## Current Status

Day 1 skeleton:

- FastAPI application
- Dockerized API service
- PostgreSQL service
- Redis service
- Environment-based configuration
- Health check endpoint
- Swagger/OpenAPI docs

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- Redis
- Docker
- Docker Compose

## Run Locally

```bash
cp .env.example .env
docker compose up --build