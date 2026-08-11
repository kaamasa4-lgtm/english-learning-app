# Backend — AI英語発音コーチ（FastAPI + ローカルAI）

WSL2 / Ubuntu 上で動作するバックエンドです。音声の受信・変換、STT（faster-whisper）、LLM（Ollama）、TTS（MeloTTS）を統合し、フロントエンドへ JSON レスポンスを返します。

プロジェクト全体の概要は [ルート README](../README.md) を参照してください。

## 役割

| 責務 | 説明 |
|------|------|
| CORS 設定 | Windows ブラウザからのクロスオリジンリクエストを許可 |
| 音声の標準化 | FFmpeg で `16kHz / 16bit / モノラル` WAV に変換 |
| STT（耳） | faster-whisper で文字起こし＋単語タイムスタンプ抽出 |
| LLM（脳） | Ollama にメタデータ付きプロンプトを送り、日本語アドバイスを生成 |
| TTS（口） | MeloTTS でお手本・返答音声を合成（Phase 4） |
| レスポンス | スコア・フィードバック・グラフ用データを JSON で返却 |

## ディレクトリ構造

```text
backend/
├── README.md              # 本ドキュメント
├── main.py                # FastAPI エントリーポイント（CORS・ルーティング）
├── requirements.txt       # Python 依存ライブラリ
├── scripts/
│   └── verify.sh          # 全コンポーネントの動作確認スクリプト
│
├── services/
│   ├── stt_service.py     # faster-whisper による文字起こし
│   ├── llm_service.py     # Ollama API 連携
│   └── tts_service.py     # MeloTTS による音声合成
│
└── storage/               # .gitignore で除外（Git 管理しない）
    ├── raw_audio/         # フロントから届いた一時音声（webm 等）
    └── processed_wav/     # Whisper 用 WAV、TTS 生成音声
```

## 技術スタック

| カテゴリ | ライブラリ / ツール |
|----------|---------------------|
| ランタイム | Python 3.10+ |
| GPU | CUDA Toolkit 12.x、NVIDIA GPU（VRAM 12GB 以上推奨） |
| Web サーバー | FastAPI + uvicorn |
| STT | faster-whisper（large-v3） |
| LLM | Ollama（`qwen2.5-coder:7b` / `llama3:8b` 4-bit 推奨） |
| TTS | MeloTTS（将来 StyleTTS2 も検討） |
| 音声処理 | FFmpeg、pydub、ffmpeg-python |
| 数値計算 | fastdtw、scipy（DTW アライメント、Phase 4） |

## 前提条件

### システムパッケージ（WSL2 / Ubuntu）

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-full python3-pip ffmpeg git \
  mecab libmecab-dev mecab-ipadic-utf8
```

> **Ubuntu 24.04+ (PEP 668):** システム Python へ直接 `pip install` すると `externally-managed-environment` エラーになります。必ず `.venv` を作成してからインストールしてください。

### NVIDIA GPU（推奨）

```bash
# CUDA が利用可能か確認
nvidia-smi
```

### Ollama（Phase 3 以降）

```bash
# インストール後、推奨モデルを取得
ollama pull qwen2.5-coder:7b
# または
ollama pull llama3:8b
```

## セットアップ

```bash
cd backend
source .venv/bin/activate   # プロンプトに (.venv) が付くことを確認

# 依存ライブラリのインストール（MeloTTS 含む）
pip install -r requirements.txt
python -m unidic download   # 日本語 TTS に必要

# ストレージディレクトリの作成
mkdir -p storage/raw_audio storage/processed_wav
```

`.venv` がまだない場合のみ: `python3 -m venv .venv` を先に実行してください。

## 動作確認

```bash
cd backend
bash scripts/verify.sh
```

環境・インポート・Ollama 接続・API エンドポイント・TTS を一括チェックします。結果は `../VERIFICATION_RESULTS.txt` に保存されます。

## 起動方法

```bash
cd backend
source .venv/bin/activate

# 開発用（ホットリロード有効）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

起動後、次で疎通を確認します。

```bash
curl http://localhost:8000/health
```

Windows ブラウザからは `http://localhost:8000` でアクセスできます（WSL2 のポートフォワーディングにより自動で届きます）。

## API 設計

### `GET /health`

疎通確認用。Phase 1 で最初に実装します。

**レスポンス例:**

```json
{
  "status": "ok",
  "device": "cuda",
  "model": "qwen2.5:3b",
  "tts": "melotts"
}
```

