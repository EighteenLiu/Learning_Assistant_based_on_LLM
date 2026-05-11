from django.conf import settings
from django.db import models


class Courseware(models.Model):
    STATUS_UPLOADED = "uploaded"
    STATUS_TRANSLATING = "translating"
    STATUS_TRANSLATED = "translated"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_TRANSLATING, "Translating"),
        (STATUS_TRANSLATED, "Translated"),
        (STATUS_FAILED, "Failed"),
    )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coursewares")
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="coursewares/")
    source_language = models.CharField(max_length=10, default="en")
    target_language = models.CharField(max_length=10, default="zh")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    last_error = models.TextField(blank=True, default="")
    translation_started_at = models.DateTimeField(null=True, blank=True)
    translation_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    translation_total_chunks = models.PositiveIntegerField(default=0)
    translation_completed_chunks = models.PositiveIntegerField(default=0)
    translation_current_slide_no = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} ({self.owner_id})"


class SlideContent(models.Model):
    courseware = models.ForeignKey(Courseware, on_delete=models.CASCADE, related_name="slides")
    slide_no = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True, default="")
    source_image_url = models.CharField(max_length=500, blank=True, default="")
    processed_image_url = models.CharField(max_length=500, blank=True, default="")
    translation_done = models.BooleanField(default=False)
    preview_done = models.BooleanField(default=False)
    source_text = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    translated_text = models.TextField(blank=True, default="")
    translated_notes = models.TextField(blank=True, default="")
    source_layout = models.JSONField(default=dict, blank=True)
    translated_layout = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("slide_no",)
        unique_together = ("courseware", "slide_no")

    def __str__(self) -> str:
        return f"Courseware#{self.courseware_id}-Slide#{self.slide_no}"


class QARecord(models.Model):
    courseware = models.ForeignKey(Courseware, on_delete=models.CASCADE, related_name="qa_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qa_records")
    question = models.TextField()
    answer = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class SummaryRecord(models.Model):
    courseware = models.ForeignKey(Courseware, on_delete=models.CASCADE, related_name="summary_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="summary_records")
    chapter_summary = models.TextField()
    key_points = models.JSONField(default=list, blank=True)
    term_pairs = models.JSONField(default=list, blank=True)
    learning_suggestions = models.JSONField(default=list, blank=True)
    mind_map = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class TermDictionary(models.Model):
    source_term = models.CharField(max_length=200, unique=True)
    target_term = models.CharField(max_length=200)
    subject_area = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("source_term",)

    def __str__(self) -> str:
        return f"{self.source_term} -> {self.target_term}"


class TranslationCache(models.Model):
    cache_key = models.CharField(max_length=64, unique=True, db_index=True)
    translation_type = models.CharField(max_length=32, default="slide_text", db_index=True)
    source_language = models.CharField(max_length=10, default="en")
    target_language = models.CharField(max_length=10, default="zh")
    model_name = models.CharField(max_length=120, blank=True, default="")
    term_hint_hash = models.CharField(max_length=64, blank=True, default="")
    source_hash = models.CharField(max_length=64, db_index=True)
    source_text = models.TextField()
    translated_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(
                fields=("translation_type", "model_name", "term_hint_hash", "source_hash"),
                name="lrn_tc_type_model_term_src_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.translation_type}:{self.source_hash[:8]}"
