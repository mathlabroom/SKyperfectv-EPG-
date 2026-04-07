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

def main():
    # skyperfectv_epg.py 生成的带毛玻璃的目录
    raw_dir = "posters" 
    # Fury 最终使用的目录
    final_dir = "posters_final" 
    os.makedirs(final_dir, exist_ok=True)

    if not os.path.exists(raw_dir):
        print(f"❌ 找不到原始海报目录: {raw_dir}")
        return

    files = os.listdir(raw_dir)
    print(f"🔗 开始为 Fury 皮肤创建硬链接，共 {len(files)} 个文件...")

    for filename in files:
        # 匹配 skyperfectv_epg.py 生成的格式: CH.518_202604050000.jpg
        match = re.search(r'(CH\.\d+)_(\d{12})', filename)
        
        if match:
            ch_tag, time_str = match.groups()
            f_hash = FURY_MAP.get(ch_tag) # 从环境变量获取 FURY ID
            
            if not f_hash:
                continue

            try:
                # 转换时间为 Unix 时间戳
                dt = datetime.strptime(time_str, "%Y%m%d%H%M")
                # 减去 32400 (9小时) 是为了对齐日本时区偏移，保持你原有的逻辑
                ts = int(time.mktime(dt.timetuple())) - 32400
                
                new_name = f"{f_hash}_{ts}.jpg"
                src_path = os.path.join(raw_dir, filename)
                dst_path = os.path.join(final_dir, new_name)

                # --- 核心改进：不再处理图片，只建立硬链接 ---
                if not os.path.exists(dst_path):
                    os.link(src_path, dst_path) # 瞬间完成
            except Exception as e:
                print(f"❌ 链接失败 {filename}: {e}")

    print(f"✅ Fury 适配包制作完成，已存放至 {final_dir}")

if __name__ == "__main__":
    main()
