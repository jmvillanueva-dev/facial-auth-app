from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics, serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from facial_auth_app.services import FacialRecognitionService, FaceAlreadyRegisteredError
from facial_auth_app.models import FacialRecognitionProfile, ClientApp
from auth_api.serializers import (
    UserSerializer,
    RegistrationSerializer,
    FaceLoginSerializer,
    ClientAppSerializer,
)
import face_recognition


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Inicializamos el serializer con los datos de la petición
        serializer = RegistrationSerializer(data=request.data)

        try:
            # Validamos los datos (esto lanzará una excepción si hay errores)
            serializer.is_valid(raise_exception=True)

            # Si la validación pasa, creamos el usuario
            user = serializer.save()

            # Generamos los tokens para el nuevo usuario
            tokens = get_tokens_for_user(user)

            # Respuesta exitosa
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "tokens": tokens,
                    "message": "Usuario registrado exitosamente",
                },
                status=status.HTTP_201_CREATED,
            )

        except serializers.ValidationError as e:
            # Manejo de errores de validación del serializer
            errors = {}
            for field, error_list in e.detail.items():
                # Tomamos el primer mensaje de error para cada campo
                errors[field] = (
                    error_list[0] if isinstance(error_list, list) else str(error_list)
                )

            return Response(
                {
                    "errors": errors,
                    "message": "Error en los datos de registro",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except FaceAlreadyRegisteredError as e:
            # Manejo específico para rostro ya registrado
            return Response(
                {
                    "errors": {"face_image": str(e)},
                    "message": "Error en el registro facial",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # Manejo de otros errores inesperados
            return Response(
                {
                    "errors": {"non_field_errors": "Ocurrió un error inesperado"},
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

        # --- procesa foto ---
        image_np = FacialRecognitionService.process_uploaded_image(image_file)
        if image_np is None:
            return Response(
                {"detail": "No se ha encontrado ningún rostro."}, status=status.HTTP_400_BAD_REQUEST
            )

        unknown_encodings = face_recognition.face_encodings(image_np)
        if not unknown_encodings:
            return Response(
                {"detail": "No se ha encontrado ningún rostro."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        unknown = unknown_encodings[0].tobytes()

        # --- compara contra perfiles activos ---
        best_user, best_dist = None, 1.0
        for profile in FacialRecognitionProfile.objects.filter(is_active=True):
            match, dist = FacialRecognitionService.compare_faces(
                profile.face_encoding, unknown
            )
            if match and dist < best_dist:
                best_user, best_dist = profile.user, dist

        if best_user and best_dist < 0.6:
            tokens = get_tokens_for_user(best_user)
            return Response(
                {
                    "user": UserSerializer(best_user).data,
                    "tokens": tokens,
                    "confidence": round(1 - best_dist, 3),
                    "message": "Ingreso facial exitoso",
                }
            )

        return Response(
            {"detail": "El rostro del usuario no se encuentra registrado"}, status=status.HTTP_401_UNAUTHORIZED
        )


# Create Client App View
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
