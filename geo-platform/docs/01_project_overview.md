# Geo Platform — Project Overview

## What is this?

A full-stack geographic data management platform that serves three clients:
- **ArcGIS Pro** — desktop GIS authoring tool
- **Esri Portal** — web GIS viewer
- **Argo** — offline-capable .NET field app (sync via snapshot/delta/push)

## Repository

- **Repo:** https://github.com/ittai-rovnick/sk.git
- **Branch:** `develop`
- **Project root:** `geo-platform/`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Clients                             │
│   ArcGIS Pro    │   Esri Portal   │   Argo (.NET)       │
└────────┬────────┴────────┬────────┴────────┬────────────┘
         │                 │                 │
         └─────────────────▼─────────────────┘
                    FastAPI REST API
                    localhost:8000
                         │
          ┌──────────────┼──────────────────┐
          │              │                  │
     pgbouncer       geo_features        MinIO
     :6432 → :5432    :5433             :9000
          │
     geo_meta
     :5432
          │
       Redis
       :6379
```

## Stack

| Layer       | Technology                                              |
|-------------|---------------------------------------------------------|
| API         | FastAPI + SQLAlchemy 2.0 async + psycopg3 + GeoAlchemy2 |
| Auth        | Microsoft Entra ID (JWT), groups cached in Redis        |
| Meta DB     | PostgreSQL 16 + PostGIS 3.4 (`geo_meta`, port 5432)     |
| Features DB | PostgreSQL 16 + PostGIS 3.4 (`geo_features`, port 5433) |
| Pooler      | pgbouncer port 6432 (in front of geo_meta only)         |
| Cache       | Redis 7 port 6379                                       |
| Storage     | MinIO (S3-compatible) port 9000, console port 9001      |
| Web         | React 18 + TypeScript + Vite + Ant Design + MSAL        |

## Key architectural rules

1. **Routers: HTTP only. Services: business logic. Models: DB schema. Never mix.**
2. All DB operations must be async/await. No sync blocking code.
3. Every write endpoint: check permission FIRST → check layer lock SECOND → do work THIRD → audit log FOURTH.
4. Soft deletes everywhere — `deleted_at = now()`. Never hard DELETE features/layers/group_layers.
5. Optimistic locking on features: `WHERE version = client_version`. 0 rows updated = HTTP 409 → record in sync_conflicts.
6. Geometry always stored as EPSG:4326. ST_IsValid check + ST_MakeValid auto-repair on every insert.
7. Features table is `PARTITION BY HASH(layer_id)` with 32 partitions. Always include `layer_id` in queries.
8. Store S3 keys in the database. Generate pre-signed URLs on demand. Never store full URLs.
