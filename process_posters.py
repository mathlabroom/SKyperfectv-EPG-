import os
import re
import time
import ast
from datetime import datetime
from PIL import Image, ImageFilter

# --- 获取 GitHub Actions 变量 ---
def get_fury_mapping():
    raw_var = os.getenv('FURY_ID', '{}').strip()
    print(f"DEBUG: Raw FURY_ID from env: '{raw_var}'") # 确认环境变量是否真的传进来了
    
    try:
        # 强制清理：去掉可能的 FURY_ID = 前缀
        if '=' in raw_var:
            raw_var = raw_var.split('=', 1)[1].strip()
        
        # 尝试解析
        mapping = ast.literal_eval(raw_var)
        print(f"DEBUG: Parsed mapping keys: {list(mapping.keys())}")
        return mapping
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
    
    # 检查路径是否存在
    if not os.path.exists(raw_dir):
        print(f"❌ 错误: 找不到目录 {raw_dir}")
        return

    files = os.listdir(raw_dir)
    print(f"DEBUG: Found {len(files)} files in {raw_dir}")
    
    for filename in files:
        # 增加对后缀的检查，避免匹配到临时文件
        match = re.search(r'(CH\.\d+)_(\d{12})', filename)
        
        if match:
            ch_tag, time_str = match.groups()
            f_hash = FURY_MAP.get(ch_tag)
            
            if not f_hash:
                # print(f"DEBUG: No hash for {ch_tag}, skipping...")
                continue

            try:
                # 转换时间戳
                dt = datetime.strptime(time_str, "%Y%m%d%H%M")
                ts = int(time.mktime(dt.timetuple())) - 32400
                
                new_name = f"{f_hash}_{ts}.jpg"
                src_path = os.path.join(raw_dir, filename)
                dst_path = os.path.join(final_dir, new_name)

                if process_image(src_path, dst_path):
                    print(f"✅ 转换完成: {filename} -> {new_name}")
                else:
                    print(f"❌ 处理失败: {filename}")
                    
            except Exception as e:
                print(f"⚠️ 处理 {filename} 时出错: {e}")
                continue

if __name__ == "__main__":
    # 假设 FURY_MAP 和 process_image 已经定义
    main()
