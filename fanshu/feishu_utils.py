import json


def extract_img_and_first_text_group(data, separator=''):
    """
    从JSON数据中提取第一个img标签的image_key值和第一个包含text的列表中的所有text值

    Args:
        data: dict 或 JSON字符串
        separator: text值之间的分隔符，默认为空字符串（直接连接）

    Returns:
        tuple: (image_key, combined_text_from_first_group)
               - image_key: 第一个img标签的image_key值，如果没有则为None
               - combined_text_from_first_group: 第一个包含text的列表中所有text值合并后的字符串
    """
    # 如果输入是字符串，先解析为字典
    if isinstance(data, str):
        data = json.loads(data)

    content = data.get('content', [])

    first_image_key = None
    first_text_group = []
    first_text_group_found = False

    # 遍历content中的每个列表
    for item_list in content:
        current_list_texts = []

        # 一次遍历同时处理img和text
        for item in item_list:
            tag = item.get('tag')

            # 查找第一个img
            if tag == 'img' and first_image_key is None:
                first_image_key = item.get('image_key')

            # 收集当前列表中的text（如果还没找到第一个text组）
            elif tag == 'text' and not first_text_group_found:
                text_value = item.get('text')
                if text_value:
                    current_list_texts.append(text_value)

        # 如果当前列表包含text且还没找到第一个text组，就是我们要的
        if current_list_texts and not first_text_group_found:
            first_text_group = current_list_texts
            first_text_group_found = True

        # 如果已经找到了img和第一个text组，可以提前退出
        if first_image_key is not None and first_text_group_found:
            break

    # 合并第一个text组的所有text值
    combined_text = separator.join(first_text_group) if first_text_group else ''

    return first_image_key, combined_text