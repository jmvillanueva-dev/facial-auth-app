from django.urls import path
from auth_api.views import (
    RegisterView,
    LoginView,
    FaceLoginView,
    ClientAppCreateView,
    ClientAppListView,
    ClientAppUpdateView,
    ClientAppDeleteView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/login/face/", FaceLoginView.as_view(), name="facial-login"),
    path("apps/create-app/", ClientAppCreateView.as_view(), name="create-app"),
    path("apps/my-apps/", ClientAppListView.as_view(), name="list-apps"),
    path("apps/update-app/<int:pk>/", ClientAppUpdateView.as_view(), name="update-app"),
    path("apps/delete-app/<int:pk>/", ClientAppDeleteView.as_view(), name="delete-app"),
]
