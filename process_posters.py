import os
import re
import unicodedata
import shutil

def fury_standard_clean(raw_title):
    # 1. Unicode 归一化 (解决日文假名 NFD 拆分问题，这是亮图的关键)
    text = unicodedata.normalize('NFC', raw_title)
    
    # 2. 处理特殊的“缩水”频道名 (如 NEWS24 -> ne24)
    if 'news24' in text.lower():
        text = re.sub(r'news24', 'ne24', text, flags=re.IGNORECASE)
    
    # 3. 强制全小写
    text = text.lower()
    
    # 4. 删除年份 (匹配空格+4位数字，如 2024, 2026)
    text = re.sub(r'\s\d{4}', '', text)
    
    # 5. 引号截断 (删除末尾的日文右引号 」)
    if text.endswith('」'):
        text = text[:-1]
    
    # 6. 符号过滤：删冒号，留感叹号
    text = text.replace(':', '')
    
    # 7. 括号备注清除 (删除 【】、[]、（）及其内容)
    text = re.sub(r'[\(\[].*?[\)\]]|【.*?】|（.*?）', '', text)
    
    # 8. 横杠截断：仅针对 " -" (带空格的横杠)
    text = text.partition(" -")[0]
    
    # 9. 最终首字母大写 (符合 Fury 本地匹配逻辑)
    text = text.strip().capitalize()
    
    return text

def main():
    # 设定图片存放的原始目录和目标目录
    src_dir = "posters_raw" 
    dst_dir = "posters_final"
    
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    for filename in os.listdir(src_dir):
        if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
            name_part = os.path.splitext(filename)[0]
            new_name = fury_standard_clean(name_part)
            
            # 统一强制使用 .jpg 后缀
            new_filename = f"{new_name}.jpg"
            shutil.copy2(os.path.join(src_dir, filename), os.path.join(dst_dir, new_filename))
            print(f"Standardized: {filename} -> {new_filename}")

if __name__ == "__main__":
    main()
