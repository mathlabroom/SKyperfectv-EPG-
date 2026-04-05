import os
import re
import time
import ast
from datetime import datetime
from PIL import Image, ImageFilter

# --- 获取 GitHub Actions 变量 ---
def get_fury_mapping():
    raw_var = os.getenv('FURY_ID', '{}')
    try:
        # 兼容 "FURY_ID = {..." 格式
        if 'FURY_ID =' in raw_var:
            raw_var = raw_var.split('=', 1)[1].strip()
        return ast.literal_eval(raw_var)
    except Exception as e:
        print(f"❌ 变量解析失败: {e}")
        return {}

FURY_MAP = get_fury_mapping()

def process_image(src_path, dst_path):
    """毛玻璃背景 + 2:3 比例 + 70KB 压缩"""
    try:
        with Image.open(src_path) as img:
            img = img.convert('RGB')
            target_w, target_h = 320, 480
            # 背景模糊
            bg = img.resize((target_w, target_h), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=25))
            # 前景比例缩放
            scale_h = int(img.height * (target_w / img.width))
            fg = img.resize((target_w, scale_h), Image.Resampling.LANCZOS)
            bg.paste(fg, (0, (target_h - scale_h) // 2))
            # 递归压缩
            q = 85
            bg.save(dst_path, "JPEG", quality=q, optimize=True)
            while os.path.getsize(dst_path) > 70 * 1024 and q > 30:
                q -= 10
                bg.save(dst_path, "JPEG", quality=q, optimize=True)
        return True
    except: return False

def main():
    raw_dir, final_dir = "posters_raw", "posters_final"
    os.makedirs(final_dir, exist_ok=True)
    
    for filename in os.listdir(raw_dir):
        # 匹配 CH.频道号_时间戳
        match = re.search(r'(CH\.\d+)_(\d{12})', filename)
        if match:
            ch_tag, time_str = match.groups()
            f_hash = FURY_MAP.get(ch_tag)
            
            if f_hash:
                try:
                    dt = datetime.strptime(time_str, "%Y%m%d%H%M")
                    ts = int(time.mktime(dt.timetuple()))
                    new_name = f"{f_hash}_{ts}.jpg"
                    
                    if process_image(os.path.join(raw_dir, filename), os.path.join(final_dir, new_name)):
                        print(f"✅ 转换完成: {new_name}")
                except: continue

if __name__ == "__main__":
    main()
