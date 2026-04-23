import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from learning.models import Courseware, SlideContent
from learning.services.image_processing_service import ImageProcessingService


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class ExportTranslatedPdfApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pdf-user", password="pass123456")
        token_resp = self.client.post(
            "/api/auth/login",
            {"username": "pdf-user", "password": "pass123456"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_resp.data['access']}")

    def test_export_translated_file_returns_pdf_content_type_for_pdf_courseware(self):
        courseware = Courseware.objects.create(owner=self.user, title="sample-pdf", file="coursewares/sample.pdf")
        SlideContent.objects.create(
            courseware=courseware,
            slide_no=1,
            source_text="Hello",
            translated_text="Ni Hao",
            translated_layout={
                "page_width": 1280,
                "page_height": 720,
                "blocks": [{"block_id": 1, "text": "Ni Hao"}],
                "text_containers": [{"container_id": 1, "kind": "text_frame", "text": "Ni Hao", "paragraphs": ["Ni Hao"]}],
            },
        )

        output_path = ImageProcessingService.translated_output_path(courseware.id, courseware.file.path)
        output_path.write_bytes(b"%PDF-1.7\n%mock\n")

        response = self.client.get(f"/api/coursewares/{courseware.id}/export-translated-ppt")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(str(response["Content-Type"]).startswith("application/pdf"))
        self.assertIn(".pdf", str(response["Content-Disposition"]).lower())
