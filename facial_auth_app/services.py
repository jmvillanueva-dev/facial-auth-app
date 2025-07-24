# facial_auth_app/services.py
import cv2, io, numpy as np, tensorflow as tf, tensorflow_hub as hub
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import FacialRecognitionProfile

User = get_user_model()

# ------------------------------------------------------------------
# 1. Cargar el modelo una sola vez al arrancar Django
# ------------------------------------------------------------------
facenet = hub.load(
    "https://tfhub.dev/google/imagenet/inception_resnet_v2/feature_vector/4"
)
EMBEDDING_DIM = 1536

# NOTA: el modelo anterior es un extractor genérico.
# Para FaceNet puro usa:  https://tfhub.dev/google/tf2-preview/inception_resnet_v2/feature_vector/4
# o cualquier FaceNet convertido a TF-Hub.


# ------------------------------------------------------------------
# 2. Utils
# ------------------------------------------------------------------
def _bytes_to_array(img_bytes: bytes) -> np.ndarray:
    """Convierte bytes crudos a RGB array."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


def _preprocess(img_array: np.ndarray) -> tf.Tensor:
    img = cv2.resize(img_array, (160, 160))
    img = img.astype(np.float32) / 255.0
    img = tf.expand_dims(img, axis=0)  # (1, 160, 160, 3)
    return img  # devolvemos solo el tensor


def _face_detect_and_align(img_array: np.ndarray):
    """
    Detector Haar-cascade incluido en OpenCV.
    Devuelve caras recortadas y redimensionadas a 160×160.
    """
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    rects = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )
    faces = []
    for x, y, w, h in rects:
        face = img_array[y : y + h, x : x + w]
        face = cv2.resize(face, (160, 160))
        faces.append(face)
    return faces


class FaceAlreadyRegisteredError(ValidationError):
    pass


# ------------------------------------------------------------------
# 3. API pública (misma firma que antes)
# ------------------------------------------------------------------
class FacialRecognitionService:
    @staticmethod
    def create_facial_profile(User, image: InMemoryUploadedFile):
        """Guarda el embedding de la cara principal detectada."""
        img_bytes = image.read()
        image_np = _bytes_to_array(img_bytes)
        faces = _face_detect_and_align(image_np)
        if not faces:
            return None
        embedding = facenet(_preprocess(faces[0]))[0].numpy()
        profile, _ = FacialRecognitionProfile.objects.update_or_create(
            user=User, 
            defaults={
                "face_encoding": embedding.tobytes(),
                "face_image": image,
            }
        )
        return profile

    @staticmethod
    def process_uploaded_image(image: InMemoryUploadedFile) -> np.ndarray | None:
        """Útil para EndUserRegistrationSerializer."""
        return _bytes_to_array(image.read())

    @staticmethod
    def compare_faces(stored_bytes: bytes, new_bytes: bytes, threshold=0.45):
        """
        Compara dos embeddings usando cosine similarity.
        Devuelve (match: bool, distance: float)
        """
        emb1 = np.frombuffer(stored_bytes, dtype=np.float32)
        emb2 = np.frombuffer(new_bytes, dtype=np.float32)
        dist = 1 - cosine_similarity([emb1], [emb2])[0][0]
        return dist < threshold, dist

    @staticmethod
    def login_with_face(image: InMemoryUploadedFile):
        """Devuelve el usuario si la cara coincide con algún perfil."""
        img_bytes = image.read()
        faces = _face_detect_and_align(_bytes_to_array(img_bytes))
        if not faces:
            return None
        emb = facenet(_preprocess(faces[0]))[0].numpy()

        # Búsqueda lineal (para < 1k usuarios es instantáneo)
        for profile in FacialRecognitionProfile.objects.select_related("user").all():
            match, _ = FacialRecognitionService.compare_faces(
                profile.face_encoding, emb.tobytes()
            )
            if match and profile.user.face_auth_enabled:
                return profile.user
        return None
