from django.urls import path

from .views import (
    CoursewareListView,
    CoursewareSlidesView,
    CoursewareUploadView,
    LoginView,
    QAView,
    RecordsView,
    RegisterView,
    SummaryView,
    CoursewareStatusView,
    ExportTranslatedPPTView,
    TranslateSlideNotesView,
    TranslateCoursewareView,
)


urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="register"),
    path("auth/login", LoginView.as_view(), name="login"),
    path("coursewares", CoursewareListView.as_view(), name="courseware-list"),
    path("coursewares/upload", CoursewareUploadView.as_view(), name="courseware-upload"),
    path("coursewares/<int:pk>/translate", TranslateCoursewareView.as_view(), name="courseware-translate"),
    path("coursewares/<int:pk>/slides", CoursewareSlidesView.as_view(), name="courseware-slides"),
    path("coursewares/<int:pk>/slides/<int:slide_no>/translate-notes", TranslateSlideNotesView.as_view(), name="slide-notes-translate"),
    path("coursewares/<int:pk>/status", CoursewareStatusView.as_view(), name="courseware-status"),
    path("coursewares/<int:pk>/export-translated-ppt", ExportTranslatedPPTView.as_view(), name="courseware-export-translated-ppt"),
    path("coursewares/<int:pk>/qa", QAView.as_view(), name="courseware-qa"),
    path("coursewares/<int:pk>/summary", SummaryView.as_view(), name="courseware-summary"),
    path("coursewares/<int:pk>/records", RecordsView.as_view(), name="courseware-records"),
]
