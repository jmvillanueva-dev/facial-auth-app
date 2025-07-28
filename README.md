<h1 align="center">Facial-auth-app</h1>

<p align="center">
  <img src="https://img.artiversehub.ai/2025/06/03/c83841258fcd4250bb0ce7a24391ec35.webp" alt="Demo de la app" width="400">
</p>

Aplicación de autenticación facial desarrollada con Django y Django REST Framework. Este proyecto permite autenticar usuarios mediante reconocimiento facial, integrando modelos de aprendizaje profundo, procesamiento de imágenes y una API REST para facilitar su integración.

## Integrantes
- Adrian Caiza
- Erick Nuñez
- Jhonny Villanueva M.

## Características principales
- 🔐 Autenticación mediante credenciales tradicionales y reconocimiento facial.
- 🧑‍💼 Asociación de perfiles faciales únicos por usuario.
- 🌐 API RESTful lista para integrarse con aplicaciones web y móviles.
- 🔐 Almacenamiento seguro de imágenes y codificaciones faciales.
- 🗣️ Soporte para feedback del sistema de reconocimiento, útil para mejorar su rendimiento.

## Estructura del Proyecto
```text
facial-auth-app/
├── auth_api/           # Lógica de autenticación y gestión de usuarios
├── facial_auth_app/    # Reconocimiento facial y lógica de procesamiento
├── core/               # Configuración principal del proyecto Django
├── tf_models/          # Modelos descargados desde TensorFlow Hub
├── download_models.py  # Script para obtener los modelos de reconocimiento facial
├── requirements.txt    # Dependencias del proyecto
├── manage.py           # Utilidad estándar de Django
└── README.md           # Documentación del proyecto
```
## Tecnologías y dependencias principales
Estas son las librerías y frameworks clave utilizadas en nuestro proyecto:

| Paquete                      | Descripción breve                                                                 |
|-----------------------------|------------------------------------------------------------------------------------|
| `Django`                  | Framework web de alto nivel para construir aplicaciones web seguras y rápidas.    |
| `Django REST Framework`   | Extensión de Django para crear APIs RESTful de manera sencilla y robusta.         |
| `SimpleJWT`               | Proveedor de autenticación con JSON Web Tokens (JWT) para DRF.                    |
| `OpenCV-Python-Headless`  | Librería de visión computacional optimizada para servidores sin GUI.              |
| `NumPy`                   | Biblioteca fundamental para cálculos numéricos con arrays multidimensionales.     |
| `Scikit-learn`            | Herramientas de machine learning y análisis predictivo en Python.                 |
| `TensorFlow CPU`          | Versión optimizada para CPU del framework de aprendizaje profundo TensorFlow.     |
| `TensorFlow Hub`          | Repositorio de modelos preentrenados listos para usar en tareas de ML.            |
| `Pillow`                  | Biblioteca para abrir, manipular y guardar imágenes en distintos formatos.         |
| `python-dotenv`           | Carga variables de entorno desde un archivo `.env` para configuración segura.     |
| `django-cors-headers`    | Middleware que permite configurar políticas CORS para peticiones externas.        |
| `django-filter`          | Filtros avanzados para búsquedas en vistas genéricas de DRF.                      |
| `django-extensions`       | Conjunto de herramientas útiles para mejorar el desarrollo con Django.            |

## Modulos del Proyecto
- **auth_api**: Contiene la lógica de autenticación y gestión de usuarios, incluyendo vistas y serializadores para manejar el registro, inicio de sesión y autenticación mediante JWT.
- **facial_auth_app**: Implementa el reconocimiento facial y la lógica de procesamiento de imágenes, incluyendo la carga y comparación de imágenes faciales.
- **core**: Configuración principal del proyecto Django, incluyendo ajustes y configuraciones globales.
- **tf_models**: Almacena los modelos descargados desde TensorFlow Hub, utilizados para el reconocimiento facial.
- **download_models.py**: Script para descargar y preparar los modelos de reconocimiento facial necesarios para el funcionamiento de la aplicación. 
- **requirements.txt**: Lista de dependencias del proyecto, necesaria para instalar los paquetes requeridos.
- **manage.py**: Utilidad estándar de Django para ejecutar comandos de gestión del proyecto, como migraciones y ejecución del servidor.

## Archivo [admin.py]

Este archivo define los modelos que se mostrarán en el panel de administración de Django, permitiendo gestionar usuarios y sus perfiles faciales.

### 🔐 CustomUserAdmin – Usuarios Administradores
Vista personalizada de métricas por usuario.
Campos visibles: 
- Nombre
- Email
- Autenticación facial habilitada
- Fecha de registro
- etc.

Métricas mostradas:

- Total de intentos de inicio de sesión
- Resultados por estado inicial (success, ambiguous_match, no_match, error)
- Feedback del usuario (correcto / incorrecto)
- Tasa de verdaderos y falsos positivos (basado en feedback)

### 🧑‍💼 ClientAppAdmin – Aplicaciones Cliente
Administra las apps registradas que consumen la API.
Métricas específicas por app, como número de intentos y rendimiento del reconocimiento facial.

Campos configurables:

- CONFIDENCE_THRESHOLD y FALLBACK_THRESHOLD para ajustar la sensibilidad del sistema.

### 👥 EndUserAdmin – Usuarios Finales
Gestiona los usuarios que usan reconocimiento facial en las apps cliente.

### 📷 EndUserFeedbackAdmin – Feedback de Reconocimiento
Muestra feedback enviado por los usuarios finales tras un intento de autenticación.

### 🔍 EndUserLoginAttemptAdmin y CustomUserLoginAttemptAdmin
Registro detallado de todos los intentos de inicio de sesión por reconocimiento facial.

Campos disponibles:

- Imagen enviada
- Usuario que intentó autenticarse
- Usuario coincidente (si lo hubo)
- Estado del sistema y feedback humano
- Distancia de similitud, tasa de éxito, confirmación por feedback

## Archivo [models.py]
Este archivo define los modelos de datos utilizados en la aplicación, incluyendo usuarios, aplicaciones cliente y feedback de reconocimiento facial.

### 👤 CustomUser
Extiende el modelo base AbstractUser para incluir:
- face_auth_enabled: activa o desactiva autenticación facial.
- full_name: nombre completo del usuario.
Comportamiento sobrescrito para errores de unicidad personalizados.

### 🏢 ClientApp
Representa una aplicación cliente que consume la API de autenticación facial.
Asociada a un CustomUser como propietario.

Campos de configuración:

- CONFIDENCE_THRESHOLD: umbral de confianza para coincidencias faciales.
- FALLBACK_THRESHOLD: umbral para coincidencias ambiguas.
- face_encoding: vector numérico que representa la codificación facial del usuario.

### 👥 EndUser
Usuarios finales registrados por las aplicaciones cliente.
Almacenamiento de face_encoding (vector numérico) en formato binario.
Asociado a una ClientApp.
Soporte para eliminación lógica mediante el campo deleted.

### 📸 EndUserFeedback
Feedback facial enviado por un EndUser luego de un intento de autenticación.
Imagen enviada, tipo de feedback (correcto, incorrecto, etc.).
Asociado a la app y usuario.
Útil para retroalimentar y mejorar los modelos de reconocimiento.

### 🧪 EndUserLoginAttempt
Registra todos los intentos de login facial de un EndUser.
Campos destacados:

- attempting_end_user: quién intentó iniciar sesión.
- best_match_user: usuario que el sistema detectó como mejor coincidencia.
- initial_status: resultado según el modelo (success, no_match, etc.).
- user_feedback: opinión del usuario tras el intento.
- is_verified_and_correct: confirma si fue un login válido tras feedback.

### 🧪 CustomUserLoginAttempt
Similar al anterior, pero registra intentos de login facial de usuarios administradores (CustomUser).
Mismo conjunto de campos que EndUserLoginAttempt.
Útil para medir el rendimiento del sistema en el backend.

### Ejemplo del flujo de trabajo
1. Un CustomUser crea una ClientApp.
2. Registra a varios EndUser junto con sus imágenes faciales.
3. Un EndUser intenta iniciar sesión mediante reconocimiento facial.
4. El sistema evalúa, asigna un initial_status, y solicita feedback.
5. El intento se guarda como EndUserLoginAttempt, y si hay feedback, se almacena en EndUserFeedback.

## Archivo [serializers.py]

Este módulo define los serializadores utilizados en el sistema de autenticación facial para usuarios internos y finales. Estos serializadores manejan registro, login, feedback y administración de apps cliente.


### 🔧 Serializadores Incluidos

