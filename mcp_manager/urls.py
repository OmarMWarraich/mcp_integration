
from django.urls import path
from . import views



urlpatterns = [
    path('', views.documentation_interface, name='documentation_interface'),
    # TODO: Add the URL of the generate_documentation view
]