import os
import shutil
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from services.stt_service import STTService
from services.llm_service import LLMService

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# FastAPI アプリの初期化
app = FastAPI(
    title="English Speaking Coach API",
    description="Whisper(STT) と Ollama(LLM) を統合した発音・スピーキング解析バックエンド",
    version="1.0.0"
)

# CORS ミドルウェア設定 (フロントエンドからのアクセス許可)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発環境用にすべて許可 (本番環境ではドメインを指定)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# サービスのインスタンス化
stt_service = STTService()
llm_service = LLMService()


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {"message": "English Speaking Coach API is running!"}


@app.get("/health")
async def health_check():
    """フロントエンドからの接続確認用ヘルスチェック"""
    return {
        "status": "ok",
        "device": stt_service.device,
        "model": llm_service.model_name
    }


@app.post("/upload-audio")
async def upload_audio(audio: UploadFile = File(...)):
    """
    音声ファイルを受け取り、以下を処理して返します:
    1. 一時ファイルとしてローカルに保存
    2. STT (faster-whisper) による文字起こし & 単語レベルタイムスタンプ抽出
    3. LLM (Ollama) による日本語発音アドバイスの生成
    4. 一時ファイルの削除
    """
    if not audio.filename:
        raise HTTPException(status_code=400, detail="ファイル名が無効です。")

    # 一時ファイルの生成 (拡張子を維持)
    ext = os.path.splitext(audio.filename)[1] or ".webm"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    temp_path = temp_file.name

    try:
        # アップロードされた音声データを一時ファイルに保存
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        file_size = os.path.getsize(temp_path)
        logger.info(f"音声受信完了: {audio.filename} ({file_size} bytes) -> {temp_path}")

        # 1. STT解析 (Whisper)
        stt_result = stt_service.transcribe(temp_path)
        logger.info(f"STT完了: {stt_result['transcript']}")

        # 2. LLMフィードバック生成 (Ollama)
        feedback_text = await llm_service.generate_feedback(
            transcript=stt_result["transcript"],
            words=stt_result["words"]
        )
        logger.info("LLMフィードバック生成完了")

        # 3. レスポンス返却
        return {
            "status": "success",
            "filename": audio.filename,
            "size_bytes": file_size,
            "transcript": stt_result["transcript"],
            "words": stt_result["words"],
            "feedback": feedback_text
        }

    except Exception as e:
        logger.error(f"音声処理中にエラーが発生しました: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"音声解析処理に失敗しました: {str(e)}")

    finally:
        # 一時ファイルの削除 (クリーンアップ)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info(f"一時ファイルを削除しました: {temp_path}")
            except Exception as e:
                logger.warning(f"一時ファイルの削除に失敗しました: {temp_path} ({e})")