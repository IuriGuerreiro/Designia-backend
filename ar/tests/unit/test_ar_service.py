from unittest.mock import Mock, PropertyMock, patch

import pytest

from ar.models import ProductARModel
from ar.services.ar_service import ARService


@pytest.mark.unit
class TestARServiceUnit:
    def setup_method(self):
        self.service = ARService()
        self.product_id = "test-product-id"

    @patch("ar.models.ProductARModel.objects.filter")
    def test_has_3d_model_true(self, mock_filter):
        mock_filter.return_value.exists.return_value = True

        result = self.service.has_3d_model(self.product_id)
        assert result.ok
        assert result.value is True

    @patch("ar.models.ProductARModel.objects.filter")
    def test_has_3d_model_false(self, mock_filter):
        mock_filter.return_value.exists.return_value = False

        result = self.service.has_3d_model(self.product_id)
        assert result.ok
        assert result.value is False

    @patch("ar.models.ProductARModel.objects.filter")
    def test_get_ar_view_url_success(self, mock_filter):
        mock_ar_model = Mock(spec=ProductARModel)
        mock_ar_model.s3_key = "models/test.glb"
        mock_filter.return_value.first.return_value = mock_ar_model

        result = self.service.get_ar_view_url(self.product_id)

        assert result.ok
        assert result.value == "/api/system/s3-models/models/test.glb"

    @patch("ar.models.ProductARModel.objects.filter")
    def test_get_ar_view_url_none(self, mock_filter):
        mock_filter.return_value.first.return_value = None

        result = self.service.get_ar_view_url(self.product_id)

        assert result.ok
        assert result.value is None

    def test_validate_3d_model_file_valid(self):
        mock_file = Mock()
        mock_file.name = "model.glb"
        mock_file.size = 1024 * 1024  # 1MB

        result = self.service.validate_3d_model_file(mock_file)
        assert result.ok
        assert result.value is True

    def test_validate_3d_model_file_invalid_ext(self):
        mock_file = Mock()
        mock_file.name = "model.txt"
        mock_file.size = 1024

        result = self.service.validate_3d_model_file(mock_file)
        assert not result.ok
        assert "Invalid file format" in result.error_detail

    def test_validate_3d_model_file_too_large(self):
        mock_file = Mock()
        mock_file.name = "model.glb"
        mock_file.size = 100 * 1024 * 1024  # 100MB (limit is 50MB)

        result = self.service.validate_3d_model_file(mock_file)
        assert not result.ok
        assert "exceeds limit" in result.error_detail

    @patch("ar.models.ProductARModel.objects.filter")
    def test_get_model_metadata(self, mock_filter):
        mock_ar_model = Mock(spec=ProductARModel)
        mock_ar_model.id = 1
        mock_ar_model.file_size = 1024
        mock_ar_model.content_type = "model/gltf-binary"
        mock_ar_model.s3_key = "models/test.glb"
        mock_ar_model.original_filename = "test.glb"

        mock_filter.return_value.first.return_value = mock_ar_model

        result = self.service.get_model_metadata(self.product_id)

        assert result.ok
        assert result.value["id"] == 1
        assert result.value["file_size"] == 1024
        assert result.value["url"] == "/api/system/s3-models/models/test.glb"

    @patch("ar.models.ProductARModel.objects.filter")
    def test_has_3d_model_error(self, mock_filter):
        mock_filter.side_effect = Exception("DB Error")
        result = self.service.has_3d_model(self.product_id)
        assert not result.ok
        assert "DB Error" in result.error_detail

    @patch("ar.models.ProductARModel.objects.filter")
    def test_get_ar_view_url_error(self, mock_filter):
        mock_filter.side_effect = Exception("DB Error")
        result = self.service.get_ar_view_url(self.product_id)
        assert not result.ok
        assert "DB Error" in result.error_detail

    def test_validate_3d_model_file_error(self):
        mock_file = Mock()
        # Raise exception when accessing size
        p = PropertyMock(side_effect=Exception("File Error"))
        type(mock_file).size = p

        result = self.service.validate_3d_model_file(mock_file)
        assert not result.ok
        assert "File Error" in result.error_detail

    @patch("ar.models.ProductARModel.objects.filter")
    def test_get_model_metadata_not_found(self, mock_filter):
        mock_filter.return_value.first.return_value = None
        result = self.service.get_model_metadata(self.product_id)
        assert not result.ok
        assert "No AR model found" in result.error_detail

    @patch("ar.models.ProductARModel.objects.filter")
    def test_get_model_metadata_error(self, mock_filter):
        mock_filter.side_effect = Exception("DB Error")
        result = self.service.get_model_metadata(self.product_id)
        assert not result.ok
        assert "DB Error" in result.error_detail
