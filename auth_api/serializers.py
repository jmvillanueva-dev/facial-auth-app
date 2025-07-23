from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from facial_auth_app.services import (
    FacialRecognitionService,
    FaceAlreadyRegisteredError,
)
from auth_api.models import ClientApp, EndUser
import face_recognition

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "face_auth_enabled",
            "date_joined",
        ]
        read_only_fields = ["id", "face_auth_enabled", "date_joined"]


class RegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="Lo sentimos, email ingresado ya está registrado",
            )
        ]
    )

    password_conf = serializers.CharField(write_only=True)
    face_image = serializers.ImageField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "full_name",
            "password",
            "password_conf",
            "face_image",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
        }

    # ----- password validation -----
    def validate(self, data):
        try:
            validate_password(data["password"])
        except ValidationError as e:
            password_errors = []
            for error in e.messages:
                if (
                    error
                    == "This password is too short. It must contain at least 8 characters."
                ):
                    password_errors.append(
                        "La contraseña debe tener mínimo 8 caracteres."
                    )
                elif error == "This password is too common.":
                    password_errors.append(
                        "Por seguridad, elige una contraseña menos común."
                    )
                elif error == "This password is entirely numeric.":
                    password_errors.append("La contraseña no puede ser solo numérica.")
                else:
                    password_errors.append(error)

            raise serializers.ValidationError({"password": password_errors})

        return data

    # ----- create user + facial profile atomically -----
    def create(self, validated_data):
        from facial_auth_app.services import FacialRecognitionService
        from django.db import transaction

        # Genera username único a partir del email
        base_username = validated_data["email"].split("@")[0]
        username = base_username
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        validated_data["username"] = username

        face_image = validated_data.pop("face_image")
        validated_data.pop("password_conf")
        password = validated_data.pop("password")

        with transaction.atomic():
            user = User.objects.create(
                **validated_data,
            )
            user.set_password(password)
            user.save()

            profile = FacialRecognitionService.create_facial_profile(user, face_image)
            if not profile:
                raise serializers.ValidationError(
                    {"face_image": "Could not process face image"}
                )

            user.face_auth_enabled = True
            user.save(update_fields=["face_auth_enabled"])

        return user


class FaceLoginSerializer(serializers.Serializer):
    face_image = serializers.ImageField()


class ClientAppSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientApp
        fields = ["id", "name", "description", "token", "strictness", "created_at"]
        read_only_fields = ["token", "created_at"]


class EndUserRegistrationSerializer(serializers.ModelSerializer):
    face_image = serializers.ImageField(write_only=True)

    class Meta:
        model = EndUser
        fields = ["email", "full_name", "role", "password", "face_image"]

    def create(self, validated_data):
        face_image = validated_data.pop("face_image")
        app = self.context.get("app")
        email = validated_data.get("email")

        # Procesar imagen
        image_np = FacialRecognitionService.process_uploaded_image(face_image)
        if image_np is None:
            raise serializers.ValidationError("No se pudo procesar la imagen.")

        face_encodings = face_recognition.face_encodings(image_np)
        if not face_encodings:
            raise serializers.ValidationError("No se detectó ningún rostro.")

        encoding_bytes = face_encodings[0].tobytes()

        # Verificar si el usuario existe y está eliminado

        existing = EndUser.objects.filter(app=app, email=email).first()
        if existing:
            if existing.deleted:
                # Reactivar usuario
                existing.deleted = False
                existing.full_name = validated_data.get("full_name")
                existing.role = validated_data.get("role")
                existing.face_encoding = encoding_bytes
                existing.password = validated_data.get("password")
                existing.save()
                return existing
            else:
                raise serializers.ValidationError("El email ya está registrado.")

        # Verificar duplicidad facial solo entre usuarios no eliminados
        for end_user in app.end_users.filter(deleted=False):
            match, _ = FacialRecognitionService.compare_faces(
                end_user.face_encoding, encoding_bytes
            )
            if match:
                raise FaceAlreadyRegisteredError(
                    "Este rostro ya está registrado para esta aplicación."
                )

        # Crear nuevo usuario
        validated_data["face_encoding"] = encoding_bytes
        validated_data["app"] = app
        return EndUser.objects.create(**validated_data)

