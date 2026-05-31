resource "aws_s3_bucket" "downloads" {
  bucket = "${var.project_name}-downloads-${data.aws_caller_identity.current.account_id}"

  tags = {
    Project = var.project_name
  }
}

resource "aws_s3_bucket_public_access_block" "downloads" {
  bucket = aws_s3_bucket.downloads.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "downloads" {
  bucket = aws_s3_bucket.downloads.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "downloads" {
  bucket = aws_s3_bucket.downloads.id

  rule {
    id     = "expire-downloads"
    status = "Enabled"

    filter {
      prefix = "downloads/"
    }

    expiration {
      days = var.s3_lifecycle_days
    }
  }
}

data "aws_caller_identity" "current" {}
