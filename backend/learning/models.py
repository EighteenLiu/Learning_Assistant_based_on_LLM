from django.conf import settings
from django.db import models


class Courseware(models.Model):
    # 课件处理采用明确的状态机：上传后进入 uploaded，翻译任务运行时为 translating，
    # 至少有有效结果时进入 translated，全部失败或异常时进入 failed，便于前端轮询和错误恢复。
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
    # last_error 不直接抛给线程外层，而是落库保存，避免后台任务失败后前端只能看到“请求成功”。
    last_error = models.TextField(blank=True, default="")
    # 下面几个字段服务于长任务进度展示：任务开始时间用于估算耗时，chunk 进度用于解释“为什么还在处理中”。
    translation_started_at = models.DateTimeField(null=True, blank=True)
    translation_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    translation_total_chunks = models.PositiveIntegerField(default=0)
    translation_completed_chunks = models.PositiveIntegerField(default=0)
    translation_current_slide_no = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    # 返回对象的可读名称，方便管理后台、日志和调试定位。
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
    # layout 保存的是归一化坐标和文本容器信息，而不是只保存纯文本。
    # 这样导出 PPT/PDF 时可以把译文放回原来的位置，保留原课件的视觉结构。
    source_layout = models.JSONField(default=dict, blank=True)
    translated_layout = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("slide_no",)
        unique_together = ("courseware", "slide_no")

    # 返回对象的可读名称，方便管理后台、日志和调试定位。
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

    # 返回对象的可读名称，方便管理后台、日志和调试定位。
    def __str__(self) -> str:
        return f"{self.source_term} -> {self.target_term}"


class TranslationCache(models.Model):
    # 缓存键同时包含模型、术语表、语种和原文哈希，避免“同一句话在不同术语约束下复用错译文”。
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

    # 返回对象的可读名称，方便管理后台、日志和调试定位。
    def __str__(self) -> str:
        return f"{self.translation_type}:{self.source_hash[:8]}"
