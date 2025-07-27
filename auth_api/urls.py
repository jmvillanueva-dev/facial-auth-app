from django.urls import path
from auth_api.views import (
    RegisterView,
    LoginView,
    FaceLoginView,
    FaceLoginFeedbackView,
    ClientAppCreateView,
    ClientAppListView,
    ClientAppUpdateView,
    ClientAppDeleteView,
    EndUserRegisterView,
    EndUserFaceLoginView,
    EndUserListView,
    EndUserDeleteView,
    EndUserFaceFeedbackView,
)

urlpatterns = [
    # Rutas para el cliente de la API (tu usuario)
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/login/face/", FaceLoginView.as_view(), name="facial-login"),
    path(
        "auth/login/face/feedback/",
        FaceLoginFeedbackView.as_view(),
        name="facial-login-feedback",
    ),
    # Rutas para la gestión de las aplicaciones del cliente
    path("apps/create/", ClientAppCreateView.as_view(), name="create-app"),
    path("apps/", ClientAppListView.as_view(), name="list-apps"),
    path("apps/<int:pk>/update/", ClientAppUpdateView.as_view(), name="update-app"),
    path("apps/<int:pk>/delete/", ClientAppDeleteView.as_view(), name="delete-app"),
    # Rutas para los usuarios finales de las aplicaciones de terceros
    path(
        "apps/v1/<str:app_token>/register/",
        EndUserRegisterView.as_view(),
        name="enduser-register",
    ),
    path(
        "apps/v1/<str:app_token>/face-login/",
        EndUserFaceLoginView.as_view(),
        name="enduser-face-login",
    ),
    path(
        "apps/v1/<str:app_token>/face-feedback/",
        EndUserFaceFeedbackView.as_view(),
        name="enduser-face-feedback",
    ),
    # Rutas para que el cliente administre los usuarios finales de su app
    path(
        "apps/<int:app_id>/users/", EndUserListView.as_view(), name="app-endusers-list"
    ),
    path(
        "apps/<int:app_id>/users/<int:user_id>/delete/",
        EndUserDeleteView.as_view(),
        name="app-enduser-delete",
    ),
]
