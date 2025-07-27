from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics, serializers as drf_serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import render
from django.contrib.auth import authenticate, get_user_model
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
# from facial_auth_app.models import FacialRecognitionProfile
from auth_api.models import ClientApp, EndUser, EndUserFeedback, EndUserLoginAttempt, CustomUserLoginAttempt
from auth_api.serializers import (
    UserSerializer,
    RegistrationSerializer,
    FaceLoginSerializer,
    ClientAppSerializer,
    EndUserRegistrationSerializer,
    FaceLoginFeedbackSerializer,
    EndUserSerializer,
    EndUserFaceFeedbackSerializer,
)

User = get_user_model()

def home(request):
    return render(request, "home.html")


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        force_register = request.data.get("force_register", "false").lower() == "true"
        serializer = RegistrationSerializer(
            data=request.data, context={"force_register": force_register}
        )
        try:
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            tokens = get_tokens_for_user(user)
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Usuario registrado exitosamente",
                },
                status=status.HTTP_201_CREATED,
            )

        except drf_serializers.ValidationError as e:
            errors = {
                field: (
                    error_list[0] if isinstance(error_list, list) else str(error_list)
                )
                for field, error_list in e.detail.items()
            }
            return Response(
                {"errors": errors, "message": "Error en los datos de registro"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except FaceAlreadyRegisteredError as e:
            return Response(
                {
                    "errors": {"face_image": str(e)},
                    "message": "Error en el registro facial",
                    "detail": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {
                    "errors": {"non_field_errors": str(e)},
                    "message": "Error en el servidor",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        user = authenticate(username=username, password=password)
        if not user:
            return Response(
                {"detail": "Verifica tus credenciales"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        tokens = get_tokens_for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": tokens,
                "message": "Inicio de sesión exitoso",
            }
        )


class FaceLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = FaceLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image_file = request.FILES.get("face_image")

        # Crear un registro de intento de login para CustomUser
        # El campo 'user' puede ser nulo inicialmente si el usuario no está autenticado
        login_attempt = CustomUserLoginAttempt.objects.create(
            user=request.user if request.user.is_authenticated else None,
            initial_status="error",  # Default a error, se actualizará
        )
        login_attempt.submitted_image = image_file
        login_attempt.save()  # Guardar para que la imagen se suba

        image_file.seek(0)  # Resetear el puntero del archivo después de guardarlo

        try:
            image_np = _bytes_to_array(image_file.read())
            faces = _face_detect_and_align(image_np)

            if not faces:
                login_attempt.initial_status = "no_match"
                login_attempt.save()
                return Response(
                    {"detail": "No se detectó ningún rostro en la imagen."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            processed_face = _preprocess_for_embedding(faces[0])
            emb = embedding_model(processed_face)[0].numpy()
            unknown = emb.tobytes()

            matches_by_user = {}
            # FILTRO CLAVE: Obtener solo usuarios que tienen autenticación facial habilitada
            # y al menos un perfil de reconocimiento facial con un encoding no nulo.
            # Usamos 'facial_profiles' que es el related_name de la ForeignKey.
            users_with_face_auth = User.objects.filter(
                face_auth_enabled=True,
                facial_profiles__face_encoding__isnull=False,  # Usar el related_name correcto
            ).distinct()  # Usar distinct para evitar usuarios duplicados si tienen múltiples perfiles

            if not users_with_face_auth.exists():
                login_attempt.initial_status = "no_match"
                login_attempt.save()
                return Response(
                    {
                        "detail": "No hay usuarios con autenticación facial habilitada o rostros registrados."
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Iterar a través de cada usuario y sus múltiples perfiles faciales
            for user_obj in users_with_face_auth:
                # Obtener todos los perfiles faciales activos para el usuario actual
                # Asegúrate de que 'is_active' exista en tu modelo FacialRecognitionProfile
                user_profiles = user_obj.facial_profiles.filter(
                    is_active=True, face_encoding__isnull=False
                )

                for profile in user_profiles:
                    face_encoding = profile.face_encoding

                    match, dist = FacialRecognitionService.compare_faces(
                        face_encoding,
                        unknown,
                        threshold=0.25,  # Umbral genérico para CustomUser o definir uno en CustomUser
                    )
                    if match:
                        user_id = user_obj.id
                        # Si este usuario ya es una posible coincidencia, mantenemos la mejor (distancia más pequeña)
                        if (
                            user_id not in matches_by_user
                            or dist < matches_by_user[user_id]["distance"]
                        ):
                            matches_by_user[user_id] = {
                                "user": user_obj,
                                "distance": dist,
                            }

            if not matches_by_user:
                login_attempt.initial_status = "no_match"
                login_attempt.save()
                return Response(
                    {"detail": "Rostro no reconocido para ningún usuario del sistema."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            matches = sorted(matches_by_user.values(), key=lambda x: x["distance"])
            best_match = matches[0]

            login_attempt.best_match_user = best_match["user"]
            login_attempt.best_match_distance = best_match["distance"]

            # Definir umbrales para CustomUser (pueden ser fijos o configurables)
            CUSTOMUSER_CONFIDENCE_THRESHOLD = 0.18
            # CUSTOMUSER_FALLBACK_THRESHOLD = 0.25 # Ya usado en el filtro de umbral

            if best_match["distance"] <= CUSTOMUSER_CONFIDENCE_THRESHOLD:
                login_attempt.initial_status = "success"
                # is_verified_and_correct se establecerá a True solo después del feedback 'correcto'
                login_attempt.save()

                user_data = UserSerializer(best_match["user"]).data
                tokens = get_tokens_for_user(best_match["user"])

                return Response(
                    {
                        "status": "success",
                        "user": user_data,
                        "tokens": tokens,
                        "message": "Ingreso facial exitoso. Por favor, confirma tu identidad.",
                        "confidence": round(1 - best_match["distance"], 3),
                        "login_attempt_id": login_attempt.id,  # Devolver el ID del intento
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                login_attempt.initial_status = "ambiguous_match"
                login_attempt.save()
                ambiguous_matches = [
                    {
                        "id": m["user"].id,
                        "username": m["user"].username,
                        "full_name": m["user"].full_name,
                        "distance": m["distance"],
                    }
                    for m in matches
                ]
                return Response(
                    {
                        "status": "ambiguous_match",
                        "matches": ambiguous_matches,
                        "detail": "Múltiples coincidencias, se requiere confirmación del usuario.",
                        "login_attempt_id": login_attempt.id,  # Devolver el ID del intento
                    },
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            import traceback

            traceback.print_exc()
            login_attempt.initial_status = "error"
            login_attempt.save()
            return Response(
                {"detail": f"Error interno del servidor: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FaceLoginFeedbackView(APIView):
    """
    Endpoint para manejar la retroalimentación del usuario del sistema principal (CustomUser).
    Recibe la imagen, el ID del usuario real y la decisión de feedback.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = FaceLoginFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login_attempt_id = serializer.validated_data.get("login_attempt_id")
        feedback_decision = serializer.validated_data.get("feedback_decision")
        user_id = serializer.validated_data.get("user_id")
        password = serializer.validated_data.get("password")
        face_image = request.FILES.get(
            "face_image"
        )  # Usar request.FILES para la imagen

        try:
            login_attempt = CustomUserLoginAttempt.objects.get(id=login_attempt_id)
        except CustomUserLoginAttempt.DoesNotExist:
            return Response(
                {"detail": "Intento de login no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            if feedback_decision == "incorrecto":
                login_attempt.user_feedback = "incorrecto"
                login_attempt.is_verified_and_correct = False
                login_attempt.save()
                return Response(
                    {"message": "Feedback de 'incorrecto' registrado."},
                    status=status.HTTP_200_OK,
                )

            # Si feedback_decision es 'correcto', user_id, password y face_image son obligatorios
            # (validado por el serializer)
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"detail": "Usuario no encontrado."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not user.check_password(password):
                return Response(
                    {"detail": "Contraseña incorrecta."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Procesar y almacenar feedback para CustomUser
            success = FacialRecognitionService.process_and_store_feedback(
                user, face_image
            )

            if not success:
                return Response(
                    {"detail": "No se detectó un rostro en la imagen de feedback."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            login_attempt.confirmed_by_feedback = user
            login_attempt.user = user  # Establecer el usuario real que intentó
            login_attempt.user_feedback = "correcto"
            login_attempt.is_verified_and_correct = True
            login_attempt.save()

            tokens = get_tokens_for_user(user)
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Verificación exitosa, bienvenido. Gracias por tu feedback.",
                },
                status=status.HTTP_200_OK,
            )


# -----------------------------
# ClientApp CRUD
# -----------------------------
class ClientAppCreateView(generics.CreateAPIView):
    queryset = ClientApp.objects.all()
    serializer_class = ClientAppSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ClientAppListView(generics.ListAPIView):
    serializer_class = ClientAppSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ClientApp.objects.filter(owner=self.request.user)


class ClientAppUpdateView(generics.UpdateAPIView):
    serializer_class = ClientAppSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return ClientApp.objects.filter(owner=self.request.user)


class ClientAppDeleteView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return ClientApp.objects.filter(owner=self.request.user)


# -----------------------------
# EndUsers
# -----------------------------
class EndUserRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, app_token):
        try:
            app = ClientApp.objects.get(token=app_token)
        except ClientApp.DoesNotExist:
            return Response(
                {"detail": "Token inválido"}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = EndUserRegistrationSerializer(
            data=request.data, context={"app": app}
        )
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                {"message": "Usuario registrado exitosamente"},
                status=status.HTTP_201_CREATED,
            )
        except FaceAlreadyRegisteredError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except drf_serializers.ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {"detail": "Ocurrió un error inesperado al registrar el usuario."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EndUserFaceLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, app_token):
        try:
            app = ClientApp.objects.get(token=app_token)
        except ClientApp.DoesNotExist:
            return Response(
                {"detail": "Token inválido"}, status=status.HTTP_403_FORBIDDEN
            )

        image = request.FILES.get("face_image")
        if not image:
            return Response(
                {"detail": "Imagen requerida"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Crear un registro de intento de login. Se usará el ID para el feedback.
        login_attempt = EndUserLoginAttempt.objects.create(
            app=app, initial_status="error"  # Default a error, se actualizará
        )
        # Guardar la imagen en el modelo de intento de login
        login_attempt.submitted_image = image
        login_attempt.save()

        image.seek(0)

        try:
            image_np = _bytes_to_array(image.read())
            faces = _face_detect_and_align(image_np)

            # ... (Lógica de detección de rostros y preprocesamiento se mantiene igual)

            if not faces:
                login_attempt.initial_status = "no_match"
                login_attempt.save()
                return Response(
                    {"detail": "No se detectó ningún rostro en la imagen."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            processed_face = _preprocess_for_embedding(faces[0])
            emb = embedding_model(processed_face)[0].numpy()
            unknown = emb.tobytes()

            matches_by_user = {}
            for user in app.end_users.filter(deleted=False):
                match, dist = FacialRecognitionService.compare_faces(
                    user.face_encoding,
                    unknown,
                    threshold=app.FALLBACK_THRESHOLD,
                )
                if match:
                    user_id = user.id
                    if (
                        user_id not in matches_by_user
                        or dist < matches_by_user[user_id]["distance"]
                    ):
                        matches_by_user[user_id] = {"user": user, "distance": dist}

            if not matches_by_user:
                login_attempt.initial_status = "no_match"
                login_attempt.save()
                return Response(
                    {"detail": "Rostro no reconocido"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            matches = sorted(matches_by_user.values(), key=lambda x: x["distance"])
            best_match = matches[0]

            login_attempt.best_match_user = best_match["user"]
            login_attempt.best_match_distance = best_match["distance"]

            if best_match["distance"] <= app.CONFIDENCE_THRESHOLD:
                # Si hay un match de alta confianza, se registra como intento 'success'.
                # La verificación final y el campo 'is_verified_and_correct'
                # se actualizarán con el feedback del usuario.
                login_attempt.initial_status = "success"
                login_attempt.save()
                return Response(
                    {
                        "status": "success",
                        "user": EndUserSerializer(best_match["user"]).data,
                        "message": "Ingreso facial exitoso. ¿Es usted?",
                        "confidence": round(1 - best_match["distance"], 3),
                        "login_attempt_id": login_attempt.id,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                # El resto de la lógica para 'ambiguous_match' se mantiene igual
                login_attempt.initial_status = "ambiguous_match"
                login_attempt.save()
                ambiguous_matches = [
                    {
                        "id": m["user"].id,
                        "full_name": m["user"].full_name,
                        "distance": m["distance"],
                    }
                    for m in matches
                ]
                return Response(
                    {
                        "status": "ambiguous_match",
                        "matches": ambiguous_matches,
                        "detail": "Múltiples coincidencias, se requiere confirmación del usuario.",
                        "login_attempt_id": login_attempt.id,
                    },
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            # ... (Manejo de errores se mantiene igual)

            import traceback

            traceback.print_exc()
            login_attempt.initial_status = "error"
            login_attempt.save()
            return Response(
                {"detail": f"Error interno del servidor: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EndUserFaceFeedbackView(APIView):
    """
    Endpoint para manejar la retroalimentación de los usuarios finales (EndUser)
    de una ClientApp.
    Ahora también se procesa el feedback sobre un intento de login incorrecto.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, app_token):
        login_attempt_id = request.data.get("login_attempt_id")
        feedback_decision = request.data.get(
            "feedback_decision"
        )  # 'correcto' o 'incorrecto'

        # Validar que los campos esenciales para cualquier feedback estén presentes
        if not login_attempt_id:
            return Response(
                {"detail": "login_attempt_id es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if feedback_decision not in ["correcto", "incorrecto"]:
            return Response(
                {"detail": "feedback_decision debe ser 'correcto' o 'incorrecto'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            app = ClientApp.objects.get(token=app_token)
        except ClientApp.DoesNotExist:
            return Response(
                {"detail": "Token de aplicación inválido"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            login_attempt = EndUserLoginAttempt.objects.get(
                id=login_attempt_id, app=app
            )
        except EndUserLoginAttempt.DoesNotExist:
            return Response(
                {
                    "detail": "Intento de login no encontrado o no pertenece a esta aplicación."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- Lógica para manejar el feedback 'incorrecto' ---
        if feedback_decision == "incorrecto":
            with transaction.atomic():
                login_attempt.user_feedback = "incorrecto"
                login_attempt.is_verified_and_correct = (
                    False  # Marcar como falso positivo/negativo corregido
                )
                login_attempt.save()
            return Response(
                {"message": "Feedback de 'incorrecto' registrado. Intente nuevamente."},
                status=status.HTTP_200_OK,
            )

        # --- Lógica para manejar el feedback 'correcto' ---
        # Si el feedback es 'correcto', entonces 'user_id' y 'password' son obligatorios
        user_id = request.data.get("user_id")
        password = request.data.get("password")
        face_image = request.FILES.get(
            "face_image"
        )  # La imagen es necesaria para actualizar el embedding

        if not user_id:
            return Response(
                {"detail": "user_id es requerido para feedback 'correcto'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not password:
            return Response(
                {"detail": "Contraseña es requerida para feedback 'correcto'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not face_image:
            return Response(
                {"detail": "Imagen de rostro es requerida para feedback 'correcto'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            end_user = EndUser.objects.get(id=user_id, app=app)
        except EndUser.DoesNotExist:
            return Response(
                {"detail": "Usuario final no encontrado para esta aplicación."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Lógica de verificación de contraseña del EndUser
        if end_user.password:  # Si el usuario tiene contraseña configurada
            if not end_user.password == password:  # Comparación directa para el EndUser
                return Response(
                    {"detail": "Contraseña incorrecta para el usuario final."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        else:  # Si el usuario no tiene contraseña configurada, y se envió una, es un error
            if password:
                return Response(
                    {
                        "detail": "Este usuario final no requiere contraseña para confirmación."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            img_np = _bytes_to_array(face_image.read())
            faces = _face_detect_and_align(img_np)

            if not faces:
                return Response(
                    {"detail": "No se detectó un rostro en la imagen de feedback."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            processed_face_for_embedding = _preprocess_for_embedding(faces[0])
            new_embedding = embedding_model(processed_face_for_embedding)[0].numpy()

            end_user.face_encoding = new_embedding.tobytes()
            end_user.save(update_fields=["face_encoding"])

            EndUserFeedback.objects.create(
                end_user=end_user,
                app=app,
                submitted_image=face_image,
                feedback_type="confirmed_login",
            )

            # Actualizar el registro de intento de login
            login_attempt.confirmed_by_feedback = end_user
            login_attempt.attempting_end_user = end_user
            login_attempt.user_feedback = "correcto"
            login_attempt.is_verified_and_correct = True
            login_attempt.save()

            return Response(
                {
                    "user": EndUserSerializer(end_user).data,
                    "message": "Feedback procesado y perfil de usuario final actualizado.",
                },
                status=status.HTTP_200_OK,
            )


class EndUserListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, app_id):
        try:
            app = ClientApp.objects.get(id=app_id, owner=request.user)
        except ClientApp.DoesNotExist:
            return Response(
                {"detail": "App not found"}, status=status.HTTP_404_NOT_FOUND
            )

        end_users = app.end_users.filter(deleted=False)
        serializer = EndUserSerializer(end_users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class EndUserDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, app_id, user_id):
        try:
            app = ClientApp.objects.get(id=app_id, owner=request.user)
        except ClientApp.DoesNotExist:
            return Response(
                {"detail": "App not found"}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            user = app.end_users.get(id=user_id)
        except EndUser.DoesNotExist:
            return Response(
                {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        user.deleted = True
        user.save()
        return Response(
            {"message": "User deleted (soft)"}, status=status.HTTP_204_NO_CONTENT
        )
