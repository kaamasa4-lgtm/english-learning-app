import os
import logging
from pydub import AudioSegment
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

class STTService:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model_instance = None
        self.device = "unknown"

    def get_whisper_model(self):
        """
        faster-whisperモデルのインスタンスを取得。
        WSL2のGPU (CUDA) の利用可否を確認し、エラー時は自動的にCPUへフォールバックします。
        """
        if self._model_instance is None:
            logger.info(f"Loading faster-whisper model '{self.model_size}'...")
            try:
                self._model_instance = WhisperModel(self.model_size, device="cuda", compute_type="float16")
                self.device = "cuda"
                logger.info("faster-whisper loaded successfully on GPU (CUDA, float16)")
            except Exception as e:
                logger.warning(f"Failed to initialize faster-whisper on CUDA: {str(e)}. Falling back to CPU.")
                try:
                    self._model_instance = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                    self.device = "cpu"
                    logger.info("faster-whisper loaded successfully on CPU (int8)")
                except Exception as cpu_error:
                    logger.error(f"Failed to initialize faster-whisper on CPU: {str(cpu_error)}")
                    raise cpu_error
                    
        return self._model_instance

    def convert_audio_to_wav(self, input_path: str, output_path: str) -> str:
        """
        入力音声ファイル（WebM, MP3等）を 16kHz / 16bit / モノラル の WAV形式に変換します。
        """
        logger.info(f"Converting {input_path} to WAV ({output_path})...")
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input audio file not found: {input_path}")
            
        try:
            audio = AudioSegment.from_file(input_path)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            audio.export(output_path, format="wav")
            logger.info(f"Audio conversion completed: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Audio conversion failed via pydub: {str(e)}")
            try:
                import subprocess
                logger.info("Attempting fallback conversion via ffmpeg subprocess...")
                cmd = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", output_path
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logger.info(f"Audio conversion completed via fallback FFmpeg: {output_path}")
                return output_path
            except Exception as ffmpeg_error:
                logger.error(f"Fallback FFmpeg conversion also failed: {str(ffmpeg_error)}")
                raise RuntimeError(f"Failed to convert audio: {str(e)} / {str(ffmpeg_error)}")

    def transcribe(self, file_path: str) -> dict:
        """
        音声ファイルをWAVに変換してから文字起こしを実行し、結果を返します。
        """
        # 一時WAVファイルパスの生成
        wav_path = os.path.splitext(file_path)[0] + "_converted.wav"
        
        try:
            # 1. WAV変換
            self.convert_audio_to_wav(file_path, wav_path)
            
            # 2. 文字起こし
            logger.info(f"Starting transcription for {wav_path}...")
            model = self.get_whisper_model()
            
            segments, info = model.transcribe(wav_path, word_timestamps=True, language="en")
            
            words_data = []
            full_transcript_parts = []
            
            for segment in segments:
                full_transcript_parts.append(segment.text)
                
                if segment.words:
                    for word in segment.words:
                        words_data.append({
                            "text": word.word.strip(),
                            "start": round(word.start, 2),
                            "end": round(word.end, 2),
                            "avg_logprob": round(word.probability, 4)
                        })
                else:
                    words = segment.text.strip().split()
                    if words:
                        duration = segment.end - segment.start
                        word_duration = duration / len(words)
                        for i, w in enumerate(words):
                            words_data.append({
                                "text": w,
                                "start": round(segment.start + i * word_duration, 2),
                                "end": round(segment.start + (i + 1) * word_duration, 2),
                                "avg_logprob": 0.5
                            })
                            
            full_transcript = " ".join(full_transcript_parts).strip()
            logger.info(f"Transcription completed. Text: {full_transcript}")
            
            return {
                "transcript": full_transcript,
                "words": words_data
            }
            
        finally:
            # 一時WAVファイルの削除
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass