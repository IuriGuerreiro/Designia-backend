# Designia Development Environment Startup Script (PowerShell)

Write-Host "🚀 Starting MySQL, Redis, and MinIO..." -ForegroundColor Cyan

docker-compose -f docker-compose.dev.yml up -d

Write-Host ""
Write-Host "⏳ Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Import MySQL data if backup exists
if (Test-Path "designia_backup.sql") {
    Write-Host "📦 Restoring MySQL database from backup..." -ForegroundColor Green
    Get-Content designia_backup.sql | docker exec -i Designia-dev-MySQL mysql -uroot -p8NbDfnqvAbGgu2xd5pOO871udctt2r designia
    Write-Host "✅ MySQL database restored!" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No MySQL backup found (designia_backup.sql)" -ForegroundColor Yellow
}

# Setup MinIO bucket and restore data
Write-Host "🪣 Setting up MinIO..." -ForegroundColor Cyan
docker exec Designia-dev-MinIO mc alias set myminio http://localhost:9000 myuser mystrongpassword123 2>$null
docker exec Designia-dev-MinIO mc mb myminio/designia 2>$null

# Restore MinIO data if backup exists
if (Test-Path "minio-backup") {
    Write-Host "📦 Restoring MinIO data from backup..." -ForegroundColor Green
    docker cp minio-backup Designia-dev-MinIO:/tmp/designia-backup
    docker exec Designia-dev-MinIO mc mirror /tmp/designia-backup /data/designia
    Write-Host "✅ MinIO data restored!" -ForegroundColor Green
} else {
    Write-Host "ℹ️  No MinIO backup found (minio-backup folder)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ All done! Your dev environment is ready." -ForegroundColor Green
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "MySQL:  localhost:3308 (with your data)" -ForegroundColor White
Write-Host "Redis:  localhost:6379" -ForegroundColor White
Write-Host "MinIO:  http://localhost:9100 (Console: http://localhost:9101)" -ForegroundColor White
Write-Host "        Bucket 'designia' with all your files restored" -ForegroundColor Gray
Write-Host ""
