// バックエンドのベースURL設定 (WSL2のFastAPIをターゲット)
const BACKEND_URL = 'http://localhost:8000';

// DOM要素の取得
const statusBadge = document.getElementById('statusBadge');
const statusText = document.getElementById('statusText');
const recordBtn = document.getElementById('recordBtn');
const micIcon = document.getElementById('micIcon');
const stopIcon = document.getElementById('stopIcon');
const timerDisplay = document.getElementById('timer');
const loader = document.getElementById('loader');
const responseContainer = document.getElementById('responseContainer');
const responseMeta = document.getElementById('responseMeta');

// 録音ステート変数
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let startTime = null;
let timerInterval = null;

/**
 * バックエンドサーバーとの疎通確認 (ヘルスチェック)
 */
async function checkServerConnection() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`, { method: 'GET' });
    if (response.ok) {
      const data = await response.json();
      if (data.status === 'ok') {
        const ttsLabel = data.tts_available ? 'TTS: 有' : 'TTS: 無';
        setConnectionStatus(true, `接続中 / ${data.model} / ${ttsLabel}`);
        return;
      }
    }
    setConnectionStatus(false, 'サーバー未接続');
  } catch (error) {
    setConnectionStatus(false, 'サーバー未接続');
  }
}

/**
 * 接続状態のUIを切り替える
 */
function setConnectionStatus(isConnected, message = '') {
  if (isConnected) {
    statusBadge.className = 'status-badge connected';
    statusText.textContent = message || 'サーバー接続済み';
  } else {
    statusBadge.className = 'status-badge disconnected';
    statusText.textContent = message || 'サーバー未接続';
  }
}

/**
 * タイマー表示の更新
 */
function updateTimer() {
  if (!startTime) return;
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const seconds = String(elapsed % 60).padStart(2, '0');
  timerDisplay.textContent = `${minutes}:${seconds}`;
}

/**
 * 録音開始処理
 */
async function startRecording() {
  audioChunks = [];
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    let options = { mimeType: 'audio/webm' };
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      options = {}; // ブラウザのデフォルト形式
    }

    mediaRecorder = new MediaRecorder(stream, options);
    
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      const audioBlob = new Blob(audioChunks, { type: options.mimeType || 'audio/webm' });
      await uploadAudio(audioBlob);
    };

    mediaRecorder.start();
    isRecording = true;
    startTime = Date.now();
    
    // UIの更新
    recordBtn.classList.add('recording');
    micIcon.style.display = 'none';
    stopIcon.style.display = 'block';
    timerDisplay.classList.add('active');
    
    timerDisplay.textContent = '00:00';
    timerInterval = setInterval(updateTimer, 1000);

  } catch (error) {
    console.error('Error starting recording:', error);
    alert('マイクのアクセス許可が得られないか、マイクが接続されていません。');
    isRecording = false;
  }
}

/**
 * 録音停止処理
 */
function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === 'inactive') return;

  mediaRecorder.stop();
  isRecording = false;
  
  recordBtn.classList.remove('recording');
  micIcon.style.display = 'block';
  stopIcon.style.display = 'none';
  timerDisplay.classList.remove('active');
  
  clearInterval(timerInterval);
  timerInterval = null;
}

/**
 * 簡易Markdownパーサー (LLMからのレスポンス整形用)
 */
function parseMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/^\- (.*$)/gim, '<li>$1</li>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

/**
 * 録音データをバックエンドへ送信 & 結果描画
 */
async function uploadAudio(audioBlob) {
  loader.style.display = 'flex';
  responseContainer.innerHTML = '';
  responseMeta.textContent = '解析中...';

  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');

  const uploadStart = Date.now();

  try {
    const response = await fetch(`${BACKEND_URL}/upload-audio`, {
      method: 'POST',
      body: formData
    });

    const elapsedMs = Date.now() - uploadStart;

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server returned error: ${response.status} - ${errorText}`);
    }

    const result = await response.json();

    // メタ情報の更新
    responseMeta.textContent = `処理時間: ${(elapsedMs / 1000).toFixed(1)}s | ファイル: ${(result.size_bytes / 1024).toFixed(1)} KB`;
    
    // 1. 文字起こし文の表示
    const transcriptHtml = `
      <div class="section-block">
        <div class="section-title">文字起こし</div>
        <div class="transcript-text">
          ${result.transcript || '<span class="empty-state">音声が認識されませんでした。</span>'}
        </div>
      </div>
    `;

    // 2. 単語ごとのタイムラインバッジ作成
    let timelineHtml = '<div class="section-block"><div class="section-title">単語ごとの解析</div><div class="timeline-container">';
    if (result.words && result.words.length > 0) {
      result.words.forEach(word => {
        const scorePct = Math.round(word.avg_logprob * 100);
        timelineHtml += `
          <div class="word-badge">
            <span class="word-text">${word.text}</span>
            <span class="word-time">${word.start.toFixed(1)}s - ${word.end.toFixed(1)}s</span>
            <span class="word-score">${scorePct}%</span>
          </div>
        `;
      });
    } else {
      timelineHtml += '<p class="empty-state">単語ごとの情報はありません。</p>';
    }
    timelineHtml += '</div></div>';

    // 3. AIコーチからのアドバイスカード作成
    let feedbackHtml = '';
    if (result.feedback) {
      feedbackHtml = `
        <div class="section-block feedback-block">
          <h3>アドバイス</h3>
          <div>${parseMarkdown(result.feedback)}</div>
        </div>
      `;
    }

    let audioHtml = '';
    if (result.audio_url) {
      audioHtml = `
        <div class="section-block audio-block">
          <h3>音声フィードバック</h3>
          <audio controls src="${BACKEND_URL}${result.audio_url}"></audio>
        </div>
      `;
    }

    // 表示エリアへ結合して描画
    responseContainer.innerHTML = transcriptHtml + timelineHtml + feedbackHtml + audioHtml;

  } catch (error) {
    console.error('Error uploading audio:', error);
    responseMeta.textContent = 'エラー';
    responseContainer.innerHTML = `
      <div class="error-block">
        <strong>送信に失敗しました</strong><br>
        ${error.message}
        <div class="error-hint">
          バックエンド（FastAPI）と Ollama が起動しているか確認してください。
        </div>
      </div>
    `;
  } finally {
    loader.style.display = 'none';
  }
}

// 録音ボタンのクリックイベント
recordBtn.addEventListener('click', () => {
  if (isRecording) {
    stopRecording();
  } else {
    startRecording();
  }
});

// 初期ロード時にサーバーの接続状態をチェック
document.addEventListener('DOMContentLoaded', () => {
  checkServerConnection();
  setInterval(checkServerConnection, 5000);
});