| Clase                            | Descripción                                                                 |
|----------------------------------|------------------------------------------------------------------------------|
| `UserSerializer`                 | Serializa datos públicos de un usuario.                                     |
| `RegistrationSerializer`         | Registro de usuarios internos con imagen facial.                            |
| `FaceLoginSerializer`           | Login por imagen facial.                                                    |
| `FaceLoginFeedbackSerializer`    | Retroalimentación del login facial.                                         |
| `ClientAppSerializer`            | Gestión de aplicaciones cliente.                                            |
| `EndUserRegistrationSerializer`  | Registro facial para usuarios finales vinculados a una app cliente.         |
| `EndUserSerializer`              | Visualiza datos del usuario final.                                          |
| `EndUserFaceFeedbackSerializer`  | Feedback sobre intentos de login de usuarios finales.                       |

---

### 👤 RegistrationSerializer

Permite registrar usuarios internos con autenticación facial.

- Valida la contraseña conforme a políticas de Django.
- Detecta y valida rostro en imagen.
- Verifica duplicado por correo o por rostro (a menos que se use `force_register`).

### 🔐 FaceLoginSerializer
Recibe una imagen para autenticar a un usuario.
Compara el rostro con embeddings ya registrados.

### 🔁 FaceLoginFeedbackSerializer
Permite dar retroalimentación sobre el resultado de un login facial.
Tipos de feedback:
- Correcto: requiere user_id, password, face_image.
- Incorrecto: requiere login_attempt_id.

### 🧩 ClientAppSerializer
Permite registrar o administrar una app cliente que usará reconocimiento facial.

Campos especiales:
- CONFIDENCE_THRESHOLD: umbral para coincidencia exacta.
- FALLBACK_THRESHOLD: umbral para coincidencias ambiguas.

### 👥 EndUserRegistrationSerializer
Registra usuarios finales (por ejemplo, clientes de una app externa).
Asocia un rostro a un end_user único por app.
Reactiva registros antiguos si el usuario ya existía.
Puede forzar registro duplicado con force_register.

## Archivo [urls.py]

Este archivo define los endpoints disponibles en la API para manejar tanto usuarios internos como usuarios finales vinculados a una aplicación cliente.


### 🔑 Endpoints de Autenticación (Usuario interno)

| Método | Endpoint                     | Vista                | Descripción                                         |
|--------|------------------------------|----------------------|-----------------------------------------------------|
| POST   | `/auth/register/`            | `RegisterView`       | Registro de usuario con imagen facial.             |
| POST   | `/auth/login/`               | `LoginView`          | Login tradicional con correo y contraseña.         |
| POST   | `/auth/login/face/`          | `FaceLoginView`      | Login por reconocimiento facial.                   |
| POST   | `/auth/login/face/feedback/` | `FaceLoginFeedbackView` | Enviar retroalimentación del login facial.     |


### 🧩 Endpoints para Gestión de Aplicaciones Cliente

| Método | Endpoint                        | Vista                   | Descripción                          |
|--------|----------------------------------|--------------------------|--------------------------------------|
| POST   | `/apps/create/`                 | `ClientAppCreateView`    | Crear una nueva aplicación cliente. |
| GET    | `/apps/`                        | `ClientAppListView`      | Listar todas las aplicaciones.      |
| PUT    | `/apps/<int:pk>/update/`       | `ClientAppUpdateView`    | Actualizar una app específica.      |
| DELETE | `/apps/<int:pk>/delete/`       | `ClientAppDeleteView`    | Eliminar una app específica.        |


### 👤 Endpoints para Usuarios Finales de Aplicaciones

| Método | Endpoint                                           | Vista                      | Descripción                                    |
|--------|----------------------------------------------------|----------------------------|------------------------------------------------|
| POST   | `/apps/v1/<app_token>/register/`                  | `EndUserRegisterView`      | Registrar un usuario final con imagen.         |
| POST   | `/apps/v1/<app_token>/face-login/`                | `EndUserFaceLoginView`     | Login facial para usuarios finales.            |
| POST   | `/apps/v1/<app_token>/face-feedback/`             | `EndUserFaceFeedbackView`  | Enviar feedback del intento de login facial.   |


### 🛠️ Endpoints de Administración de Usuarios Finales

| Método | Endpoint                                                     | Vista                 | Descripción                                     |
|--------|--------------------------------------------------------------|------------------------|-------------------------------------------------|
| GET    | `/apps/<app_id>/users/`                                     | `EndUserListView`      | Lista de usuarios finales de una app.          |
| DELETE | `/apps/<app_id>/users/<user_id>/delete/`                    | `EndUserDeleteView`    | Eliminar un usuario final específico.          |


📌 Las rutas están organizadas para cubrir tanto el **registro y autenticación facial** como la **gestión de usuarios y apps cliente**.  
Todas las operaciones están protegidas y requieren autenticación apropiada.

