import httpx
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, model_name: str = "qwen2.5:3b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/chat"

    def _build_prompt(self, transcript: str, words: List[Dict[str, Any]]) -> str:
        truncated_transcript = transcript[:500] + ("..." if len(transcript) > 500 else "")
        
        # 1. スコア（確信度）が低めの単語（80%未満）だけを抽出して昇順ソート
        low_score_words = [w for w in words if w.get('avg_logprob', 1.0) < 0.8]
        low_score_words = sorted(low_score_words, key=lambda w: w.get('avg_logprob', 1.0))[:10]
        
        if low_score_words:
            words_summary = ", ".join([f"'{w.get('text')}'(スコア: {int(w.get('avg_logprob', 0)*100)}点)" for w in low_score_words])
            issue_info = f"システムによる自動解析で、特に発音が不鮮明・改善の余地があると判定された単語:\n[{words_summary}]"
        else:
            issue_info = "システムによる自動解析で、特に発音が不鮮明な単語は見つかりませんでした（全体的に非常にクリアな発音です）。"

        return f"""
ユーザーの発話内容: "{truncated_transcript}"
{issue_info}

上記の発音解析データを踏まえ、英語学習者へ向けたアドバイスを以下の形式で出力してください：

1. 発音の良かった点・評価
2. 注意すべき単語やアクセントのアドバイス（※不鮮明な単語がない場合は全体のワンポイントアドバイス）
3. 次回へのひとこと応援メッセージ

【注意事項】
- 「あなたが付けた確信度」のような表現は避け、コーチとして自然な語り口でアドバイスしてください。
- スコア数値そのものを直接言及する必要はありません。
"""

    async def generate_feedback(self, transcript: str, words: List[Dict[str, Any]]) -> str:
        if not transcript or not transcript.strip():
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
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                message = data.get("message", {})
                content = message.get("content", "")
                
                if content:
                    return content
                else:
                    return f"APIからのレスポンス構造が不正です: {data}"

        except httpx.ConnectError:
            logger.error("Failed to connect to Ollama server.")
            return "Ollama サーバーへの接続に失敗しました。`ollama serve` が実行されているか確認してください。"
        except httpx.TimeoutException:
            logger.error("Ollama API request timed out.")
            return "AIの応答処理がタイムアウトしました。もう一度試してみてください。"
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama API error: {e.response.status_code} - {e.response.text}")
            return f"Ollama API エラーが発生しました ({e.response.status_code}): {e.response.text}"
        except Exception as e:
            logger.error(f"Unexpected error in LLMService: {str(e)}", exc_info=True)
            return f"エラーが発生しました: {type(e).__name__} - {str(e)}"