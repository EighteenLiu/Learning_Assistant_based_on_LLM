from pathlib import Path
from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Courseware, QARecord, SlideContent, SummaryRecord


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("id", "username", "password")

    # 根据校验后的数据创建业务对象，并补齐必要的派生字段。
    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class CoursewareUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Courseware
        fields = ("id", "title", "file", "source_language", "target_language", "status", "created_at")
        read_only_fields = ("id", "title", "status", "created_at")

    # 校验上传文件格式，只放行系统解析链路支持的课件类型。
    def validate_file(self, file_obj):
        # 在序列化层先拦截格式，比进入解析服务后再失败更容易给调用方返回稳定的 400 错误。
        supported_formats = [".pptx", ".ppt", ".pdf"]
        file_ext = Path(file_obj.name).suffix.lower()
        if file_ext not in supported_formats:
            raise serializers.ValidationError(f"Only {', '.join(supported_formats)} files are supported.")
        return file_obj

    # 根据校验后的数据创建业务对象，并补齐必要的派生字段。
    def create(self, validated_data):
        file_obj = validated_data["file"]
        owner = validated_data.get("owner")
        # 标题从原始文件名派生，并在同一用户范围内做去重，避免列表里出现多个同名课件无法区分。
        base_title = Path(file_obj.name or "").stem.strip() or "untitled"
        validated_data["title"] = self._build_unique_title(owner, base_title)
        return super().create(validated_data)

    @staticmethod
    # 实现数据规范化和结构构建，让调用方获得稳定的输出。
    def _build_unique_title(owner, base_title: str) -> str:
        if owner is None:
            return base_title

        existing_titles = set(
            Courseware.objects.filter(owner=owner).values_list("title", flat=True)
        )
        if base_title not in existing_titles:
            return base_title

        suffix = 2
        while f"{base_title}({suffix})" in existing_titles:
            suffix += 1
        return f"{base_title}({suffix})"


class SlideContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlideContent
        fields = (
            "slide_no",
            "title",
            "source_image_url",
            "processed_image_url",
            "translation_done",
            "preview_done",
            "source_text",
            "translated_text",
            "notes",
            "translated_notes",
            "source_layout",
            "translated_layout",
        )


class QARequestSerializer(serializers.Serializer):
    history = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    question = serializers.CharField(max_length=1000)
    slide_no = serializers.IntegerField(required=False, min_value=1)
    use_global_scope = serializers.BooleanField(required=False, default=True)

    # 清理并校验用户问题，防止空问题进入问答模型。
    def validate_question(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Question cannot be empty.")
        return stripped

    # 清洗历史对话，只保留合法角色和有限长度的上下文。
    def validate_history(self, value):
        # 只保留最近的有效对话并限制单条长度，既能支持多轮追问，也能控制 LLM 请求体大小。
        cleaned = []
        for item in value[:12]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            cleaned.append({"role": role, "content": content[:4000]})
        return cleaned


class QARecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = QARecord
        fields = ("id", "question", "answer", "citations", "created_at")


class SummaryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SummaryRecord
        fields = ("id", "chapter_summary", "key_points", "term_pairs", "learning_suggestions", "mind_map", "created_at")
