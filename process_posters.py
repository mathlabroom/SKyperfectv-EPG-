import os
import re
import time
import ast
import hashlib
import shutil
from datetime import datetime
from PIL import Image, ImageFilter

# --- 获取 GitHub Actions 变量 ---
def get_fury_mapping():
    raw_var = os.getenv('FURY_ID', '{}').strip()
    print(f"DEBUG: Raw FURY_ID from env: '{raw_var}'")
    
    try:
        if '=' in raw_var:
            raw_var = raw_var.split('=', 1)[1].strip()
        
        mapping = ast.literal_eval(raw_var)
        print(f"DEBUG: Parsed mapping keys: {list(mapping.keys())}")
        return mapping
    except Exception as e:
        print(f"❌ 变量解析失败: {e}")
        return {}

FURY_MAP = get_fury_mapping()

def get_file_md5(file_path):
    """计算文件的 MD5 值"""
    hash_md = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md.update(chunk)
    return hash_md.hexdigest()

def main():
    raw_dir, final_dir = "posters_raw", "posters_final"
    os.makedirs(final_dir, exist_ok=True)
    
    if not os.path.exists(raw_dir):
        print(f"❌ 错误: 找不到目录 {raw_dir}")
        return

    files = os.listdir(raw_dir)
    print(f"DEBUG: Found {len(files)} files in {raw_dir}")

    # 用于去重的内存映射表 { "图片的MD5": "第一个成品的绝对路径" }
    processed_md5_map = {}

    for filename in files:
        # 匹配 CH.xxx_时间戳 格式
        match = re.search(r'(CH\.\d+)_(\d{12})', filename)
        
        if match:
            ch_tag, time_str = match.groups()
            f_hash = FURY_MAP.get(ch_tag)
            
            if not f_hash:
                continue

            try:
                # 转换时间戳 (JST to UTC/Unix)
                dt = datetime.strptime(time_str, "%Y%m%d%H%M")
                ts = int(time.mktime(dt.timetuple())) - 32400
                
                new_name = f"{f_hash}_{ts}.jpg"
                src_path = os.path.join(raw_dir, filename)
                dst_path = os.path.join(final_dir, new_name)

                # --- 核心去重逻辑 ---
                img_md5 = get_file_md5(src_path)

                if img_md5 in processed_md5_map:
                    # 如果内容重复，建立硬链接节省空间
                    src_master = processed_md5_map[img_md5]
                    if not os.path.exists(dst_path):
                        try:
                            os.link(src_master, dst_path)
                        except Exception:
                            shutil.copy2(src_master, dst_path)
                else:
                    # 第一次见到这个内容
                    try:
                        # 因为 skyperfectv_epg.py 已经处理过毛玻璃了，这里直接复制
                        shutil.copy2(src_path, dst_path)
                        # 记录这个成品路径，供后续重复的图使用
                        processed_md5_map[img_md5] = os.path.abspath(dst_path)
                    except Exception as e:
                        print(f"  ⚠️ 复制文件失败 {filename}: {e}")

            except Exception as e:
                print(f"❌ 处理文件逻辑出错 {filename}: {e}")

    print(f"✅ 处理完成。原始图片: {len(files)}, 实际去重后成品: {len(processed_md5_map)}")

if __name__ == "__main__":
    main()
