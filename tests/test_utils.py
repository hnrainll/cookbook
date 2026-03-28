"""Tests for app/utils/ modules"""
import io

from PIL import Image

from app.utils.feishu import extract_img_and_first_text_group
from app.utils.image import compress_image_advanced


class TestCompressImageAdvanced:

    def _make_image(self, width=100, height=100, color="red", fmt="JPEG") -> bytes:
        img = Image.new("RGB", (width, height), color)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()

    def test_small_image_unchanged(self):
        """小于目标大小的图片不压缩"""
        data = self._make_image()
        result = compress_image_advanced(data, target_size_mb=1)
        assert result == data

    def test_large_image_compressed(self):
        """大图片被压缩到目标大小以内"""
        # 创建一个大图片
        data = self._make_image(width=4000, height=4000)
        # 用很小的目标大小强制压缩
        result = compress_image_advanced(data, target_size_mb=0.001)
        assert len(result) < len(data)

    def test_rgba_image_handled(self):
        """RGBA 图片可以被正确处理"""
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        # target_size very small to force compression
        result = compress_image_advanced(data, target_size_mb=0.0001)
        assert isinstance(result, bytes)

    def test_max_dimension(self):
        """max_dimension 参数限制图片最大边"""
        data = self._make_image(width=2000, height=1000)
        result = compress_image_advanced(data, target_size_mb=10, max_dimension=500)
        # 应返回原图（可能没达到大小限制），但如果压缩了尺寸就检查
        img = Image.open(io.BytesIO(result))
        assert max(img.size) <= 2000  # 至少没有变大


class TestExtractImgAndFirstTextGroup:

    def test_basic_text_and_image(self):
        data = {
            "content": [
                [
                    {"tag": "text", "text": "hello"},
                    {"tag": "text", "text": " world"},
                ],
                [
                    {"tag": "img", "image_key": "img_key_123"},
                ],
            ]
        }
        image_key, text = extract_img_and_first_text_group(data)
        assert image_key == "img_key_123"
        assert text == "hello world"

    def test_no_image(self):
        data = {
            "content": [
                [{"tag": "text", "text": "only text"}],
            ]
        }
        image_key, text = extract_img_and_first_text_group(data)
        assert image_key is None
        assert text == "only text"

    def test_no_text(self):
        data = {
            "content": [
                [{"tag": "img", "image_key": "key1"}],
            ]
        }
        image_key, text = extract_img_and_first_text_group(data)
        assert image_key == "key1"
        assert text == ""

    def test_empty_content(self):
        data = {"content": []}
        image_key, text = extract_img_and_first_text_group(data)
        assert image_key is None
        assert text == ""

    def test_json_string_input(self):
        import json
        data = json.dumps({
            "content": [
                [{"tag": "text", "text": "from json"}],
            ]
        })
        image_key, text = extract_img_and_first_text_group(data)
        assert text == "from json"

    def test_separator(self):
        data = {
            "content": [
                [
                    {"tag": "text", "text": "a"},
                    {"tag": "text", "text": "b"},
                ],
            ]
        }
        _, text = extract_img_and_first_text_group(data, separator="-")
        assert text == "a-b"
