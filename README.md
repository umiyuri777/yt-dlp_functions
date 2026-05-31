# yt-dlp Music Download (Monorepo)

YouTube 等の URL から音声・動画を取得し、S3 に保存したうえで Presigned URL を返す AWS Lambda（コンテナ）と、それを呼び出す静的 Web フロントのモノレポです。

## アーキテクチャ

```
[Browser / front] --POST /download--> [API Gateway HTTP API]
                                           |
                                           v
                                    [Lambda (container)]
                                    yt-dlp + ffmpeg
                                           |
                                           v
                                    [S3 bucket]
                                    (2日で自動削除)
                                           |
                                           v
                              Presigned URL を JSON で返却
```

| ディレクトリ | 内容 |
|-------------|------|
| `lambda/` | コンテナイメージ（Python 3.12 + yt-dlp + ffmpeg） |
| `front/` | 静的 HTML/JS（API を呼び出してダウンロードリンク表示） |
| `terraform/` | S3 / ECR / Lambda / API Gateway / IAM |
| `.github/workflows/` | CI（検証・ビルド）と Deploy（ECR push + Terraform + GitHub Pages） |

## 前提条件

- AWS アカウント
- ローカル: [Terraform](https://www.terraform.io/) 1.5+、[Docker](https://www.docker.com/)、AWS CLI
- GitHub Actions デプロイ時: AWS 認証（**OIDC 推奨** またはアクセスキー）

## デプロイ手順（初回・二段階）

Lambda コンテナイメージは ECR に存在しないと作成できないため、**ECR → イメージ push → 全体 apply** の順序が必要です。`deploy.yml` はこの順序を自動化しています。

### 1. Terraform 変数

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# 必要に応じて編集（terraform.tfvars は gitignore 済み）
```

**AWS プロファイルの指定（ローカル）**

| 方法 | 例 |
|------|-----|
| `terraform.tfvars` | `aws_profile = "my-profile"` |
| 環境変数（tfvars 未設定時） | `export AWS_PROFILE=my-profile` |

`aws_profile` を null のままにすると、Terraform は `AWS_PROFILE` またはデフォルトの認証チェーンを使います。Docker の ECR ログインや `aws` CLI も同じプロファイルに揃えてください。

```bash
export AWS_PROFILE=my-profile
aws ecr get-login-password --region ap-northeast-1 | ...
```

### 2. 手動デプロイ（ローカル）

```bash
cd terraform
terraform init

# ブートストラップ（ECR / S3 / IAM のみ）
terraform apply -target=aws_ecr_repository.lambda \
  -target=aws_s3_bucket.downloads \
  -target=aws_s3_bucket_public_access_block.downloads \
  -target=aws_s3_bucket_server_side_encryption_configuration.downloads \
  -target=aws_s3_bucket_lifecycle_configuration.downloads \
  -target=aws_iam_role.lambda \
  -target=aws_iam_role_policy_attachment.lambda_basic \
  -target=aws_iam_role_policy.lambda_s3

ECR_URL=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region ap-northeast-1 | \
  docker login --username AWS --password-stdin "${ECR_URL%%/*}"

cd ../lambda
docker build -t "${ECR_URL}:latest" .
docker push "${ECR_URL}:latest"

cd ../terraform
terraform apply
```

### 3. フロントのデプロイ（GitHub Pages）

1. リポジトリの **Settings → Pages → Build and deployment** で **Source: GitHub Actions** を選択
2. `main` へ push するか、`Deploy` ワークフローを手動実行
3. Terraform apply 後、`deploy-pages` ジョブが `front/` を GitHub Pages に公開し、`config.js` の `apiUrl` を `terraform output api_url` から自動生成します

公開 URL は Actions の `deploy-pages` ジョブ、または **Settings → Pages** で確認できます（例: `https://<user>.github.io/<repo>/`）。

**ローカル開発:** `front/config.js.example` を `front/config.js` にコピーし、`apiUrl` をデプロイ済み API に合わせてください。

**本番 CORS:** `terraform.tfvars` の `cors_allowed_origins` に GitHub Pages のオリジンを含めてください（例: `https://<user>.github.io`）。開発中は `["*"]` のままでも動作します。

**既に `static_site.tf` で S3 ウェブサイトを作成済みの場合:** `terraform destroy` で `aws_s3_bucket.website` 関連リソースを削除するか、`terraform state rm` で state から外してから apply してください。

### 4. GitHub Actions シークレット

**OIDC（推奨）**

Deploy ワークフロー実行前に、ローカルで Terraform から OIDC 用ロールを作成し、ARN を GitHub に登録します。

1. `terraform.tfvars` に `github_repository = "あなたのユーザー/yt-dlp_functions"` を追加（例は `terraform.tfvars.example` 参照）
2. ローカルで GitHub Actions 用リソースのみ作成:

```bash
cd terraform
terraform init

terraform apply \
  '-target=aws_iam_openid_connect_provider.github_actions[0]' \
  -target=aws_iam_role.github_actions \
  -target=aws_iam_role_policy_attachment.github_actions_poweruser \
  -target=aws_iam_role_policy.github_actions_iam
```

アカウントに既に `token.actions.githubusercontent.com` の OIDC プロバイダがある場合は apply が失敗します。そのときは `terraform.tfvars` に既存 ARN を指定して再実行してください。

```hcl
github_oidc_provider_arn = "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
```

（このとき `-target=aws_iam_openid_connect_provider.github_actions` は不要です。）

3. ARN を取得して GitHub シークレットに登録:

```bash
terraform output -raw github_actions_role_arn
# リポジトリ Settings → Secrets and variables → Actions
#   AWS_ROLE_ARN = 上記の出力
#   AWS_REGION   = ap-northeast-1 など
```

| Secret / Variable | 説明 |
|-------------------|------|
| `AWS_ROLE_ARN` | `terraform output -raw github_actions_role_arn` の値 |
| `AWS_REGION` | 例: `ap-northeast-1`（`terraform.tfvars` の `aws_region` と揃える） |

ロールには Deploy 用に PowerUserAccess と Terraform 向け IAM 操作権限が付与されています（個人・学習用途向け。本番では必要最小限に絞ってください）。

**アクセスキー（代替）**

| Secret | 説明 |
|--------|------|
| `AWS_ACCESS_KEY_ID` | IAM ユーザー |
| `AWS_SECRET_ACCESS_KEY` | シークレット |
| `AWS_REGION` | リージョン |

`AWS_ROLE_ARN` が空のとき、ワークフローはアクセスキー方式にフォールバックします。

## ローカル開発

### Lambda イメージのビルド確認

```bash
docker build -t yt-dlp-lambda:local ./lambda
```

### フロントの起動

```bash
cd front
python3 -m http.server 8080
# http://localhost:8080 を開き、config.js の apiUrl をデプロイ済み API に設定
```

### API の手動呼び出し

```bash
curl -X POST "$(terraform -chdir=terraform output -raw api_url)" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=XXXXXXXX",
    "extension": "m4a",
    "filename": "my-song",
    "quality": "720"
  }'
```

## API 仕様

- **POST** `/download`
- **Body:**
  - `url`（必須）: ダウンロード対象 URL
  - `extension`（任意、デフォルト `m4a`）: `mp3` / `m4a` / `mp4` / `webm` など
  - `filename`（任意）: S3 キー用ベース名（拡張子なし、英数字・`-`・`_` のみ）
  - `quality`（任意、動画時）: `360` / `480` / `720` / `1080` / `best`（デフォルト `720`）
- **成功 (200):** `{ "presigned_url": "...", "key": "downloads/...", "expires_in": 3600, "filename": "my-song.m4a" }`
- **エラー:** `400`（不正 JSON / パラメータ不正）、`422`（yt-dlp 失敗）、`500`（その他）

CORS は API Gateway の `cors_allowed_origins`（デフォルト `*`）で設定します。本番ではフロントのオリジンを明示してください。

## S3 ライフサイクル

`downloads/` プレフィックスのオブジェクトは **1 日後** に自動削除されます（`s3_lifecycle_days` で変更可）。

## 法的注意・免責

本ツールは技術デモ・個人利用の学習目的で提供されています。**著作権で保護されたコンテンツを、権利者の許可なくダウンロード・再配布することは、多くの法域で違法となる可能性があります。** 利用者は適用される法律・各サービスの利用規約を自己責任で確認し、遵守してください。作者・提供者は利用による損害や法的問題について一切の責任を負いません。

## ライセンス

プロジェクトの LICENSE が未設定の場合は、利用前にリポジトリ管理者に確認してください。
