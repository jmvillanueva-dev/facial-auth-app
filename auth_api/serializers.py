from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from facial_auth_app.services import (
    FacialRecognitionService,
    FaceAlreadyRegisteredError,
    _bytes_to_array,
    _face_detect_and_align,
    _preprocess_for_embedding,
    embedding_model,
)
from facial_auth_app.models import FacialRecognitionProfile
from auth_api.models import ClientApp, EndUser, CustomUserLoginAttempt

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
    # Nuevo campo para forzar el registro
    force_register = serializers.BooleanField(default=False, write_only=True)

    class Meta:
        model = User
        fields = [
            "email",
            "full_name",
            "password",
            "password_conf",
            "face_image",
            "force_register",
        ]
        extra_kwargs = {"password": {"write_only": True}}

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

        face_image = data.get("face_image")
        if face_image:
            img_np = _bytes_to_array(face_image.read())
            faces = _face_detect_and_align(img_np)
            if not faces:
                raise serializers.ValidationError(
                    {
                        "face_image": "No se detectó ningún rostro en la imagen proporcionada."
                    }
                )
            face_image.seek(0)
        else:
            raise serializers.ValidationError(
                {"face_image": "Se requiere una imagen facial."}
            )

        return data

    def create(self, validated_data):
        print("DEBUG: Iniciando creación del usuario")

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
        force_register = validated_data.pop(
            "force_register", False
        )

        with transaction.atomic():
            user = User.objects.create(**validated_data)
            user.set_password(password)
            user.save()

            # Procesar la imagen para obtener el embedding
            img_np = _bytes_to_array(face_image.read())
            faces = _face_detect_and_align(img_np)
            if not faces:
                user.delete()  # Si no hay rostro, eliminar el usuario recién creado
                raise serializers.ValidationError(
                    {
                        "face_image": "No se pudo procesar la imagen facial para el perfil."
                    }
                )
            processed_face_for_embedding = _preprocess_for_embedding(faces[0])
            embedding = embedding_model(processed_face_for_embedding)[0].numpy()
            encoding_bytes = embedding.tobytes()

            # Lógica de verificación de duplicados basada en force_register
            if not force_register:
                for existing_profile in FacialRecognitionProfile.objects.filter(
                    is_active=True
                ).exclude(
                    user=user
                ):  # Excluir el usuario recién creado
                    match, _ = FacialRecognitionService.compare_faces(
                        existing_profile.face_encoding, encoding_bytes
                    )
                    if match:
                        user.delete()  # Eliminar el usuario recién creado si hay duplicado
                        raise FaceAlreadyRegisteredError(
                            "Este rostro ya está registrado por otro usuario. Si estás seguro de que eres tú, marca 'Forzar Registro'."
                        )

            FacialRecognitionProfile.objects.update_or_create(
                user=user,
                defaults={
                    "face_encoding": encoding_bytes,
                    "face_image": face_image,
                    "description": (
                        "Initial registration"
                        if not force_register
                        else "Forced registration/re-registration"
                    ),
                },
            )

            user.face_auth_enabled = True
            user.save(update_fields=["face_auth_enabled"])

        return user


class FaceLoginSerializer(serializers.Serializer):
    face_image = serializers.ImageField()


class FaceLoginFeedbackSerializer(serializers.Serializer):
    """
    Serializador para validar los datos del feedback de autenticación facial.
    """
    user_id = serializers.IntegerField(required=False)
    password = serializers.CharField(required=False)
    face_image = serializers.ImageField(
        required=False
    )  # Puede ser opcional si solo se envía feedback negativo sin nueva imagen
    login_attempt_id = serializers.IntegerField(required=True)
    feedback_decision = serializers.CharField(
        required=True
    )  # 'correcto' o 'incorrecto'

    def validate(self, data):
        feedback_decision = data.get("feedback_decision")
        user_id = data.get("user_id")
        password = data.get("password")
        face_image = data.get("face_image")

        if feedback_decision == "correcto":
            if not user_id:
                raise serializers.ValidationError(
                    {"user_id": "user_id es requerido para feedback 'correcto'."}
                )
            if not password:
                raise serializers.ValidationError(
                    {"password": "Contraseña es requerida para feedback 'correcto'."}
                )
            if not face_image:
                raise serializers.ValidationError(
                    {
                        "face_image": "Imagen de rostro es requerida para feedback 'correcto'."
                    }
                )
        elif feedback_decision == "incorrecto":
            # Para 'incorrecto', user_id y password no son necesarios,
            # pero login_attempt_id y face_image (opcionalmente) sí.
            pass
        else:
            raise serializers.ValidationError(
                {
                    "feedback_decision": "feedback_decision debe ser 'correcto' o 'incorrecto'."
                }
            )

        return data


class ClientAppSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientApp
        fields = [
            "id",
            "name",
            "description",
            "token",
            "CONFIDENCE_THRESHOLD",
            "FALLBACK_THRESHOLD",
            "created_at",
        ]
        read_only_fields = ["token", "created_at"]

    def validate(self, data):
        confidence = data.get("CONFIDENCE_THRESHOLD")
        fallback = data.get("FALLBACK_THRESHOLD")

        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise serializers.ValidationError(
                {"CONFIDENCE_THRESHOLD": "El valor debe estar entre 0.0 y 1.0."}
            )

        if fallback is not None and not (0.0 <= fallback <= 1.0):
            raise serializers.ValidationError(
                {"FALLBACK_THRESHOLD": "El valor debe estar entre 0.0 y 1.0."}
            )

        return data


class EndUserRegistrationSerializer(serializers.ModelSerializer):
    face_image = serializers.ImageField(write_only=True)
    force_register = serializers.BooleanField(default=False, write_only=True)

    class Meta:
        model = EndUser
        fields = [
            "email",
            "full_name",
            "role",
            "password",
            "face_image",
            "force_register",
        ]

    def create(self, validated_data):
        face_image = validated_data.pop("face_image")
        app = self.context.get("app")
        email = validated_data.get("email")
        force_register = validated_data.pop(
            "force_register", False
        )  # Obtener y remover force_register

        image_np = _bytes_to_array(face_image.read())

        faces = _face_detect_and_align(image_np)
        if not faces:
            raise serializers.ValidationError(
                "No se detectó ningún rostro en la imagen."
            )

        processed_face = _preprocess_for_embedding(faces[0])
        embedding = embedding_model(processed_face)[0].numpy()
        encoding_bytes = embedding.tobytes()

        existing = EndUser.objects.filter(app=app, email=email).first()
        if existing:
            if existing.deleted:
                # Si el usuario existía pero estaba "eliminado", lo reactivamos
                existing.deleted = False
                existing.full_name = validated_data.get("full_name")
                existing.role = validated_data.get("role")
                existing.face_encoding = encoding_bytes  # Actualizar encoding
                existing.password = validated_data.get(
                    "password"
                )  # O set_password si es hashed
                existing.save()
                return existing
            else:
                # Si el usuario existe y no está eliminado, y no se fuerza el registro, es un error
                if not force_register:
                    raise serializers.ValidationError(
                        "El email ya está registrado para esta aplicación. Si deseas actualizar tu rostro, marca 'Forzar Registro'."
                    )
                else:
                    # Si se fuerza el registro, actualizamos el perfil existente
                    existing.full_name = validated_data.get("full_name")
                    existing.role = validated_data.get("role")
                    existing.face_encoding = encoding_bytes  # Actualizar encoding
                    existing.password = validated_data.get(
                        "password"
                    )
                    existing.save()
                    return existing

        # Verificar duplicidad facial solo si no se fuerza el registro y el usuario es nuevo
        if not force_register:
            for end_user_in_app in app.end_users.filter(deleted=False):
                match, _ = FacialRecognitionService.compare_faces(
                    end_user_in_app.face_encoding,
                    encoding_bytes,
                    threshold=app.CONFIDENCE_THRESHOLD,
                )
                if match:
                    raise FaceAlreadyRegisteredError(
                        "Este rostro ya está registrado para esta aplicación. Si estás seguro de que no eres tú, marca 'Forzar Registro'."
                    )

        # Crear nuevo EndUser si no existe o si se forzó el registro y no había duplicado de email
        validated_data["face_encoding"] = encoding_bytes
        validated_data["app"] = app
        return EndUser.objects.create(**validated_data)


class EndUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = EndUser
        fields = ["id", "email", "full_name", "role", "created_at"]
        read_only_fields = ["id", "email", "full_name", "role", "created_at"]


class EndUserFaceFeedbackSerializer(serializers.Serializer):
    """
    Serializador para validar los datos del feedback de autenticación facial
    para los usuarios finales (EndUser) de una ClientApp.
    """
    user_id = serializers.IntegerField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True) 
    face_image = serializers.ImageField(write_only=True)

    def validate(self, data):
        face_image = data.get("face_image")
        if face_image:
            img_np = _bytes_to_array(face_image.read())
            faces = _face_detect_and_align(img_np)
            if not faces:
                raise serializers.ValidationError(
                    {"face_image": "No se detectó ningún rostro en la imagen proporcionada."}
                )
            face_image.seek(0) # Restablecer el puntero del archivo
        else:
            raise serializers.ValidationError(
                {"face_image": "Se requiere una imagen facial para el feedback."}
            )
        return data

        return data
