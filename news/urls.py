from django.urls import path

from .views import FakeNewsListView, StoryDetailView, StoryListView, critical_stories

urlpatterns = [
    path("", StoryListView.as_view(), name="story-list"),
    path("critical", critical_stories, name="story-critical"),
    path("fake-news", FakeNewsListView.as_view(), name="story-fake-news"),
    path("<int:pk>", StoryDetailView.as_view(), name="story-detail"),
]
