import os
import re
import unicodedata
import shutil

def fury_standard_clean(raw_title):
    # 1. Unicode 归一化 (解决 NFD 编码导致的不显图问题)
    text = unicodedata.normalize('NFC', raw_title)
    
    # 2. 频道名特殊修正 (针对 Fury 暴力清洗的适配)
    if 'news24' in text.lower():
        text = re.sub(r'news24', 'ne24', text, flags=re.IGNORECASE)
    
    # 3. 强制全小写
    text = text.lower()
    
    # 4. 删除年份 (兼容有无空格，限定19/20开头)
    text = re.sub(r'\s?(19|20)\d{2}', '', text)
    
    # 5. 【新增：末尾感叹号删除】
    # 只要是以 ! (半角) 或 ！(全角) 结尾，就切掉
    while text.endswith('!') or text.endswith('！'):
        text = text[:-1]
    
    # 6. 【引号截断】删除末尾的日文右引号 」
    if text.endswith('」'):
        text = text[:-1]
    
    # 7. 符号处理：只删除冒号 ':'，中间的感叹号会因为没触发上面的 endswith 而保留
    text = text.replace(':', '')
    
    # 8. 括号备注清除 【】 [] （）
    text = re.sub(r'[\(\[].*?[\)\]]|【.*?】|（.*?）', '', text)
    
    # 9. 横杠截断：仅限 " -" (带空格的横杠)
    text = text.partition(" -")[0]
    
    # 10. 最终首字母大写
    text = text.strip().capitalize()
    
    return text
def main():
    src_dir = "posters_raw" 
    dst_dir = "posters_final"
    
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    for root, dirs, files in os.walk(src_dir):
        for filename in files:
            if filename.startswith('.'): continue
            if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
                name_part = os.path.splitext(filename)[0]
                new_name = fury_standard_clean(name_part)
                
                new_filename = f"{new_name}.jpg"
                src_path = os.path.join(root, filename)
                dst_path = os.path.join(dst_dir, new_filename)
                
                try:
                    shutil.copy2(src_path, dst_path)
                except Exception:
                    pass

if __name__ == "__main__":
    main()
