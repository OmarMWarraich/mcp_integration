
from django.urls import path
from . import views



urlpatterns = [
    path('', views.documentation_interface, name='documentation_interface'),
    path('generate/', views.generate_documentation, name='generate_documentation'),
    path('generate-multiple/', views.generate_documentation_multiple, name='generate_documentation_multiple'),
    path('run-crew/', views.run_crew, name='run_crew'),
    path('crew-status/<str:task_id>/', views.crew_status, name='crew_status'),
]