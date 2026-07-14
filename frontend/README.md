# Frontend — AI英語発音コーチ（ブラウザUI）

Windows 11 上のブラウザで動作するフロントエンドです。マイク録音・課題表示・解析結果の可視化を担当し、WSL2 上の FastAPI バックエンド（`http://localhost:8000`）と通信します。

プロジェクト全体の概要は [ルート README](../README.md) を参照してください。

## 役割

| 責務 | 説明 |
|------|------|
| 課題提示 | 練習用の英文テキストや対話シナリオを表示 |
| マイク録音 | `MediaRecorder API` で音声をキャプチャし `Blob` として保持 |
| データ送信 | 録音データを `FormData` に載せてバックエンドへ POST |
| 結果表示 | スコア、LLM のアドバイス、グラフ用データを UI に反映 |
| 音声再生 | お手本音声・AI 教師の返答音声を再生（Phase 4） |

## ディレクトリ構造（予定）

```text
frontend/
├── README.md          # 本ドキュメント
├── index.html         # メイン UI（録音ボタン・結果表示エリア）
└── js/
    └── app.js         # 録音制御、fetch 通信、グラフ描画ロジック
```

## 技術スタック

- **HTML5 / Vanilla JavaScript**（ビルドツール不要で Phase 1 を最短起動）
- **MediaRecorder API** — ブラウザ標準のマイクキャプチャ
- **Fetch API** — バックエンドへの音声アップロード
- **Plotly.js** または **Chart.js** — DTW ズレの可視化（Phase 4）

将来的に UI を拡張する場合は Next.js への移行を検討できます。

## 前提条件

- Windows 11 + マイク（内蔵または外付け）
- ブラウザ: Chrome / Edge（`MediaRecorder` + `audio/webm` 対応）
- WSL2 上でバックエンドが `localhost:8000` で起動していること

## 起動方法

フロントエンドは静的ファイルのため、専用サーバーは不要です。Phase 1 では次のいずれかで開きます。

### 方法 A: ファイルを直接開く（最も簡単）

```text
frontend/index.html をブラウザにドラッグ＆ドロップ
```

> `file://` プロトコルではマイク権限や CORS の挙動が環境によって異なる場合があります。問題が出たら方法 B を使ってください。

### 方法 B: 簡易 HTTP サーバー（推奨）

Windows の PowerShell または WSL から:

```bash
# frontend/ ディレクトリで実行
python -m http.server 5500
```

ブラウザで `http://localhost:5500` を開きます。

## バックエンドとの通信

### エンドポイント

| メソッド | パス | 用途 | フェーズ |
|----------|------|------|----------|
| `POST` | `/upload-audio` | 録音データの送信 | Phase 1〜 |
| `GET` | `/health` | 疎通確認 | Phase 1 |

### リクエスト例（Phase 1: 疎通確認）

```javascript
const formData = new FormData();
formData.append('audio', audioBlob, 'recording.webm');

const response = await fetch('http://localhost:8000/upload-audio', {
  method: 'POST',
  body: formData,
});

const result = await response.json();
```

### レスポンス例（Phase 3 以降の想定）

```json
{
  "transcript": "Hello, how are you today?",
  "score": 82,
  "feedback": "「today」の発音がやや不明瞭でした。舌の位置を意識してみましょう。",
  "words": [
    { "text": "Hello", "start": 0.12, "end": 0.45, "avg_logprob": -0.23 },
    { "text": "how", "start": 0.50, "end": 0.68, "avg_logprob": -0.18 }
  ],
  "graph_data": [],
  "audio_url": "/storage/processed_wav/response.wav"
}
```

## 開発フェーズ別の実装目標

### Phase 1: 疎通確認

- [ ] マイク権限の取得と録音開始・停止
- [ ] `audio/webm` 形式で `Blob` を生成
- [ ] `POST /upload-audio` でバックエンドへ送信
- [ ] レスポンス JSON を画面に表示（エラーハンドリング含む）

### Phase 2: STT 結果の表示

- [ ] 文字起こしテキストの表示
- [ ] 単語ごとのタイムスタンプ・信頼度の一覧表示

### Phase 3: LLM フィードバックの表示

- [ ] 日本語アドバイステキストの表示
- [ ] 総合スコアの表示

### Phase 4: 高度な UI

- [ ] DTW グラフ（発話ペースのズレ可視化）
- [ ] AI 教師の返答音声の再生
- [ ] お手本音声との比較 UI

## 録音フロー（設計）

```text
[録音開始] → MediaRecorder.start()
     ↓
  音声チャンクをメモリに蓄積
     ↓
[録音停止] → MediaRecorder.stop() → Blob 生成
     ↓
  FormData にパッケージング
     ↓
  fetch → localhost:8000/upload-audio
     ↓
  JSON レスポンスを UI に反映
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| マイクが使えない | ブラウザのサイト権限でマイクを許可。`file://` ではなく `http://localhost` で開く |
| CORS エラー | バックエンドの `CORSMiddleware` 設定を確認（[backend README](../backend/README.md)） |
| `fetch` が失敗する | WSL2 でバックエンドが起動しているか確認: `curl http://localhost:8000/health` |
| 録音データが空 | `MediaRecorder` の `ondataavailable` でチャンクが溜まってから `stop()` すること |

## 関連ドキュメント

- [プロジェクト全体 README](../README.md)
- [バックエンド README](../backend/README.md)
