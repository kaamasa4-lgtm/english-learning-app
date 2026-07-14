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
        setConnectionStatus(true);
        return;
      }
    }
    setConnectionStatus(false);
  } catch (error) {
    console.warn('Backend connection check failed:', error);
    setConnectionStatus(false);
  }
}

/**
 * 接続状態のUIを切り替える
 */
function setConnectionStatus(isConnected) {
  if (isConnected) {
    statusBadge.className = 'status-badge connected';
    statusText.textContent = 'サーバー接続済み';
  } else {
    statusBadge.className = 'status-badge disconnected';
    statusText.textContent = 'サーバー未接続';
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
    // マイクのアクセス権限を取得
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    // サポートされている録音形式を確認し、優先的にwebmを指定
    let options = { mimeType: 'audio/webm' };
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
      console.log(`${options.mimeType} is not supported. Using default browser audio format.`);
      options = {}; // デフォルトの形式を使用
    }

    mediaRecorder = new MediaRecorder(stream, options);
    
    // 録音データのチャンクが利用可能になった時のイベントハンドラ
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    // 録音停止時のイベントハンドラ
    mediaRecorder.onstop = async () => {
      // マイクのトラックをすべて停止してインジケータを消す
      stream.getTracks().forEach(track => track.stop());
      
      // 録音データをBlob化
      const audioBlob = new Blob(audioChunks, { type: options.mimeType || 'audio/webm' });
      console.log('Audio blob created. Size:', audioBlob.size, 'MIME:', audioBlob.type);
      
      // バックエンドへ送信
      await uploadAudio(audioBlob);
    };

    // 録音開始
    mediaRecorder.start();
    isRecording = true;
    startTime = Date.now();
    
    // UIの更新
    recordBtn.classList.add('recording');
    micIcon.style.display = 'none';
    stopIcon.style.display = 'block';
    timerDisplay.classList.add('active');
    
    // タイマーの始動
    timerDisplay.textContent = '00:00';
    timerInterval = setInterval(updateTimer, 1000);
    
    console.log('Recording started');

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
  
  // UIの更新
  recordBtn.classList.remove('recording');
  micIcon.style.display = 'block';
  stopIcon.style.display = 'none';
  timerDisplay.classList.remove('active');
  
  // タイマーのクリア
  clearInterval(timerInterval);
  timerInterval = null;
  
  console.log('Recording stopped');
}

/**
 * 録音データをバックエンドへ送信
 */
async function uploadAudio(audioBlob) {
  loader.style.display = 'flex';
  responseContainer.innerHTML = '';
  responseMeta.textContent = '送信中...';

  // FormDataオブジェクトの作成
  const formData = new FormData();
  // 拡張子つきのファイル名でBlobをアタッチする
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
    console.log('Server response:', result);

    // UIへ結果を出力
    responseMeta.textContent = `${elapsedMs}ms | ステータス: OK`;
    
    // プレミアムなカードUIで表示
    responseContainer.innerHTML = `
      <div class="result-card">
        <div class="result-row">
          <span class="result-label">メッセージ</span>
          <span class="result-value success">${result.message}</span>
        </div>
        <div class="result-row">
          <span class="result-label">保存ファイル名</span>
          <span class="result-value">${result.filename}</span>
        </div>
        <div class="result-row">
          <span class="result-label">ファイルサイズ</span>
          <span class="result-value">${(result.size_bytes / 1024).toFixed(2)} KB</span>
        </div>
      </div>
    `;

    // サーバーとの接続状態も再確認して更新
    setConnectionStatus(true);

  } catch (error) {
    console.error('Error uploading audio:', error);
    responseMeta.textContent = 'エラー';
    responseContainer.innerHTML = `
      <div style="color: #ef4444; font-family: inherit;">
        <strong>送信に失敗しました:</strong><br>
        ${error.message}<br><br>
        <span style="font-size: 0.8rem; color: var(--text-secondary);">
          ・WSL2側でサーバーが起動しているか確認してください。<br>
          ・ブラウザとサーバーのCORS設定が一致しているか確認してください。
        </span>
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
  
  // 定期的に接続を確認する (5秒おき)
  setInterval(checkServerConnection, 5000);
});
