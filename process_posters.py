import os
import re
import unicodedata
from PIL import Image, ImageFilter  # 引入模糊滤镜

def fury_standard_clean(raw_title):
    # 1. Unicode 归一化 (核心：防止日文编码导致机顶盒蓝屏)
    text = unicodedata.normalize('NFC', raw_title)
    
    # 2. 转小写并删除开头的 ★ 和空格
    text = text.lower().lstrip('★ ')
    
    # 3. 频道/特定词汇修正
    if 'news24' in text:
        text = re.sub(r'news24', 'ne24', text, flags=re.IGNORECASE)
    
    # 4. 删除年份 (精准匹配数字，不伤及空格)
    text = re.sub(r'\s?(19|20)\d{2}', '', text)

    # 5. 删除括号备注 (【】 [] 等)
    text = re.sub(r'[\(\[].*?[\)\]]|【.*?】|（.*?）', '', text)
    
    # 6. 横杠截断
    text = text.partition(" -")[0]

    # 7. 删除文件系统禁忌符号：冒号
    text = text.replace(':', '')

    # 8. 格式化：只处理第一个字符大写，保留中间所有空格和符号 (∞, ●, !!)
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]
        
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
