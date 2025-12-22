#!/bin/bash
# Start Designia Core Dev Containers

echo "🚀 Starting MySQL, Redis, and MinIO..."

docker-compose -f docker-compose.dev.yml up -d

echo ""
echo "⏳ Waiting for MySQL to be ready..."
sleep 10

# Import existing data if backup exists
if [ -f "designia_backup.sql" ]; then
    echo "📦 Restoring database from backup..."
    docker exec -i Designia-dev-MySQL mysql -uroot -p8NbDfnqvAbGgu2xd5pOO871udctt2r designia < designia_backup.sql
    echo "✅ Database restored!"
else
    echo "ℹ️  No backup found (designia_backup.sql)"
fi

# Create MinIO bucket
echo "🪣 Setting up MinIO bucket..."
docker exec Designia-dev-MinIO mc alias set myminio http://localhost:9000 myuser mystrongpassword123 2>/dev/null
docker exec Designia-dev-MinIO mc mb myminio/designia 2>/dev/null || echo "✓ Bucket exists"

echo ""
echo "✅ Done!"
echo ""
echo "MySQL:  localhost:3308 (with your data restored)"
echo "Redis:  localhost:6379"
echo "MinIO:  http://localhost:9100 (Console: http://localhost:9101)"
echo ""
