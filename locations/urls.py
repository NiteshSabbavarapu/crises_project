from django.urls import path

from .views import AreaListView, CityListView

urlpatterns = [
    path("cities", CityListView.as_view(), name="location-cities"),
    path("areas", AreaListView.as_view(), name="location-areas"),
]
