# ADR-019 Fly.io Docker Deployment
**Date:** 2026-04-27
**Status:** Accepted

## Context
The Kairos Python Engine needs to be deployed to a headless VPS environment. Fly.io was chosen as the hosting provider. Initially, the automated `fly launch` command failed because Fly.io could not automatically detect the project's framework or runtime from the `pyproject.toml` file alone.

## Decision
We elected to explicitly define the application environment using a standard Dockerfile rather than relying on Fly.io's auto-detection mechanisms. 

- Created a `Dockerfile` using `python:3.11-slim` as the base image.
- Installed the project and its dependencies via `pip install --no-cache-dir .` to utilize the existing `pyproject.toml` (hatchling build system).
- Set the entry point to `CMD ["python", "-m", "kairos.scheduler"]`, which mirrors the exact execution command used in the existing local Systemd service file (`kairos.service`).
- Added a `.dockerignore` file to prevent local artifacts (`.venv`, `__pycache__`, `.env`) from bloating the image or leaking secrets.

## Rationale
Using a Dockerfile is the most resilient, reproducible, and standard way to deploy Python applications to cloud platforms like Fly.io. It ensures we have full control over the runtime environment, dependencies, and execution entry points without depending on black-box buildpacks.

## Alternatives Considered
- Relying on a `fly.toml` with buildpack specifications. Rejected because a Dockerfile is more portable (can be tested locally or moved to AWS/GCP easily).

## Consequences
- Deployment requires Docker virtualization (handled transparently by Fly.io).
- Secrets must be managed via `flyctl secrets` rather than a local `.env` file during deployment.