### `POST /upload-audio`

フロントエンドから録音データを受け取り、解析パイプラインを実行します。

**リクエスト:**

- `Content-Type`: `multipart/form-data`
- フィールド: `audio`（ファイル、`audio/webm` または `audio/wav`）

**レスポンス例（Phase 1 — エコー確認）:**

```json
{
  "message": "音声を受信しました",
  "filename": "recording.webm",
  "size_bytes": 48231
}
```

**レスポンス例（完全解析）:**

```json
{
  "status": "success",
  "filename": "recording.webm",
  "size_bytes": 48231,
  "transcript": "Hello, how are you today?",
  "words": [
    {
      "text": "Hello",
      "start": 0.12,
      "end": 0.45,
      "avg_logprob": 0.92
    }
  ],
  "feedback": "全体的にクリアな発音です。",
  "converted_wav": "tmpXXXX_converted.wav",
  "audio_url": "/storage/processed_wav/feedback_abc123.wav"
}
```

`audio_url` は常に返されます。静的配信は `/storage/processed_wav/` で行われます。

## 処理パイプライン

```text
[POST /upload-audio]
     ↓
  raw_audio/ に保存
     ↓
  FFmpeg → 16kHz / 16bit / モノラル WAV
     ↓
  faster-whisper → テキスト + タイムスタンプ + avg_logprob
     ↓
  メタデータ算出（言い淀み時間、低信頼度単語など）
     ↓
  Ollama → 日本語フィードバック生成
     ↓
  MeloTTS → 返答音声生成（Phase 4）
     ↓
  JSON レスポンスを返却
```

## CORS 設定

Windows ブラウザ（例: `http://localhost:5500`）からのリクエストを受け付けるため、`main.py` で次を設定します。

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発中はワイルドカード、本番では限定すること
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 開発フェーズ別の実装目標

### Phase 1: 疎通確認

- [x] FastAPI アプリの起動（`main.py`）
- [x] `GET /health` エンドポイント
- [x] `POST /upload-audio` でファイル受信・サイズ返却
- [x] CORS ミドルウェアの設定

### Phase 2: STT（耳）

- [x] FFmpeg による WAV 変換（`16kHz / モノラル`）
- [x] `stt_service.py` — faster-whisper 連携
- [x] 単語ごとの `start` / `end` / `avg_logprob` を JSON 化

### Phase 3: LLM（脳）

- [x] `llm_service.py` — Ollama API 連携
- [x] 文字起こし＋メタデータをプロンプトに注入
- [x] 日本語アドバイスレポートの生成

### Phase 4: TTS（口）と高度な解析

- [x] `tts_service.py` — MeloTTS 連携
- [x] 返答音声 URL の返却と静的配信
- [ ] fastdtw による発話ペース比較
- [ ] グラフ用データの生成

## `requirements.txt`

```text
fastapi
uvicorn[standard]
python-multipart
pydub
ffmpeg-python
faster-whisper
httpx
git+https://github.com/myshell-ai/MeloTTS.git
```

## ストレージと Git 管理

`storage/` 配下の音声ファイルは `.gitignore` で除外します。巨大なモデルファイルやユーザーの録音データが Git 履歴に入るとリポジトリが肥大化するため、必ず除外設定を行ってください。

```text
backend/storage/
*.webm
*.wav
*.mp3
.venv/
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| `externally-managed-environment` | `source .venv/bin/activate` 後に pip を実行 |
| `localhost:8000` に届かない | WSL2 でサーバーが起動しているか確認。`--host 0.0.0.0` を指定 |
| CORS エラー | `CORSMiddleware` の `allow_origins` を確認 |
| FFmpeg が見つからない | `sudo apt install ffmpeg` を実行し、`which ffmpeg` でパスを確認 |
| Whisper が遅い / OOM | モデルサイズを下げる（`medium` → `small`）、または `compute_type="int8"` を検討 |
| Ollama に接続できない | `ollama serve` が起動しているか確認。デフォルトは `http://localhost:11434` |
| MeloTTS インストール失敗 | `sudo apt install mecab libmecab-dev mecab-ipadic-utf8 git` 後に `pip install -r requirements.txt` |
| TTS / MeCab エラー | `python -m unidic download` を実行 |
| GPU が使われない | `nvidia-smi` で認識を確認。CUDA 版 PyTorch / CTranslate2 のインストールを見直す |

## 関連ドキュメント

- [プロジェクト全体 README](../README.md)
- [フロントエンド README](../frontend/README.md)
