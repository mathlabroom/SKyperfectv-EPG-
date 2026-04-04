import os
import re
import unicodedata
import shutil

def fury_standard_clean(raw_title):
    # 1. Unicode 归一化 (解决 Zgemma/Linux 识别不出的关键)
    text = unicodedata.normalize('NFC', raw_title)
    
    # 2. 修正 NEWS24 这种会被 Fury 洗掉的频道名
    if 'news24' in text.lower():
        text = re.sub(r'news24', 'ne24', text, flags=re.IGNORECASE)
    
    # 3. 强制小写
    text = text.lower()
    
    # 4. 删除年份 (空格+4位数字)
    text = re.sub(r'\s\d{4}', '', text)
    
    # 5. 删除末尾的日文右引号 」
    if text.endswith('」'):
        text = text[:-1]
    
    # 6. 符号处理：保留感叹号，删除冒号
    text = text.replace(':', '')
    
    # 7. 清理括号备注 【】 [] （）
    text = re.sub(r'[\(\[].*?[\)\]]|【.*?】|（.*?）', '', text)
    
    # 8. 横杠截断 (仅限 " -")
    text = text.partition(" -")[0]
    
    # 9. 首字母大写 (适应 Fury 寻找本地文件的逻辑)
    text = text.strip().capitalize()
    
    return text

def main():
    src_dir = "posters_raw" 
    dst_dir = "posters_final"
    
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    # 遍历文件夹（包括处理 zip 解压出来的子目录）
    for root, dirs, files in os.walk(src_dir):
        for filename in files:
            if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
                name_part = os.path.splitext(filename)[0]
                new_name = fury_standard_clean(name_part)
                
                new_filename = f"{new_name}.jpg"
                src_path = os.path.join(root, filename)
                dst_path = os.path.join(dst_dir, new_filename)
                
                shutil.copy2(src_path, dst_path)
                print(f"Standardized: {filename} -> {new_filename}")

if __name__ == "__main__":
    main()
