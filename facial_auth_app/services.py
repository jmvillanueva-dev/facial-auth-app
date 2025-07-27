import os
import cv2, io, numpy as np, tensorflow as tf, tensorflow_hub as hub
from PIL import Image
from sklearn.metrics.pairwise import cosine_similarity
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import FacialRecognitionProfile, FaceFeedback

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
    img = (img.astype(np.float32) / 127.5 - 1.0)
    img = tf.expand_dims(img, axis=0)
    return img


def _face_detect_and_align(img_array: np.ndarray):
    """
    Detecta caras usando el modelo `face_detector`.
    Devuelve los rostros recortados.
    """
    preprocessed_img = _preprocess_for_detection(img_array)
    detections = face_detector(preprocessed_img)

    if "detection_boxes" not in detections or "detection_scores" not in detections:
        return []

    boxes = detections["detection_boxes"][0].numpy()
    scores = detections["detection_scores"][0].numpy()

    faces = []
    for i in range(len(scores)):
        if scores[i] > 0.5:
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
                continue

            face = img_array[top:bottom, left:right]
            if (face.shape[0] > 0 and face.shape[1] > 0):
                faces.append(face)

    return faces


class FaceAlreadyRegisteredError(ValidationError):
    pass


# ------------------------------------------------------------------
# 3. API pública
# ------------------------------------------------------------------
class FacialRecognitionService:
    # Umbral de distancia para detectar una coincidencia.
    # Por ejemplo, 0.18 significa que 1 - 0.18 = 0.82 de similitud (82%)
    CONFIDENCE_THRESHOLD = 0.18
    # Umbral de distancia para una posible coincidencia (más permisivo)
    FALLBACK_THRESHOLD = 0.20

    @staticmethod
    def create_facial_profile(user_instance, image: InMemoryUploadedFile):
        """Crea el primer embedding de cara para un nuevo usuario."""
        img_bytes = image.read()
        image_np = _bytes_to_array(img_bytes)

        faces = _face_detect_and_align(image_np)
        if not faces:
            return None

        processed_face_for_embedding = _preprocess_for_embedding(faces[0])
        embedding = embedding_model(processed_face_for_embedding)[0].numpy()
        profile = FacialRecognitionProfile.objects.create(
            user=user_instance,
            face_encoding=embedding.tobytes(),
            face_image=image,
            description="Initial registration",  # <--- Usamos el nuevo campo
        )
        return profile

    @staticmethod
    def process_and_store_feedback(user_instance, image: InMemoryUploadedFile):
        """
        Procesa y guarda la imagen de feedback como un nuevo perfil
        para mejorar inmediatamente el sistema.
        """
        img_bytes = image.read()
        image_np = _bytes_to_array(img_bytes)

        faces = _face_detect_and_align(image_np)
        if not faces:
            return False

        processed_face_for_embedding = _preprocess_for_embedding(faces[0])
        new_embedding = embedding_model(processed_face_for_embedding)[0].numpy()

        # Guarda la imagen de feedback
        FaceFeedback.objects.create(user=user_instance, submitted_image=image)

        # Crea un nuevo perfil facial para el usuario con el embedding de la imagen de feedback.
        # Esto mejora inmediatamente la precisión para este usuario.
        FacialRecognitionProfile.objects.create(
            user=user_instance,
            face_encoding=new_embedding.tobytes(),
            face_image=image,
            description="Feedback from ambiguous match",
        )

        return True

    @staticmethod
    def process_uploaded_image(image: InMemoryUploadedFile) -> np.ndarray | None:
        return _bytes_to_array(image.read())

    @staticmethod
    def compare_faces(stored_bytes: bytes, new_bytes: bytes, threshold=None):
        threshold = threshold or FacialRecognitionService.CONFIDENCE_THRESHOLD

        emb1 = np.frombuffer(stored_bytes, dtype=np.float32)
        emb2 = np.frombuffer(new_bytes, dtype=np.float32)

        if np.linalg.norm(emb1) > 0:
            emb1 = emb1 / np.linalg.norm(emb1)
        if np.linalg.norm(emb2) > 0: 
            emb2 = emb2 / np.linalg.norm(emb2)

        dist = 1 - cosine_similarity([emb1], [emb2])[0][0]
        return dist < threshold, dist

    @staticmethod
    def login_with_face(image: InMemoryUploadedFile):
        """
        Devuelve un diccionario con el estado del login.
        - 'success': si encuentra una coincidencia con alta confianza.
        - 'ambiguous_match': si encuentra una o más coincidencias posibles que requieren confirmación.
        - 'no_match': si no encuentra ninguna coincidencia.
        """
        img_bytes = image.read()
        image_np = _bytes_to_array(img_bytes)
        faces = _face_detect_and_align(image_np)

        if not faces:
            return {"status": "no_match"}

        processed_face_for_embedding = _preprocess_for_embedding(faces[0])
        emb = embedding_model(processed_face_for_embedding)[0].numpy()

        all_profiles = FacialRecognitionProfile.objects.select_related("user").filter(
            user__face_auth_enabled=True
        )

        matches_by_user = {}
        for profile in all_profiles:
            # Comparamos el embedding de la imagen con CADA uno de los perfiles guardados
            match, dist = FacialRecognitionService.compare_faces(
                profile.face_encoding,
                emb.tobytes(),
                threshold=FacialRecognitionService.FALLBACK_THRESHOLD,
            )
            if match:
                user_id = profile.user.id
                if (
                    user_id not in matches_by_user
                    or dist < matches_by_user[user_id]["distance"]
                ):
                    matches_by_user[user_id] = {"user": profile.user, "distance": dist}

        if not matches_by_user:
            return {"status": "no_match"}

        matches = sorted(matches_by_user.values(), key=lambda x: x["distance"])
        best_match = matches[0]

        if best_match["distance"] <= FacialRecognitionService.CONFIDENCE_THRESHOLD:
            return {"status": "success", "user": best_match["user"]}

        ambiguous_matches = [
            {
                "id": m["user"].id,
                "full_name": m["user"].full_name,
                "distance": m["distance"],
            }
            for m in matches
        ]
        return {"status": "ambiguous_match", "matches": ambiguous_matches}

print("DEBUG: services.py module loaded completely.")
