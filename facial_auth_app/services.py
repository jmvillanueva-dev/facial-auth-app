import os
import cv2, io, numpy as np, tensorflow as tf, tensorflow_hub as hub
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import FacialRecognitionProfile

print("DEBUG: Starting import of services.py")


User = get_user_model()

MODEL_DIR = os.path.abspath("tf_models")
os.environ["TFHUB_CACHE_DIR"] = MODEL_DIR  

# ------------------------------------------------------------------
# 1. Cargar modelos una sola vez al arrancar Django
# ------------------------------------------------------------------
print("DEBUG: About to load face_detector model.")
try:
    face_detector = hub.load(
        "https://tfhub.dev/tensorflow/faster_rcnn/resnet101_v1_640x640/1"
    )
    print("DEBUG: face_detector model loaded successfully.")
except Exception as e:
    print(f"ERROR: Failed to load face_detector model. Exception: {e}")

print("DEBUG: About to load embedding_model.")
try:
    embedding_model = hub.load(
        "https://tfhub.dev/google/imagenet/inception_resnet_v2/feature_vector/4"
    )
    print("DEBUG: embedding_model loaded successfully.")
except Exception as e:
    print(f"ERROR: Failed to load embedding_model. Exception: {e}")

EMBEDDING_DIM = 1536
# ------------------------------------------------------------------
# 2. Utils
# ------------------------------------------------------------------
def _bytes_to_array(img_bytes: bytes) -> np.ndarray:
    """Convierte bytes crudos a RGB array."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


def _preprocess_for_detection(img_array: np.ndarray) -> tf.Tensor:
    """
    Preprocesa la imagen para el modelo de detección (Faster R-CNN).
    Esperará una imagen redimensionada a 640x640 y valores en [0, 255] (dtype=uint8).
    """
    img = cv2.resize(img_array, (640, 640))
    # img = img.astype(np.float32) # ¡Esta línea ya la eliminaste!
    img = tf.expand_dims(img, axis=0)
    return img


def _preprocess_for_embedding(img_array: np.ndarray) -> tf.Tensor:
    """
    Preprocesa la imagen para el modelo de embedding (InceptionResNetV2).
    Espera una imagen redimensionada a 299x299 y valores en [-1, 1].
    """
    img = cv2.resize(img_array, (299, 299))
    # CORRECCIÓN: Normalizar de [0, 255] a [-1, 1] para InceptionResNetV2
    img = (
        img.astype(np.float32) / 127.5 - 1.0
    )  # <-- ¡Línea corregida para rango [-1, 1]!
    img = tf.expand_dims(img, axis=0)
    return img


def _face_detect_and_align(img_array: np.ndarray):
    """
    Detecta caras usando el modelo `face_detector`.
    Devuelve los rostros recortados.
    """
    preprocessed_img = _preprocess_for_detection(img_array)

    detections = face_detector(preprocessed_img)

    # Es crucial que estas claves existan en la salida del modelo
    if "detection_boxes" not in detections or "detection_scores" not in detections:
        # Podrías loggear esto para depuración
        # print("Advertencia: Claves 'detection_boxes' o 'detection_scores' no encontradas en la salida del detector.")
        return []

    boxes = detections["detection_boxes"][0].numpy()
    scores = detections["detection_scores"][0].numpy()

    faces = []
    for i in range(len(scores)):
        if scores[i] > 0.5:  # Umbral de confianza para la detección
            ymin, xmin, ymax, xmax = boxes[i]

            h, w, _ = img_array.shape
            left, right, top, bottom = (
                int(xmin * w),
                int(xmax * w),
                int(ymin * h),
                int(ymax * h),
            )

            # Aseguramos que las coordenadas estén dentro de los límites de la imagen
            left, top = max(0, left), max(0, top)
            right, bottom = min(w, right), min(h, bottom)

            # Verificar si las dimensiones de recorte son válidas para evitar errores con cv2
            if bottom <= top or right <= left:
                continue  # Saltar esta detección si las dimensiones son inválidas

            face = img_array[top:bottom, left:right]

            if (
                face.shape[0] > 0 and face.shape[1] > 0
            ):  # Asegurar que la cara no esté vacía
                faces.append(face)

    return faces


class FaceAlreadyRegisteredError(ValidationError):
    pass


# ------------------------------------------------------------------
# 3. API pública
# ------------------------------------------------------------------
class FacialRecognitionService:
    DEFAULT_THRESHOLD = 0.18

    @staticmethod
    def create_facial_profile(user_instance, image: InMemoryUploadedFile):
        """Guarda el embedding de la cara principal detectada."""
        img_bytes = image.read()
        image_np = _bytes_to_array(img_bytes)

        faces = _face_detect_and_align(image_np)

        if not faces:
            return None

        processed_face_for_embedding = _preprocess_for_embedding(faces[0])

        embedding = embedding_model(processed_face_for_embedding)[0].numpy()

        profile, created = FacialRecognitionProfile.objects.update_or_create(
            user=user_instance,
            defaults={
                "face_encoding": embedding.tobytes(),
                "face_image": image,
            },
        )
        return profile

    @staticmethod
    def process_uploaded_image(image: InMemoryUploadedFile) -> np.ndarray | None:
        return _bytes_to_array(image.read())

    @staticmethod
    def compare_faces(stored_bytes: bytes, new_bytes: bytes, threshold=None):
        threshold = threshold or FacialRecognitionService.DEFAULT_THRESHOLD

        emb1 = np.frombuffer(stored_bytes, dtype=np.float32)
        emb2 = np.frombuffer(new_bytes, dtype=np.float32)

        # La normalización ya se hace, lo cual es correcto para cosine_similarity
        # Asegúrate de que los embeddings sean unitarios para que la similitud coseno
        # represente la distancia angular.
        if np.linalg.norm(emb1) > 0:  # Evitar división por cero
            emb1 = emb1 / np.linalg.norm(emb1)
        if np.linalg.norm(emb2) > 0:  # Evitar división por cero
            emb2 = emb2 / np.linalg.norm(emb2)

        dist = 1 - cosine_similarity([emb1], [emb2])[0][0]

        return dist < threshold, dist

    @staticmethod
    def login_with_face(image: InMemoryUploadedFile):
        """Devuelve el usuario si la cara coincide con algún perfil."""
        img_bytes = image.read()
        image_np = _bytes_to_array(img_bytes)

        faces = _face_detect_and_align(image_np)

        if not faces:
            return None

        processed_face_for_embedding = _preprocess_for_embedding(faces[0])

        emb = embedding_model(processed_face_for_embedding)[0].numpy()

        for profile in FacialRecognitionProfile.objects.select_related("user").all():
            match, _ = FacialRecognitionService.compare_faces(
                profile.face_encoding, emb.tobytes()
            )
            if match and profile.user.face_auth_enabled:
                return profile.user
        return None

print("DEBUG: services.py module loaded completely.")
