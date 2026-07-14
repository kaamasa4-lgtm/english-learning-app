import os
import shutil
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ロギング設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI English Pronunciation Coach - Backend")

# CORSの設定
# 開発環境であるため一時的にすべてのオリジンからのアクセスを許可します
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ディレクトリの自動作成
UPLOAD_DIR = "storage/raw_audio"
PROCESSED_DIR = "storage/processed_wav"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

@app.get("/health")
def health_check():
    """
    疎通確認用エンドポイント
    """
    logger.info("Health check endpoint called")
    return {"status": "ok"}

@app.post("/upload-audio")
async def upload_audio(audio: UploadFile = File(...)):
    """
    フロントエンドから音声データを受け取るエンドポイント
    """
    logger.info(f"Received upload request. Filename: {audio.filename}, Content-Type: {audio.content_type}")
    
    if not audio.filename:
        raise HTTPException(status_code=400, detail="Filename is missing.")

    # 保存先パスの決定
    # セキュアなファイル名にするため、または衝突を防ぐために簡易的なサニタイズや命名を行います
    file_ext = os.path.splitext(audio.filename)[1] or ".webm"
    dest_filename = f"received_{audio.filename}" if audio.filename else "received_audio.webm"
    dest_path = os.path.join(UPLOAD_DIR, dest_filename)

    try:
        # 音声ファイルをローカルストレージに書き込み
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
            
        file_size = os.path.getsize(dest_path)
        logger.info(f"File saved successfully to {dest_path}. Size: {file_size} bytes")
        
        return {
            "message": "音声を受信しました",
            "filename": dest_filename,
            "size_bytes": file_size
        }
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
