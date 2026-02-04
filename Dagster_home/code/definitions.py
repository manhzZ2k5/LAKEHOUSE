import os
import boto3
from dagster import asset, Definitions, EnvVar

# --- 1. Cấu hình kết nối MinIO ---
# Lưu ý: Trong Docker, endpoint là "minio:9000" chứ không phải localhost
MINIO_CONFIG = {
    "endpoint_url": "http://minio:9000",
    "aws_access_key_id": os.getenv("MINIO_ROOT_USER", "minio_admin"),
    "aws_secret_access_key": os.getenv("MINIO_ROOT_PASSWORD", "minio_secret"),
}

@asset
def minio_test_asset():
    """
    Asset này thử kết nối đến MinIO và kiểm tra xem bucket 'bronze-lake' có tồn tại không.
    """
    # Tạo client kết nối (giả lập S3)
    s3_client = boto3.client("s3", **MINIO_CONFIG)
    
    # Lấy danh sách bucket
    response = s3_client.list_buckets()
    buckets = [b['Name'] for b in response['Buckets']]
    
    # Kiểm tra bucket 'bronze-lake'
    target_bucket = "bronze-lake"
    if target_bucket not in buckets:
        # Nếu chưa có thì tạo luôn (Tiện tay!)
        s3_client.create_bucket(Bucket=target_bucket)
        message = f"Đã tạo mới bucket: {target_bucket}"
    else:
        message = f"Bucket '{target_bucket}' đã tồn tại."
        
    # Trả về kết quả để hiển thị trên UI
    return f"Kết nối MinIO thành công! Danh sách buckets: {buckets}. {message}"

# --- 2. Đăng ký với Dagster ---
defs = Definitions(
    assets=[minio_test_asset],
)