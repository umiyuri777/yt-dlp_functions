variable "project_name" {
  description = "リソース名のプレフィックス"
  type        = string
  default     = "yt-dlp-music"
}

variable "aws_region" {
  description = "AWS リージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "aws_profile" {
  description = "AWS CLI のプロファイル名（null のときは環境変数 AWS_PROFILE またはデフォルト認証チェーン）"
  type        = string
  default     = null
  nullable    = true
}

variable "presigned_url_expiry" {
  description = "Presigned URL の有効期限（秒）"
  type        = number
  default     = 3600
}

variable "lambda_image_tag" {
  description = "ECR に push する Lambda コンテナイメージのタグ"
  type        = string
  default     = "latest"
}

variable "cors_allowed_origins" {
  description = "API Gateway CORS で許可するオリジン（開発時は * も可）"
  type        = list(string)
  default     = ["*"]
}

variable "lambda_timeout" {
  description = "Lambda タイムアウト（秒）"
  type        = number
  default     = 300
}

variable "lambda_memory_mb" {
  description = "Lambda メモリ（MB）"
  type        = number
  default     = 2048
}

variable "s3_lifecycle_days" {
  description = "S3 オブジェクトを削除するまでの日数"
  type        = number
  default     = 1
}

variable "github_repository" {
  description = "GitHub リポジトリ (owner/repo)。OIDC の sub 制限に使用"
  type        = string
}

variable "github_oidc_provider_arn" {
  description = "既存アカウントの GitHub OIDC プロバイダ ARN。null のとき新規作成（既存があると apply が失敗する場合は ARN を指定）"
  type        = string
  default     = null
  nullable    = true
}
