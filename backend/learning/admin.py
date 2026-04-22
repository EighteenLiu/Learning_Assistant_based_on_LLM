from django.contrib import admin

from .models import Courseware, QARecord, SlideContent, SummaryRecord, TermDictionary


@admin.register(Courseware)
class CoursewareAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "owner__username")


@admin.register(SlideContent)
class SlideContentAdmin(admin.ModelAdmin):
    list_display = ("id", "courseware", "slide_no")
    list_filter = ("courseware",)
    search_fields = ("courseware__title", "title")


@admin.register(QARecord)
class QARecordAdmin(admin.ModelAdmin):
    list_display = ("id", "courseware", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("question", "answer")


@admin.register(SummaryRecord)
class SummaryRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "courseware", "user", "created_at")
    list_filter = ("created_at",)


@admin.register(TermDictionary)
class TermDictionaryAdmin(admin.ModelAdmin):
    list_display = ("id", "source_term", "target_term", "subject_area")
    search_fields = ("source_term", "target_term", "subject_area")

