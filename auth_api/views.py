from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics, serializers as drf_serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import render
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from facial_auth_app.services import (
    FacialRecognitionService,
    FaceAlreadyRegisteredError,
    _bytes_to_array,
    _face_detect_and_align,
    _preprocess_for_embedding,
    embedding_model,
)
from facial_auth_app.models import FacialRecognitionProfile
from auth_api.models import ClientApp, EndUser
from auth_api.serializers import (
    UserSerializer,
    RegistrationSerializer,
    FaceLoginSerializer,
    ClientAppSerializer,
    EndUserRegistrationSerializer,
)


def home(request):
    return render(request, "home.html")


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
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
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            import traceback
            traceback.print_exc()  # 👈 Agrega esto
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
        image_file = serializer.validated_data["face_image"]

        user = FacialRecognitionService.login_with_face(image_file)

        if user:
            tokens = get_tokens_for_user(user)
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Ingreso facial exitoso",
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"detail": "El rostro del usuario no se encuentra registrado"},
            status=status.HTTP_401_UNAUTHORIZED,
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
        except (
            drf_serializers.ValidationError
        ) as e:
            return Response(
                e.detail, status=status.HTTP_400_BAD_REQUEST
            )  
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

        image_np = _bytes_to_array(image.read())

        faces = _face_detect_and_align(image_np)
        if not faces:
            return Response(
                {"detail": "No se detectó ningún rostro en la imagen."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        processed_face = _preprocess_for_embedding(faces[0])
        emb = embedding_model(processed_face)[0].numpy()
        unknown = emb.tobytes()

        best_user = None
        best_dist = 1.0

        # Iterar sobre los usuarios de la aplicación para encontrar una coincidencia
        # El threshold aquí debe coincidir con el DEFAULT_THRESHOLD del servicio,
        # o puedes usar app.strictness si lo deseas.
        # Por ahora, mantendremos el 0.6 que tenías.
        # Se asume que `app.strictness` está entre 0 y 1 para usarse con `compare_faces`
        # si lo deseas: threshold_for_app = 1 - app.strictness (si strictness es confianza)
        # o simplemente app.strictness (si strictness es distancia).

        for user in app.end_users.filter(deleted=False):
            match, dist = FacialRecognitionService.compare_faces(
                user.face_encoding, unknown
            )
            if match and dist < best_dist: 
                best_user, best_dist = user, dist


        if (
            best_user
        ):  
            return Response(
                {
                    "email": best_user.email,
                    "full_name": best_user.full_name,
                    "message": "Inicio de Sesión exitoso",
                    "confidence": round(
                        1 - best_dist, 3
                    ), 
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"detail": "Rostro no reconocido"}, status=status.HTTP_401_UNAUTHORIZED
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
        data = [
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "created_at": user.created_at,
            }
            for user in end_users
        ]
        return Response(data, status=status.HTTP_200_OK)


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
