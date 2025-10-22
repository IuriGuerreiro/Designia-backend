# MinIO Setup: Bucket Policy and CORS

This config makes the `designia` bucket readable for public assets and enables browser uploads/downloads via CORS.

## Prerequisites
- MinIO running at `http://localhost:9100`
- Credentials: `myuser` / `mystrongpassword123`
- MinIO Client (`mc`) installed

## Quick Setup (recommended)
```bash
mc alias set local http://localhost:9100 myuser mystrongpassword123
mc mb local/designia || true
# Public read for object GETs (images, static assets)
mc anonymous set download local/designia
# Apply CORS (allow frontend dev servers)
cat > cors.json <<'JSON'
[
  {
    "AllowedOrigins": [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://localhost:5174",
      "http://127.0.0.1:5174"
    ],
    "AllowedMethods": ["GET", "POST", "PUT"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag", "x-amz-request-id", "x-amz-id-2"],
    "MaxAgeSeconds": 3000
  }
]
JSON
mc cors set local/designia cors.json
mc cors info local/designia
```

## AWS-Style Bucket Policy (alternative)
You can use an explicit policy instead of `mc anonymous set`:
```bash
cat > policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::designia/*"]
    }
  ]
}
JSON
mc policy set-json local/designia policy.json
mc policy info local/designia
```

## Verify
- Public URL example: `http://localhost:9100/designia/path/to/object.jpg`
- Django env (Designia-backend/.env):
  - `USE_S3=True`
  - `AWS_S3_ENDPOINT_URL=http://localhost:9100`
  - `AWS_ACCESS_KEY_ID=myuser`
  - `AWS_SECRET_ACCESS_KEY=mystrongpassword123`
  - `AWS_STORAGE_BUCKET_NAME=designia`
  - `AWS_S3_ADDRESSING_STYLE=path`
  - `AWS_S3_SIGNATURE_VERSION=s3v4`
  - `AWS_S3_VERIFY=False`

Run: `python manage.py test_s3` then open the printed URL.
