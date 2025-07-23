import face_recognition
import numpy as np
import cv2
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.exceptions import ValidationError
from io import BytesIO
from PIL import Image
from .models import FacialRecognitionProfile


class FaceAlreadyRegisteredError(ValidationError):
    pass


class FacialRecognitionService:
    @staticmethod
    def convert_to_face_encoding(image_path):
        """Convert image to face encoding"""
        try:
            image = face_recognition.load_image_file(image_path)
            face_encodings = face_recognition.face_encodings(image)
            if len(face_encodings) > 0:
                return face_encodings[0].tobytes()
            return None
        except Exception as e:
            print(f"Error in face encoding: {str(e)}")
            return None

    @staticmethod
    def compare_faces(known_encoding_bytes, unknown_encoding_bytes, tolerance=0.6):
        """Compare two face encodings"""
        try:
            known_encoding = np.frombuffer(known_encoding_bytes, dtype=np.float64)
            unknown_encoding = np.frombuffer(unknown_encoding_bytes, dtype=np.float64)

            result = face_recognition.compare_faces(
                [known_encoding], unknown_encoding, tolerance=tolerance
            )
            distance = face_recognition.face_distance(
                [known_encoding], unknown_encoding
            )
            return result[0], distance[0]
        except Exception as e:
            print(f"Error in face comparison: {str(e)}")
            return False, None

    @staticmethod
    def process_uploaded_image(uploaded_file):
        """Process uploaded image file"""
        try:
            # Convert InMemoryUploadedFile to PIL Image
            pil_image = Image.open(uploaded_file)

            # Convert to RGB if necessary
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Convert to numpy array
            image_np = np.array(pil_image)

            # Convert BGR to RGB (if needed)
            if image_np.shape[2] == 3:  # Color image
                image_np = cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB)

            return image_np
        except Exception as e:
            print(f"Error processing image: {str(e)}")
            return None

    @staticmethod
    def create_facial_profile(user, image_file):
        """Create facial recognition profile for FaceAuth users"""
        try:
            # Save the image file temporarily
            image_np = FacialRecognitionService.process_uploaded_image(image_file)
            if image_np is None:
                return None

            # Get face encoding
            face_encodings = face_recognition.face_encodings(image_np)
            if not face_encodings:
                return None

            encoding_bytes = face_encodings[0].tobytes()

            for profile in FacialRecognitionProfile.objects.filter(is_active=True):
                match, _ = FacialRecognitionService.compare_faces(profile.face_encoding, encoding_bytes)
                if match:
                    raise FaceAlreadyRegisteredError(
                        "Este rostro ya está registrado en nuestro sistema. "
                        "Cada usuario debe tener un rostro único."
                    )

            # Create profile
            profile = FacialRecognitionProfile.objects.create(
                user=user, face_encoding=face_encodings[0].tobytes()
            )

            # Save the image
            buffer = BytesIO()
            img_pil = Image.fromarray(cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))
            img_pil.save(buffer, format="JPEG")
            profile.face_image.save(
                f"{user.username}_face.jpg",
                InMemoryUploadedFile(
                    buffer,
                    None,
                    f"{user.username}_face.jpg",
                    "image/jpeg",
                    buffer.tell,
                    None,
                ),
            )

            return profile
        except FaceAlreadyRegisteredError as e:
            raise
        except Exception as e:
            print(f"Error creating facial profile: {str(e)}")
            return None
        
    @staticmethod
    def create_facial_profile_endusers(user, image_file):
        """Create facial recognition profile for ClientApp users"""
        try:
            # Save the image file temporarily
            image_np = FacialRecognitionService.process_uploaded_image(image_file)
            if image_np is None:
                return None

            # Get face encoding
            face_encodings = face_recognition.face_encodings(image_np)
            if not face_encodings:
                return None

            encoding_bytes = face_encodings[0].tobytes()

            for profile in FacialRecognitionProfile.objects.filter(is_active=True):
                match, _ = FacialRecognitionService.compare_faces(profile.face_encoding, encoding_bytes)
                if match:
                    raise FaceAlreadyRegisteredError(
                        "Este rostro ya está registrado en nuestro sistema. "
                        "Cada usuario debe tener un rostro único."
                    )

            # Create profile
            profile = FacialRecognitionProfile.objects.create(
                user=user, face_encoding=face_encodings[0].tobytes()
            )

            # Save the image
            buffer = BytesIO()
            img_pil = Image.fromarray(cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))
            img_pil.save(buffer, format="JPEG")
            profile.face_image.save(
                f"{user.username}_face.jpg",
                InMemoryUploadedFile(
                    buffer,
                    None,
                    f"{user.username}_face.jpg",
                    "image/jpeg",
                    buffer.tell,
                    None,
                ),
            )

            return profile
        except FaceAlreadyRegisteredError as e:
            raise
        except Exception as e:
            print(f"Error creating facial profile: {str(e)}")
            return None