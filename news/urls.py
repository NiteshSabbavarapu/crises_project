from django.urls import path

from .views import CompleteNewsListView, FakeNewsListView, StoryDetailView, StoryListView, critical_stories

urlpatterns = [
    path("", StoryListView.as_view(), name="story-list"),
    path("complete-news", CompleteNewsListView.as_view(), name="story-complete-news"),
    path("critical", critical_stories, name="story-critical"),
    path("fake-news", FakeNewsListView.as_view(), name="story-fake-news"),
    path("<int:pk>", StoryDetailView.as_view(), name="story-detail"),
]
