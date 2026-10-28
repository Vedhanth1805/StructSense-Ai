from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from webdata import ui
urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", ui.dashboard, name="dashboard"),
    path("projects/<int:project_id>/", ui.project_page, name="project-page"),
    path("projects/<int:project_id>/visualization/", ui.project_visualization, name="project-visualization"),
    path("projects/<int:project_id>/demo-video/", ui.project_demo_video, name="project-demo-video"),
    path("api/", include(("webdata.urls", "webdata"), namespace="api")),
    path("api-auth/", include("rest_framework.urls")),
]
