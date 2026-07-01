---
title: SmartAttend Face API
emoji: 📸
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# SmartAttend Face API

Face detection, enrollment, and recognition API for the SmartAttend attendance system.

## Endpoints

- `GET /health` — health check
- `POST /api/detect` — detect faces in an image
- `POST /api/enroll` — generate embeddings from 3 student photos
- `POST /api/scan` — recognize faces across 3 class photos
