import httpx
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, model_name: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/chat"

    def _build_prompt(self, transcript: str, words: List[Dict[str, Any]]) -> str:
        words_summary = ", ".join([f"{w.get('text')}({int(w.get('avg_logprob', 0)*100)}%)" for w in words[:10]])
        return f"""
ユーザーの発話テキスト: "{transcript}"
単語ごとの発音確信度スコア: [{words_summary}]

上記の英語発音データを分析し、学習者に向けたアドバイスを以下の構成で短く作成してください：
1. 発音の良かった点・評価
2. 特に注意すべき単語やアクセントのアドバイス
3. 次回へのひとこと応援メッセージ
"""

    async def generate_feedback(self, transcript: str, words: List[Dict[str, Any]]) -> str:
        """
        Ollama APIへ非同期リクエストを送信し、レスポンスを取得します。
        """
        if not transcript.strip():
            return "音声が検出されませんでした。もう少しマイクに近づいて発話してみてください。"

        prompt = self._build_prompt(transcript, words)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "あなたは優秀で優しい英語発音指導コーチです。日本語で親しみやすく具体的にアドバイスしてください。"},
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }

        try:
            # 7bモデルの初回推論に備えてタイムアウトを 120 秒に設定
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "アドバイスの生成に失敗しました。")

        except httpx.ConnectError:
            logger.error("Failed to connect to Ollama server.")
            return "Ollama サーバーへの接続に失敗しました。WSL2側で `ollama serve` が実行されているか確認してください。"
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama API error: {e.response.status_code} - {e.response.text}")
            return f"Ollama API エラーが発生しました ({e.response.status_code})。"
        except Exception as e:
            logger.error(f"Unexpected error in LLMService: {str(e)}")
            return f"エラーが発生しました: {str(e)}"