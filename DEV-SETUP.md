# Designia Dev Containers

Simple 3-container setup: MySQL, Redis, MinIO

## Start

```bash
chmod +x dev-start.sh
./dev-start.sh
```

Or manually:
```bash
docker-compose -f docker-compose.dev.yml up -d
```

## Ports

- **MySQL**: `localhost:3308` (root / 8NbDfnqvAbGgu2xd5pOO871udctt2r)
- **Redis**: `localhost:6379`
- **MinIO**: `http://localhost:9100` (Console: `http://localhost:9101`)

## Stop

```bash
docker-compose -f docker-compose.dev.yml down
```

## The other 4 containers

Your observability stack (Kong, Postgres, Prometheus, Jaeger, Grafana) runs separately via:
```bash
cd infrastructure/kong
docker-compose -f docker-compose.observability-only.yml up -d
```

Total = 7 containers when both stacks are running.
