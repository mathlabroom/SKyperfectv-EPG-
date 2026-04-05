import os
import re
import time
import ast  # 安全解析字符串为字典
from datetime import datetime
from PIL import Image, ImageFilter

# --- 从 GitHub Actions Variables 引用变量 ---
def get_mapping_from_env():
    raw_var = os.getenv('FURY_ID', '{}')
    try:
        # 如果你变量值里带了 "FURY_ID ="，需要先把它去掉
        if 'FURY_ID =' in raw_var:
            raw_var = raw_var.split('=', 1)[1].strip()
        
        # 将字符串解析成 Python 字典
        return ast.literal_eval(raw_var)
    except Exception as e:
        print(f"解析环境变量 FURY_ID 失败: {e}")
        return {}

FURY_ID = get_mapping_from_env()

def process_image(src_path, dst_path):
    """毛玻璃背景处理，解决 16:9 变 2:3 问题"""
    try:
        with Image.open(src_path) as img:
            img = img.convert('RGB') if img.mode != 'RGB' else img
            target_w, target_h = 320, 480 
            # 背景模糊
            bg = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=25)) 
            # 前景居中
            scale_h = int(img.height * (target_w / img.width))
            fg = img.resize((target_w, scale_h), Image.Resampling.LANCZOS)
            bg.paste(fg, (0, (target_h - scale_h) // 2))
            # 压缩确保 < 70KB
            bg.save(dst_path, "JPEG", quality=85, optimize=True)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    src_dir = "posters_raw"
    dst_dir = "posters_final"
    os.makedirs(dst_dir, exist_ok=True)
    
    for filename in os.listdir(src_dir):
        if not filename.lower().endswith(('.jpg', '.png')):
            continue
            
        # 匹配文件名：CH.***_时间戳
        match = re.search(r'(CH\.\d+)_(\d{12})', filename)
        
        if match:
            ch_tag, time_raw = match.groups()
            f_hash = FURY_ID.get(ch_tag)
            
            if f_hash:
                try:
                    # 计算 Unix 时间戳 (ab33c7ef0b07_1775448000)
                    dt = datetime.strptime(time_raw, "%Y%m%d%H%M")
                    ts = int(time.mktime(dt.timetuple()))
                    
                    new_name = f"{f_hash}_{ts}.jpg"
                    if process_image(os.path.join(src_dir, filename), os.path.join(dst_dir, new_name)):
                        print(f"Matched: {ch_tag} -> {new_name}")
                except:
                    continue

if __name__ == "__main__":
    main()
