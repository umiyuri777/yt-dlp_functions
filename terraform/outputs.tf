output "api_url" {
  description = "POST /download の完全 URL（フロント config.js に設定）"
  value       = "${aws_apigatewayv2_api.http.api_endpoint}/download"
}

output "api_base_url" {
  description = "API Gateway のベース URL"
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "bucket_name" {
  description = "ダウンロード保存用 S3 バケット名"
  value       = aws_s3_bucket.downloads.bucket
}

output "ecr_repository_url" {
  description = "Lambda イメージ用 ECR リポジトリ URL"
  value       = aws_ecr_repository.lambda.repository_url
}

output "lambda_function_name" {
  description = "Lambda 関数名"
  value       = aws_lambda_function.download.function_name
}

output "presigned_url_expiry" {
  description = "Presigned URL 有効期限（秒）"
  value       = var.presigned_url_expiry
}
