import os
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PROCESSED_WAV_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage",
    "processed_wav",
)

LANGUAGE_SPEAKERS = {
    "JP": "JP",
    "EN": "EN-US",
}


class TTSService:
    """
    MeloTTS による音声合成サービス（任意）。
    未インストール時はスキップし、STT / LLM はそのまま動作する。
    """

    def __init__(self, default_language: str = "JP", device: str = "auto", speed: float = 1.0):
        self.default_language = default_language
        self.device = device
        self.speed = speed
        self._models: dict = {}
        self._melo_available: Optional[bool] = None
        os.makedirs(PROCESSED_WAV_DIR, exist_ok=True)

    @property
    def is_available(self) -> bool:
        return self._check_melo_available()

    def _check_melo_available(self) -> bool:
        if self._melo_available is None:
            try:
                from melo.api import TTS  # noqa: F401
                self._melo_available = True
            except ImportError:
                logger.warning("MeloTTS is not installed. TTS features will be disabled.")
                self._melo_available = False
        return self._melo_available

    def _get_model(self, language: str):
        if not self._check_melo_available():
            raise RuntimeError("MeloTTS is not installed.")

        if language not in self._models:
            from melo.api import TTS

            logger.info(f"Loading MeloTTS model for language '{language}'...")
            try:
                model = TTS(language=language, device=self.device)
                self._models[language] = model
                logger.info(f"MeloTTS loaded for '{language}' (device={self.device})")
            except Exception as e:
                logger.warning(f"Failed to load MeloTTS on {self.device}: {e}. Falling back to CPU.")
                model = TTS(language=language, device="cpu")
                self._models[language] = model
                logger.info(f"MeloTTS loaded for '{language}' on CPU")
        return self._models[language]

    def _resolve_speaker_id(self, model, language: str) -> int:
        speaker_ids = model.hps.data.spk2id
        speaker_key = LANGUAGE_SPEAKERS.get(language, language)
        if speaker_key in speaker_ids:
            return speaker_ids[speaker_key]
        return next(iter(speaker_ids.values()))

    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        if not text or not text.strip():
            return None
        if not self._check_melo_available():
            return None

        lang = language or self.default_language
        os.makedirs(PROCESSED_WAV_DIR, exist_ok=True)

        if not filename:
            filename = f"tts_{uuid.uuid4().hex}.wav"
        elif not filename.endswith(".wav"):
            filename = f"{filename}.wav"

        output_path = os.path.join(PROCESSED_WAV_DIR, filename)

        try:
            model = self._get_model(lang)
            speaker_id = self._resolve_speaker_id(model, lang)
            logger.info(f"Synthesizing speech ({lang}): {text[:80]}...")
            model.tts_to_file(text.strip(), speaker_id, output_path, speed=self.speed, quiet=True)
            logger.info(f"TTS output saved: {output_path}")
            return filename
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}", exc_info=True)
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return None

    def synthesize_feedback(self, feedback_text: str) -> Optional[str]:
        return self.synthesize(
            feedback_text,
            language="JP",
            filename=f"feedback_{uuid.uuid4().hex}.wav",
        )

    def synthesize_reference(self, transcript: str) -> Optional[str]:
        return self.synthesize(
            transcript,
            language="EN",
            filename=f"reference_{uuid.uuid4().hex}.wav",
        )
