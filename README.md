

# 英語音声判定アプリ (ローカルLLM主軸型 AI英語発音コーチ)

ローカル計算資源（Windows 11 + WSL2 / GPU）をフル活用し、外部APIへの依存度・通信費ゼロで実現する「対話型AI英語発音コーチアプリ」の開発計画および技術仕様ドキュメントです。

## 🚀 1. プロダクトゴール
> 「ローカルLLMが『主治医』のように対話し、発音・文法・表現のすべてをリアルタイムに軌道修正してくれる、完全密室型のAI英語インテンシブ・ラボ」
>
> どれだけ文法がボロボロな声を聴かせても恥ずかしくない「完全なプライベート空間」と、通信費を気にせず「完全に自分の学習ペースに付き合ってくれる心理的安全性」を最大の価値とします。

## 🎯 2. 全体の開発手順 (ロードマップ)

環境構築のバグや依存関係の沼を避けるため、4つのフェーズに分けて段階的に開発を進めます。

```text
【Phase 1: 疎通確認】 ──> 【Phase 2: 耳(STT)の実装】 ──> 【Phase 3: 脳(LLM)の連動】 ──> 【Phase 4: 口(TTS)とUI】
Windowsマイク ➡️ WSL2     音声のWAV変換 ➡️ タイムスタンプ抽出   Ollamaへのメタデータ注入 ＆ 評価     MeloTTSによる返答の音声化 ＆ グラフ表示
```

* フェーズ 1：最小限の通信疎通（プロトタイプ構築）
* Windows（フロント）でマイク録音し、WSL2（バックエンド）のFastAPIへデータをPOST送信できる状態を最優先で確立します（CORSとマイク問題をここでクリア）。
* フェーズ 2：音声認識（耳）の組み込み
* WSL2側に `faster-whisper` を導入。受信した音声（WebM等）をFFmpegでWAV（16kHz/モノラル）に変換し、単語ごとのタイムスタンプ（`start`、`end`）と信頼度（`avg_logprob`）を正しくJSON化します。
* フェーズ 3：ローカルLLM（脳）との連動
* Ollamaを立ち上げ、Whisperが吐き出した「文字起こし文＋タイムスタンプや信頼度のメタデータ」をプロンプトに注入。ユーザーへの的確な英語指導レポートを日本語で生成させます。
* フェーズ 4：UIの高度化と音声合成（口）の追加
* フロントエンドのグラフ表示（DTWによるズレの可視化）の実装、および `MeloTTS` 等を用いた「AI教師の返答音声化」を実装し、完全な対話ループを完成させます。

## 🛠️ 3. システム構成図

マイク入力を確実に成功させるため、「フロントエンドはWindowsネイティブ（ブラウザ）」、「重いAI処理はWSL2（Ubuntu + GPU）」に分離したハイブリッド構成を採用しています。

```text
+------------------------------------+       +------------------------------------------------------+
|       [ Windows 11 側 ]            |       |                [ WSL2 / Ubuntu 側 ]                  |
|                                    |       |                                                      |
|  +------------------------------+  |       |  +------------------------------------------------+  |
|  |     Frontend (UI / ブラウザ) |  |       |  |            Backend (FastAPI)                   |  |
|  |                              |  |       |  |                                                |  |
|  |  1. 課題文 / 対話テキスト提示  |  |       |  |  ・CORS許可設定（Windowsからの通信を許可）       |  |
|  |  2. マイク録音 (Web Audio API) |  |       |  |  ・音声受信 ＆ FFmpegによるWAV変換処理         |  |
|  |  3. 解析グラフ・指導文の表示  |  |       |  +--------┬───────────────────┬────────────────+  |
|  +--------------┬---------------+  |       |           │                   │                    |
|                 │                  |       |           │ ①音声データ解析  │ ②テキスト&メタデータ|
|                 │ WAV/WebM 送信    |       |           ▼                   ▼                    |
|                 │ (localhost:8000) |       |  +-----------------+ +--------------------------+  |
|                 ▼                  |       |  |  耳 (STT):       | |  脳 (ローカルLLM):       |  |
|       (ローカルネットワーク通信)    +----->+  |  faster-whisper | |  Ollama                  |  |
|                 ▲                  |       |  |  (large-v3)     | |  (Qwen2.5-Coder / Llama3)|  |
|                 │                  |       |  +--------┬--------+ +----------------┬---------+  |
|                 │ 解析結果 (JSON)   |       |           │                          │            |
|                 │ ＆ お手本音声URL  |       |           │ 基準音声の生成           │ 返答の音声化|
|                 │                  |       |           ▼                          ▼            |
|                 │                  |       |  +--------------------------------------------+  |
|                 │                  |       |  |  口 (TTS): MeloTTS / StyleTTS2             |  |
|                 └──────────────────+───────+  +--------------------------------------------+  |
+------------------------------------+       +------------------------------------------------------+
```

```mermaid
graph TD
    %% スタイルの定義
    classDef win fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    classDef wsl fill:#efebe9,stroke:#795548,stroke-width:2px;
    classDef ai fill:#fff3e0,stroke:#ff9800,stroke-width:2px;

    %% Windows側の構成
    subgraph Windows11 [Windows 11 側 : フロントエンド]
        UI[ブラウザ UI<br>・課題提示<br>・グラフ表示]:::win
        Microphone[Web Audio API<br>・マイク録音]:::win
    end

    %% WSL2側の構成
    subgraph WSL2 [WSL2 / Ubuntu 側 : バックエンド]
        FastAPI[FastAPI サーバー<br>localhost:8000]:::wsl
        FFmpeg[FFmpeg<br>16kHz WAV変換]:::wsl

        subgraph AI_Engines [ローカルAIエンジン群]
            STT[耳: faster-whisper<br>単語ごとのタイムスタンプ抽出]:::ai
            LLM[脳: Ollama / Qwen2.5-Coder<br>発音・指導アドバイス生成]:::ai
            TTS[口: MeloTTS<br>AI教師の返答音声化]:::ai
        end
    end

    %% データの流れの定義
    Microphone -->|① 音声データ送信<br>WebM / WAV| FastAPI
    FastAPI -->|② 変換処理| FFmpeg
    FFmpeg -->|③ WAVデータ渡し| STT
    STT -->|④ テキスト化 ＆ メタデータ| LLM
    LLM -->|⑤ レポート文生成| TTS
    LLM -->|⑥ 解析結果 JSON| UI
    TTS -->|⑦ お手本・返答音声| UI

    %% クラスの適用
    class Windows11 win;
    class WSL2 wsl;

## 📁 4. ディレクトリ構造

WSL2環境側でGitを初期化（`git init`）し、プロジェクトを一括管理します。Windows側からはVS Codeの「WSL拡張機能」を使ってこのフォルダを開き、コーディングを行います。

```text
english-learning-app/
│
├── .gitignore               # ← 超重要：巨大なモデルファイルや音声生データを除外
├── README.md                # 本ドキュメント
│
├── frontend/                # 【Windows側（ブラウザ）で動作・表示】
│   ├── index.html           # 録音・結果表示を行うメインUI
│   └── js/
│       └── app.js           # 録音制御、FastAPIへのFetch通信ロジック
│
└── backend/                 # 【WSL2 / Ubuntu（GPU）側で実行】
├── main.py              # FastAPIのエントリーポイント（CORS設定、ルーティング）
├── requirements.txt     # Python依存ライブラリ一覧
│
├── services/            # 各AI機能のモジュール化
│   ├── stt_service.py   # faster-whisperによる文字起こし・メタデータ抽出
│   ├── llm_service.py   # Ollama API（ユーザーへのアドバイス生成）
│   └── tts_service.py   # MeloTTS等による音声合成
│
└── storage/             # ← .gitignore でGit管理から除外
├── raw_audio/       # フロントから届いた一時音声（webmなど）
└── processed_wav/   # Whisper用に16kHzに変換したWAV、およびTTS生成音声
```

### 必須設定: `.gitignore`
巨大なAIモデルや、ユーザーの音声ファイルがGit履歴に含まれてパンクするのを防ぐため、必ず以下の内容を設定してください。

```text
.venv/
pycache/
*.webm
*.wav
*.mp3
backend/storage/
.cache/
```

## 🛠️ 5. 技術スタック ＆ 推奨ライブラリ

### ハードウェア要件
* GPU: NVIDIA製 GPU（VRAM 12GB以上 を強く推奨。各AIモデルをグラフィックスメモリに同時常駐させるために重要です）

### フロントエンド（Windows側）
* コア技術: HTML5 / JavaScript (Vanilla JS、または拡張時に Next.js)
* 録音API: `MediaRecorder API` (ブラウザ標準のマイクキャプチャ機能)
* 可視化: `Plotly.js` または `Chart.js` (DTWのズレを可視化するグラフ用)

### バックエンド（WSL2 / Ubuntu側）
* ベース: Python 3.10+, CUDA Toolkit 12.x
* サーバーフレームワーク: `FastAPI` + `uvicorn`
* 耳 (STT): `faster-whisper` (CTranslate2実装により、本家OpenAI版より高速・低VRAM駆動。単語単位のタイムスタンプ抽出に使用)
* 脳 (LLM): `Ollama`（ローカルAIサーバー。`qwen2.5-coder:7b` や `llama3:8b` の4-bit量子化版を推奨）
* 口 (TTS): `MeloTTS`（MyShell製。環境構築が容易で、CPU/GPU問わず爆速でネイティブ音声を生成可能。将来的に表現力を極める場合は `StyleTTS2` を検討）
* 数理アルゴリズム: `fastdtw`、`scipy`（お手本音声とユーザー音声のタイムスタンプ配列をアライメントし、発話ペースのズレを計算）
* オーディオ処理: `pydub` ＋ `ffmpeg-python`（フロントから届いた音声をWhisperが最も得意とする `16kHz / 16bit / モノラル` のWAVへ変換）

## 📝 6. 前後端（フロント・バック）の詳細設計

### フロントエンド（Windowsブラウザ）の責務

ユーザー操作: 「録音開始」ボタンでマイク権限を要求し、`MediaRecorder` で音声チャンク（`Blob`）をメモリに蓄積。

データ送信: 「録音停止」で録音を終了し、データを `audio/webm` バイナリとして `FormData` にパッケージング。`fetch('http://localhost:8000/upload-audio')` でWSL2のFastAPIへPOST送信。

結果レンダリング: FastAPIから戻ってきた判定JSON（スコア、LLMのアドバイステキスト、グラフ用配列データ）を元にUIを動的更新。

### バックエンド（WSL2 / FastAPI）の責務

CORSの突破: Windowsのブラウザ（別オリジン）からのリクエストを拒否しないよう、`CORSMiddleware` を設定。

音声ファイルの標準化: 届いたデータを一度保存し、内部で `ffmpeg` を呼び出して `16kHz / 16bit / モノラル` のWAVファイルへ確実に変換。

耳（STT）の駆動: `faster-whisper` にWAVを通し、単語ごとの「テキスト」「開始時間」「終了時間」「平均対数確率（avg_logprob）」を抽出。

脳（LLM）の駆動: 抽出したデータを元に、「何秒言い淀んだか」「どこが発音不良か」のメタデータを算出し、Ollamaに対して構造化したJSONプロンプトを組み立てて送信。

レスポンス: LLMが生成した人間味のあるフィードバック文と、評価数値を合算してフロントエンドにクリーンなJSONとして返却。

## 📈 7. 【拡張機能提案】ユーザー専用の「弱点カルテ」
アプリの価値をさらに高めるため、以下の機能をフェーズ4以降に導入することを推奨します。

* 概要: 毎回「1回きりの採点」で終わらせず、過去のデータをローカルの軽量なデータベース（SQLiteやJSONログ、またはVector DBの `Chroma`）に蓄積。
* 効果: ローカルLLMを動かす際、「このユーザーは過去に `th` と `rl` の発音で5回以上つまづいています」という履歴情報をプロンプトに一緒に引き渡します（RAGの要領）。これにより、LLMが「また `world` でつまずいてしまいましたね。でも前回より言い淀み時間は0.5秒短縮されていますよ！」といった、ユーザーの過去の成長を追える、世界で唯一の完全パーソナライズ化されたAI英語教師へと進化させることが可能です。