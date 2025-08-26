import io

from PIL import Image


def compress_image_advanced(image_bytes, target_size_mb=2, max_dimension=None):
    """
    高级压缩方法，包含更多优化选项

    Args:
        image_bytes: 原始图片bytes数据
        target_size_mb: 目标大小(MB)
        max_dimension: 图片最大边长限制（可选）

    Returns:
        bytes: 压缩后的图片bytes数据
    """
    target_size_bytes = target_size_mb * 1024 * 1024

    if len(image_bytes) <= target_size_bytes:
        return image_bytes

    image = Image.open(io.BytesIO(image_bytes))

    # 处理透明度
    if image.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        if image.mode in ('RGBA', 'LA'):
            background.paste(image, mask=image.split()[-1])
        else:
            background.paste(image)
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')

    # 如果指定了最大尺寸限制
    if max_dimension:
        width, height = image.size
        if max(width, height) > max_dimension:
            if width > height:
                new_width = max_dimension
                new_height = int(height * max_dimension / width)
            else:
                new_height = max_dimension
                new_width = int(width * max_dimension / height)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # 先尝试不缩放
    low_quality, high_quality = 10, 95
    best_quality = 10

    while low_quality <= high_quality:
        mid_quality = (low_quality + high_quality) // 2
        size = _get_compressed_size(image, mid_quality)

        if size <= target_size_bytes:
            best_quality = mid_quality
            low_quality = mid_quality + 1
        else:
            high_quality = mid_quality - 1

    # 检查是否需要缩放
    if _get_compressed_size(image, best_quality) <= target_size_bytes:
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=best_quality, optimize=True)
        return output.getvalue()

    # 需要缩放，使用二分查找找到最佳尺寸
    original_width, original_height = image.size
    min_scale, max_scale = 0.1, 1.0
    best_scale = 0.1

    while max_scale - min_scale > 0.01:
        mid_scale = (min_scale + max_scale) / 2
        new_width = int(original_width * mid_scale)
        new_height = int(original_height * mid_scale)

        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 对缩放后的图片找最佳质量
        low_q, high_q = 10, 95
        best_q = 10

        while low_q <= high_q:
            mid_q = (low_q + high_q) // 2
            size = _get_compressed_size(resized_image, mid_q)

            if size <= target_size_bytes:
                best_q = mid_q
                low_q = mid_q + 1
            else:
                high_q = mid_q - 1

        if _get_compressed_size(resized_image, best_q) <= target_size_bytes:
            best_scale = mid_scale
            min_scale = mid_scale
        else:
            max_scale = mid_scale

    # 生成最终结果
    final_width = int(original_width * best_scale)
    final_height = int(original_height * best_scale)
    final_image = image.resize((final_width, final_height), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    final_image.save(output, format='JPEG', quality=best_quality, optimize=True)
    return output.getvalue()


# 二分查找最佳质量参数
def _get_compressed_size(img, quality):
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=quality, optimize=True)
    return len(output.getvalue())