import io
import tempfile
from typing import Dict, Any
import librosa
import torch
from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2FeatureExtractor
import soundfile as sf
import numpy as np


class EmotionAnalyzer:
    def __init__(self):
        self.model = None
        self.feature_extractor = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load_model()
    
    def _load_model(self):
        """Hugging Face 모델 로드"""
        # rebalanced 모델로 교체
        # https://huggingface.co/jungjongho/wav2vec2-xlsr-korean-speech-emotion-recognition2_data_rebalance
        model_name = "jungjongho/wav2vec2-xlsr-korean-speech-emotion-recognition2_data_rebalance"
        
        try:
            self.model = Wav2Vec2ForSequenceClassification.from_pretrained(model_name)
            self.feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
        except Exception as e:
            print(f"모델 로드 실패: {e}")
            self.model = None
            self.feature_extractor = None
    
    def analyze_emotion(self, audio_file) -> Dict[str, Any]:
        """
        음성 파일의 감정을 분석합니다.
        
        Args:
            audio_file: 업로드된 음성 파일 (FastAPI UploadFile)
            
        Returns:
            Dict: 감정 분석 결과
        """
        if not self.model or not self.feature_extractor:
            return {
                "error": "모델이 로드되지 않았습니다",
                "emotion": "unknown",
                "confidence": 0.0
            }
        
        try:
            # 업로드 확장자 반영하여 임시 파일로 저장
            import os
            orig_name = getattr(audio_file, "filename", "") or ""
            _, ext = os.path.splitext(orig_name)
            suffix = ext if ext.lower() in [".wav", ".m4a", ".mp3", ".flac", ".ogg", ".aac", ".caf"] else ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                content = audio_file.file.read()
                audio_file.file.seek(0)
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            # 오디오 로드 (16kHz, 견고한 로더)
            def robust_load(path: str, target_sr: int = 16000):
                try:
                    data, sr = sf.read(path, always_2d=True, dtype="float32")
                    if data.ndim == 2 and data.shape[1] > 1:
                        data = data.mean(axis=1)
                    else:
                        data = data.reshape(-1)
                    if sr != target_sr:
                        data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
                        sr = target_sr
                    return data, sr
                except Exception:
                    y, sr = librosa.load(path, sr=target_sr, mono=True)
                    return y.astype("float32"), sr

            audio, sr = robust_load(tmp_file_path, 16000)
            
            # 특성 추출
            inputs = self.feature_extractor(
                audio, 
                sampling_rate=16000, 
                return_tensors="pt", 
                padding=True
            )
            
            # GPU로 이동
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # 추론
            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
            # 감정 라벨 매핑: 모델 config 우선, 숫자형 값이면 사람이 읽을 수 있는 이름으로 대체
            default_labels = ["neutral", "happy", "sad", "angry", "fear", "surprise"]
            id2label = getattr(self.model.config, "id2label", None)
            if isinstance(id2label, dict) and predictions.shape[1] == len(id2label):
                labels = [id2label.get(str(i), id2label.get(i, str(i))) for i in range(predictions.shape[1])]
                # 값이 전부 숫자 형태라면 사람이 읽을 수 있는 기본 라벨로 대체
                if all(isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()) for v in labels):
                    emotion_labels = default_labels[:predictions.shape[1]]
                else:
                    emotion_labels = labels
            else:
                emotion_labels = default_labels[:predictions.shape[1]]
            
            # 가장 높은 확률의 감정
            predicted_class = torch.argmax(predictions, dim=-1).item()
            confidence = predictions[0][predicted_class].item()
            emotion = emotion_labels[predicted_class] if predicted_class < len(emotion_labels) else "unknown"
            
            # 모든 감정의 확률
            emotion_scores = {
                emotion_labels[i]: predictions[0][i].item()
                for i in range(min(len(emotion_labels), predictions.shape[1]))
            }
            
            # 한국어 라벨 → 영어 라벨 매핑
            ko2en = {
                "중립": "neutral",
                "기쁨": "happy",
                "행복": "happy",
                "슬픔": "sad",
                "분노": "angry",
                "화남": "angry",
                "불안": "anxiety",
                "두려움": "fear",
                "공포": "fear",
                "놀람": "surprise",
                "당황": "surprise",
            }

            def to_en(label: str) -> str:
                if not isinstance(label, str):
                    return str(label)
                return ko2en.get(label, label)

            emotion_en = to_en(emotion)
            emotion_scores_en = {to_en(k): v for k, v in emotion_scores.items()}

            return {
                "emotion": emotion_en,                 # 대표 감정 (영문)
                "top_emotion": emotion_en,             # 동일 표기(영문)
                "confidence": confidence,              # 대표 감정 확률
                "emotion_scores": emotion_scores_en,   # 영문 라벨명→확률
                "audio_duration": len(audio) / sr,
                "sample_rate": sr
            }
            
        except Exception as e:
            return {
                "error": f"분석 중 오류 발생: {str(e)}",
                "emotion": "unknown",
                "confidence": 0.0
            }
        finally:
            # 임시 파일 정리
            try:
                import os
                os.unlink(tmp_file_path)
            except:
                pass


# 전역 인스턴스
emotion_analyzer = EmotionAnalyzer()


def analyze_voice_emotion(audio_file) -> Dict[str, Any]:
    """음성 감정 분석 함수"""
    return emotion_analyzer.analyze_emotion(audio_file)
