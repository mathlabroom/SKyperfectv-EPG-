import os
import re
import unicodedata
import time
from datetime import datetime
from PIL import Image, ImageFilter

# 1. 你刚创建的变量 (这里只列出几个作为演示，请把你的完整列表贴进来)
FURY_ID = {
    "8206": "12bb2f5c88f1", # CH.518
    "8209": "4e7b73121841", # CH.521
    "8220": "a6ee7834c3b9", # CH.544
    "823C": "ebc40e38b9bb", # CH.572
    # ... 剩下的直接粘贴在这里 ...
}

def get_fury_name(sid, sky_time_str):
    """
    根据 SID 和 Sky 时间字符串生成最终文件名
    sky_time_str 格式假设为: 202604051800 (12位)
    """
    fury_hash = FURY_ID.get(sid.upper())
    if not fury_hash:
        return None
    
    try:
        # 将时间转为 Unix 时间戳
        dt = datetime.strptime(sky_time_str[:12], "%Y%m%d%H%M")
        timestamp = int(time.mktime(dt.timetuple()))
        return f"{fury_hash}_{timestamp}"
    except Exception:
        return None

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
            if filename.startswith('.') or not filename.lower().endswith(('.jpg', '.png')):
                continue
            
            # 假设你的文件名格式是 "CH.518_202604051800.jpg"
            # 如果不是这个格式，请修改下面的正则匹配
            match = re.search(r'(CH\.\d+)_(\d{12})', filename)
            
            if match:
                ch_tag = match.group(1)
                time_part = match.group(2)
                
                new_base = get_fury_filename(ch_tag, time_part)
                
                if new_base:
                    src_path = os.path.join(root, filename)
                    dst_path = os.path.join(dst_dir, f"{new_base}.jpg")
                    
                    if process_image(src_path, dst_path):
                        print(f"Matched: {ch_tag} -> {new_base}.jpg")
                    continue
            else:
                # 如果没匹配到 SID 格式，走你之前的标题清洗逻辑作为备选
                name_part = os.path.splitext(filename)[0]
                clean_name = fury_standard_clean(name_part)
                # ... 处理逻辑 ...

if __name__ == "__main__":
    main()
