import os
import re
import unicodedata
from PIL import Image, ImageFilter  # 引入模糊滤镜

def fury_standard_clean(raw_title):
    # 1. Unicode 归一化
    text = unicodedata.normalize('NFC', raw_title)
    
    # 2. 转小写并删除开头的 ★ 和空格
    # 优化：使用正则删除开头所有非字母数字的特殊符号
    text = re.sub(r'^[★☆◆◇\s]+', '', text.lower())
    
    # 3. 频道/特定词汇修正
    if 'news24' in text:
        text = re.sub(r'news24', 'ne24', text, flags=re.IGNORECASE)
    
    # 4. 删除年份
    text = re.sub(r'\s?(19|20)\d{2}', '', text)

    # 5. 删除括号备注
    text = re.sub(r'[\(\[].*?[\)\]]|【.*?】|（.*?）', '', text)
    
    # --- 新增：查漏补缺 (处理末尾残留标点) ---
    # 这一步会删除掉末尾所有的感叹号、问号、空格或特殊符号
    text = text.rstrip('!！?？. 。★ \t\n')

    # 6. 横杠截断
    text = text.partition(" -")[0]

    # 7. 删除文件系统禁忌符号
    text = text.replace(':', '')

    # 8. 格式化
    text = text.strip()
    if text:
        # 兼容只有一个字符的情况
        text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
        
    return text

def process_image(src_path, dst_path):
    """高级处理：用原图做模糊背景，解决 16:9 变 2:3 的变形问题"""
    try:
        with Image.open(src_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 定义机顶盒竖向框尺寸 2:3
            target_w, target_h = 320, 480 
            
            # --- 1. 制作背景：原图拉伸铺满并重度模糊 ---
            background = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            background = background.filter(ImageFilter.GaussianBlur(radius=25)) 
            
            # --- 2. 制作前景：等比例缩放原图，宽度撑满 320 ---
            scale_w = target_w
            scale_h = int(img.height * (target_w / img.width))
            img_foreground = img.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
            
            # --- 3. 叠加：居中贴图 ---
            y_offset = (target_h - scale_h) // 2
            background.paste(img_foreground, (0, y_offset))

            # --- 4. 递归压缩确保 < 70KB ---
            quality = 85
            background.save(dst_path, "JPEG", quality=quality, optimize=True)
            while os.path.getsize(dst_path) > 70 * 1024 and quality > 30:
                quality -= 10
                background.save(dst_path, "JPEG", quality=quality, optimize=True)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    src_dir = "posters_raw" 
    dst_dir = "posters_final"
    os.makedirs(dst_dir, exist_ok=True)
    
    for root, dirs, files in os.walk(src_dir):
        for filename in files:
            if filename.startswith('.'): continue
            if filename.lower().endswith(('.jpg', '.png', '.jpeg')):
                name_part = os.path.splitext(filename)[0]
                new_name = fury_standard_clean(name_part)
                
                dst_path = os.path.join(dst_dir, f"{new_name}.jpg")
                src_path = os.path.join(root, filename)
                
                if process_image(src_path, dst_path):
                    print(f"Standardized: {new_name}.jpg")

if __name__ == "__main__":
    main()
