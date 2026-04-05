import os
import re
import unicodedata
import shutil
from PIL import Image

def fury_standard_clean(raw_title):
    # 1. Unicode 归一化 (解决日文字符不匹配)
    text = unicodedata.normalize('NFC', raw_title)
    # 2. 频道名特殊修正 (NEWS24 -> ne24)
    if 'news24' in text.lower():
        text = re.sub(r'news24', 'ne24', text, flags=re.IGNORECASE)
    # 3. 基础清洗与年份切除
    text = text.lower()
    text = re.sub(r'\s?(19|20)\d{2}', '', text)
    # 4. 末尾符号清理
    while text.endswith('!') or text.endswith('！'):
        text = text[:-1]
    if text.endswith('」'):
        text = text[:-1]
    # 5. 符号与括号处理 (删除内容)
    text = text.replace(':', '')
    text = re.sub(r'[\(\[].*?[\)\]]|【.*?】|（.*?）', '', text)
    # 6. 横杠截断
    text = text.partition(" -")[0]
    # 7. 首字母大写并清理空格
    return text.strip().capitalize()

def process_image(src_path, dst_path):
    """关键逻辑：将横图放入竖向黑底板，防止拉伸变形"""
    try:
        with Image.open(src_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # --- 补黑边逻辑：适配机顶盒 2:3 竖屏框 ---
            # 我们把目标定为 320x480 (这是最稳的竖向尺寸)
            target_w, target_h = 320, 480 
            
            # 第一步：等比例缩放原图，让宽度撑满 320
            # 缩放后的高度 = 320 / (原图宽/高)
            scale_w = target_w
            scale_h = int(img.height * (target_w / img.width))
            img_resized = img.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
            
            # 第二步：创建纯黑底板
            final_img = Image.new('RGB', (target_w, target_h), (0, 0, 0))
            
            # 第三步：将横向图贴在黑底中间 (计算 y 轴偏移量)
            y_offset = (target_h - scale_h) // 2
            final_img.paste(img_resized, (0, y_offset))

            # --- 递归压缩确保 < 70KB (亮图底线) ---
            quality = 90
            final_img.save(dst_path, "JPEG", quality=quality, optimize=True)
            while os.path.getsize(dst_path) > 70 * 1024 and quality > 30:
                quality -= 10
                final_img.save(dst_path, "JPEG", quality=quality, optimize=True)
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
                process_image(src_path, dst_path)
    print("所有海报处理完成！")

if __name__ == "__main__":
    main()
