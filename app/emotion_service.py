import io
import os
import tempfile
from typing import Dict, Any
import librosa
import torch
from transformers import Wav2Vec2ForSequenceClassification, Wav2Vec2FeatureExtractor
import numpy as np


class EmotionAnalyzer:
    def __init__(self):
        self.model = None
        self.feature_extractor = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load_model()
    
    def _load_model(self):
        """Hugging Face 모델 로드"""
        model_name = "jungjongho/wav2vec2-xlsr-korean-speech-emotion-recognition"
        
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
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                content = audio_file.file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            # 오디오 로드 (16kHz로 리샘플링)
            audio, sr = librosa.load(tmp_file_path, sr=16000)
            
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
            
            # 감정 라벨 (모델에 따라 조정 필요)
            emotion_labels = ["neutral", "happy", "sad", "angry", "fear", "surprise", "disgust"]
            
            # 가장 높은 확률의 감정
            predicted_class = torch.argmax(predictions, dim=-1).item()
            confidence = predictions[0][predicted_class].item()
            emotion = emotion_labels[predicted_class] if predicted_class < len(emotion_labels) else "unknown"
            
            # 모든 감정의 확률
            emotion_scores = {
                emotion_labels[i]: predictions[0][i].item() 
                for i in range(min(len(emotion_labels), predictions.shape[1]))
            }
            
            return {
                "emotion": emotion,
                "confidence": confidence,
                "emotion_scores": emotion_scores,
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
                os.unlink(tmp_file_path)
            except OSError as e:
                print(f"임시 파일 삭제 실패: {tmp_file_path}, 오류: {e}")


# 전역 인스턴스
emotion_analyzer = EmotionAnalyzer()


def analyze_voice_emotion(audio_file) -> Dict[str, Any]:
    """음성 감정 분석 함수"""
    return emotion_analyzer.analyze_emotion(audio_file)
