resource "aws_lambda_function" "download" {
  function_name = "${var.project_name}-download"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.lambda_image_tag}"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_mb

  ephemeral_storage {
    size = 2048
  }

  environment {
    variables = {
      BUCKET_NAME       = aws_s3_bucket.downloads.bucket
      PRESIGNED_EXPIRY  = tostring(var.presigned_url_expiry)
      CORS_ALLOW_ORIGIN = join(",", var.cors_allowed_origins)
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_s3,
  ]

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-download"
  retention_in_days = 14
}
