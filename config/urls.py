from django.urls import path
 
from recommendations import views
 
urlpatterns = [
    path("api/health", views.health),
    path("api/form-spec", views.form_spec),
    path("api/recommend", views.recommend),
]
 