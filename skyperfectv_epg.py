import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re
import gzip
import os
import json
import threading
import zipfile
import hashlib

def load_channels():
    # 从 GitHub Actions 注入的环境变量中读取
    raw_data = os.environ.get("CHANNELS_JSON")
    if raw_data:
        try:
            # JSON 只能存列表 []，读取后转回元组 () 以保持原有逻辑兼容
            data = json.loads(raw_data)
            return {k: tuple(v) for k, v in data.items()}
        except Exception as e:
            print(f"❌ 环境变量 CHANNELS_JSON 解析出错: {e}")
    
    # 如果变量不存在或解析失败，返回一个空字典或报错提示
    print("⚠️ 未发现有效的频道环境变量，请检查 GitHub Settings。")
    return {}

CHANNELS_MAP = load_channels()

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."}
        self.session.headers.update(self.headers)
        self.session.cookies.update({'isAdult': '1', 'age_check': '1', 'adult_auth': 'true'})
        self.cache_file = "epg_cache.json"
        self.lock = threading.Lock()
        
        self.cache = self.load_cache()  # 加载历史数据
        self.new_cache = {}            # 核心：仅存放本次命中或新抓取的数据

    def ultimate_clean(self, text):
    if not text: return ""
    
    # 1. 预处理：全角空格换成半角空格（保持 E2 皮肤显示的间距一致性）
    text = text.replace('　', ' ')
    
    # 2. 删除空行：保留有文字的行，删除纯空白行
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)
    
    # 3. 过滤掉 E2 不喜欢的控制字符，但保留换行符 \n
    # 这样在 E2 的节目单详情里，描述依然是有分段的，不会糊成一团
    clean = "".join(c for c in text if c.isprintable() or c == "\n")
    
    # 4. 长度限制：E2 标题一般建议 100 字符以内，描述可以长点
    return clean[:255].strip() if clean else "NoTitle"

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"📂 已载入历史缓存: {len(data)} 条记录")
                    return data
            except: return {}
        return {}

    def save_cache(self, final=False):
        """增强版保存逻辑：支持中间进度显示和最终大扫除"""
        with self.lock:
            if not final:
                # --- 中间进度统计 ---
                current_keys = set(self.new_cache.keys())
                old_keys = set(self.cache.keys())
                real_hit = len(current_keys & old_keys)
                real_new = len(current_keys - old_keys)
                print(f"📊 [实时进度] 当前已扫描命中: {real_hit} | 本次新抓: {real_new}")
            else:
                # --- 最终大扫除逻辑 ---
                jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
                now_str = (jst_now - datetime.timedelta(hours=2)).strftime("%Y%m%d%H%M%S")
                
                old_keys = set(self.cache.keys())
                hit_keys = set(self.new_cache.keys())
                
                compensate_count = 0
                for url, info in self.cache.items():
                    if url not in hit_keys:
                        stop_val = info.get('stop', '00000000000000').split(' ')[0]
                        if stop_val > now_str:
                            self.new_cache[url] = info
                            compensate_count += 1
                
                final_keys = set(self.new_cache.keys())
                dropped_count = len(old_keys - final_keys)
                
                # 正式替换内存中的缓存
                self.cache = self.new_cache.copy()
                
                print("-" * 30)
                print(f"📊 最终缓存重构报告:")
                print(f"   - 总计扫描覆盖: {len(hit_keys)} 条")
                print(f"   - 自动补偿保留: {compensate_count} 条")
                print(f"   - 彻底清理过期: {dropped_count} 条")
                print(f"   - 最终缓存总量: {len(self.cache)} 条")
                print("-" * 30)

            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.new_cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 写入缓存文件失败: {e}")

    def parse_japanese_time(self, date_raw, time_range_str):
        try:
            # 1. 提取月/日
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_raw)
            if not date_match: return None, None
            month, day = int(date_match.group(1)), int(date_match.group(2))
            
            # 2. 强制使用日本时区确定年份，防止 GitHub 服务器时差导致跨年失败
            # JST 是 UTC+9
            jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
            year = jst_now.year
            
            # 核心跨年逻辑：如果现在是 12 月，抓到的是 1 月，年份 +1
            if jst_now.month == 12 and month == 1:
                year += 1
            # 防御逻辑：如果现在是 1 月，抓到的是 12 月（历史数据），年份 -1
            elif jst_now.month == 1 and month == 12:
                year -= 1
                
            base_dt = datetime.datetime(year, month, day)

            # 3. 提取时间
            time_parts = re.findall(r'(\d{1,2}:\d{2})', time_range_str)
            if len(time_parts) < 2: return None, None
            
            sh, sm = map(int, time_parts[0].split(':'))
            eh, em = map(int, time_parts[1].split(':'))
            
            # 4. 使用 timedelta 替代 replace，这样即使 sh >= 24 也能自动进位，更稳健
            start_dt = base_dt + datetime.timedelta(hours=sh, minutes=sm)
            end_dt = base_dt + datetime.timedelta(hours=eh, minutes=em)
            
            # 5. 处理跨子夜 (例如 23:00 ～ 01:00)
            if sh > eh:
                end_dt += datetime.timedelta(days=1)
                
            return (start_dt.strftime("%Y%m%d%H%M00 +0900"), 
                    end_dt.strftime("%Y%m%d%H%M00 +0900"))
        except:
            return None, None

    def fetch_detail(self, url, srv_ref, referer, icon_url, ch_num):
        # 1. 优先查旧缓存 (命中逻辑)
        if url in self.cache:
            data = self.cache[url].copy()
            data['ref'] = srv_ref
            data['ch_num'] = ch_num
            if icon_url and not data.get('icon'):
                data['icon'] = icon_url
            
            # ✨ 只要命中了，就存入 new_cache 确保它在 save_cache 时不被丢弃
            with self.lock:
                self.new_cache[url] = self.cache[url]
            return data
        try:
            res = self.session.get(url, headers={"Referer": referer}, timeout=10)
            if res.status_code != 200: return None
            res.encoding = res.apparent_encoding 
            soup = BeautifulSoup(res.text, 'lxml')

            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "No Title"

            time_el = soup.find('p', class_='p-info__time') or soup.find(string=re.compile(r'\d{1,2}/\d{1,2}.*?\d{2}:\d{2}'))
            if not time_el: return None
            
            raw_time_text = time_el.get_text(strip=True)
            date_match = re.search(r'(\d{1,2}/\d{1,2})', raw_time_text)
            if not date_match: return None
            date_raw = date_match.group(1)
            
            search_area = raw_time_text[date_match.end() : date_match.end() + 35]
            times = re.findall(r'(\d{1,2}:\d{2})', search_area)
            if len(times) < 2: return None
            
            start_xml, stop_xml = self.parse_japanese_time(date_raw, f"{times[0]}～{times[1]}")
            
            # 描述清洗逻辑
            parts = []
            main_d = soup.find('div', class_='p-info__detail')
            if main_d and main_d.p: parts.append(main_d.p.get_text(strip=True).replace('もっと見る', ''))
            ov_d = soup.find('div', class_='p-info__detail__overflow')
            if ov_d:
                specs = [f"【{it.h3.text}】{it.p.text}" for it in ov_d.find_all('div', class_='p-info__cast') if it.h3 and it.p]
                parts.append("\n".join(specs))
            perf_d = soup.find('div', class_='p-info__performer')
            if perf_d:
                names = [li.get_text(strip=True) for li in perf_d.find_all('li') if li.get_text(strip=True)]
                if names: parts.append("【出演者】" + "、".join(names))

            desc = "\n\n".join(parts) if parts else title
            STOP_WORDS = ("【お知らせ","お知らせ",  "【料金案内", "料金案内", "【■セットご案内", "【■セット案内", "詳細は", "◆視聴料金◆", "◆オススメ◆", "公式HP", "0120-")
            cutoff = len(desc)
            for word in STOP_WORDS:
                pos = desc.find(word)
                if pos != -1 and pos < cutoff: cutoff = pos
            desc = desc[:cutoff]

            lines = [l.strip() for l in desc.splitlines() if l.strip()]
            clean_desc = "".join(c for c in "\n".join(lines) if c.isprintable() or c in "\n\r\t")
            
            result = {
                'title': title, 
                'desc': clean_desc, 
                'start': start_xml, 
                'stop': stop_xml,
                'icon': icon_url,
                'ch_num': ch_num,
                'ref': srv_ref
            }
            
            # ✨ 新抓取的存入 new_cache
            with self.lock:
                self.new_cache[url] = result.copy()
            
            return result
        except: return None

    def fetch_channel(self, ch_num, srv_ref, name):
        url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        print(f"⏳ 正在同步: {name:<20} (ID: {ch_num})", flush=True)
        
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            items = soup.find_all('li', class_='p-program__item')
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                seen_urls = set()
                cached_count = 0
                
                for item in items:
                    a_tag = item.find('a', class_='p-program__link')
                    if not a_tag: continue
                    href = a_tag.get('href')
                    full_url = self.base_url + href
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)

                    img_tag = item.find('img', class_='js-program_thumbnail')
                    icon_url = img_tag.get('data-lazysrc') if img_tag else None

                    if full_url in self.cache: cached_count += 1
                    futures.append(executor.submit(self.fetch_detail, full_url, srv_ref, url, icon_url, ch_num))
                
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data: progs.append(res_data)
            
            new_fetched = len(seen_urls) - cached_count
            print(f"✅ {name:<20} | 总计: {len(progs):>2} | 缓存: {cached_count:>2} | 新抓: {new_fetched:>2}", flush=True)
            
        except Exception as e:
            print(f"❌ {name:<20} 发生错误: {e}", flush=True)
            
        return progs
            
    def download_to_zip(self, all_progs):
        import os
        import datetime
        import zipfile
        import hashlib
        from io import BytesIO
        from PIL import Image, ImageFilter
        from concurrent.futures import ThreadPoolExecutor

        poster_dir = "posters"
        zip_name = "posters.zip"
        if not os.path.exists(poster_dir): os.makedirs(poster_dir)
        
        # 建立一个内存中的 MD5 映射表，用于追踪已处理的图片内容
        # 格式: { md5: 磁盘上的第一个文件名 }
        processed_md5_map = {}
        md5_lock = threading.Lock()

        now = datetime.datetime.now()
        time_limit = datetime.timedelta(hours=48)

        def _process_and_save(image_content, target_path):
            try:
                with Image.open(BytesIO(image_content)) as img:
                    img = img.convert('RGB')
                    target_w, target_h = 320, 480
                    bg = img.resize((target_w, target_h), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=25))
                    scale_h = int(img.height * (target_w / img.width))
                    fg = img.resize((target_w, scale_h), Image.Resampling.LANCZOS)
                    bg.paste(fg, (0, (target_h - scale_h) // 2))
                    bg.save(target_path, "JPEG", quality=85, optimize=True)
                return True
            except: return False

        def _down(p):
            url = p.get('icon')
            start_raw = p.get('start') 
            ch_num = p.get('ch_num') 
            if not url or not start_raw or not ch_num: return
            
            try:
                time_digits = "".join(filter(str.isdigit, start_raw))[:12]
                prog_time = datetime.datetime.strptime(time_digits, "%Y%m%d%H%M")
                if abs((now - prog_time).total_seconds()) > (time_limit.total_seconds() + 28800):
                    return 

                filename = f"CH.{ch_num}_{time_digits}.jpg"
                path = os.path.join(poster_dir, filename)
                if os.path.exists(path): return
                
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    # 1. 计算原始图片的 MD5
                    raw_md5 = hashlib.md5(r.content).hexdigest()
                    
                    with md5_lock:
                        if raw_md5 in processed_md5_map:
                            # 2. 如果内容已存在，尝试创建硬链接
                            src_file = os.path.abspath(processed_md5_map[raw_md5])
                            dst_file = os.path.abspath(path)
                            if not os.path.exists(dst_file):
                                try:
                                    os.link(src_file, dst_file)
                                except:
                                    # 如果硬链接失败（比如跨文件系统），则重新处理保存一份
                                    _process_and_save(r.content, path)
                        else:
                            # 3. 第一次见到，进行毛玻璃处理并保存
                            if _process_and_save(r.content, path):
                                processed_md5_map[raw_md5] = path
            except Exception as e:
                # 外层 try 的闭合
                pass

        valid_progs = [p for p in all_progs if p and p.get('icon') and p.get('ch_num') and p.get('start')]
        unique_progs = { (p['ch_num'], p['start']): p for p in valid_progs }.values()

        print(f"🚀 开始处理海报（含毛玻璃与硬链接去重）目标: {len(unique_progs)}...")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(_down, unique_progs)
        
        # 打包逻辑
        if os.path.exists(poster_dir) and os.listdir(poster_dir):
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in os.listdir(poster_dir):
                    z.write(os.path.join(poster_dir, file), file)
            print(f"📦 打包完成: {zip_name} (含 {len(os.listdir(poster_dir))} 文件)")
            
    def run(self):
        max_tries = 3
        # ✨ 关键：在循环外初始化，用于跨轮次对比
        last_scan_count = 0 
        all_progs = []
        
        for i in range(max_tries):
            print(f"\n🔄 开始第 {i+1}/{max_tries} 轮 EPG 扫描...")
            ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
            # 每一轮清空 all_progs，因为 fetch_channel 会重新跑全量或补漏
            all_progs = [] 
            count = 0
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
                for f in as_completed(tasks):
                    try:
                        result = f.result()
                        if result:
                            with self.lock: all_progs.extend(result)
                            count += 1
                            if count % 5 == 0: self.save_cache(final=False)
                    except Exception as e: 
                        print(f"⚠️ 频道抓取异常: {e}")

            current_scan_count = len(self.new_cache)
            new_records_this_round = current_scan_count - last_scan_count
            
            # 记录本次扫描到的总量，供下一轮对比
            last_scan_count = current_scan_count

            if i < max_tries - 1:
                if new_records_this_round > 0:
                    print(f"✨ 本轮有效扫描/新增 {new_records_this_round} 条，准备下一轮补漏...")
                    time.sleep(5)
                else:
                    print("✅ 扫描数据已对齐，无需更多重试。")
                    break
                    
        self.save_cache(final=True)
        
        # 构建 XML 与保存
        file_name = "epg_ultimate.xml" 
        start_time = time.time()
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})

        # 先添加频道定义
        for ch_num, (ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=f"CH.{ch_num}")
            ET.SubElement(chan, "display-name").text = name
            ET.SubElement(chan, "icon", src=f"https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/m_{ch_num}.gif")
        
        # 添加节目详情
        for p in all_progs:
            clean_ref = p['ref'].rstrip(':').upper()
            short_id_num = ref_to_id.get(clean_ref, p.get('ch_num', 'Unknown'))
            prog = ET.SubElement(root, "programme", channel=f"CH.{short_id_num}", start=p['start'], stop=p['stop'])
            ET.SubElement(prog, "title", lang="ja").text = p['title'].strip() if p['title'] else "No Title"
            if p.get('icon'): ET.SubElement(prog, "icon", src=p['icon'])
            if p.get('desc'): ET.SubElement(prog, "desc", lang="ja").text = p.get('desc')

        # 排序
        programmes = root.findall('programme')
        programmes.sort(key=lambda x: (x.get('channel', ''), x.get('start', '')))
        root[len(CHANNELS_MAP):] = programmes

        # 写入文件
        self.save_cache()
        tree = ET.ElementTree(root)
        if hasattr(ET, 'indent'): ET.indent(tree, space="  ")
        tree.write(file_name, encoding="utf-8", xml_declaration=True)
        
        # Gzip 压缩
        with open(file_name, 'rb') as f_in, gzip.open(f"{file_name}.gz", 'wb') as f_out:
            f_out.writelines(f_in)

        # 处理海报并生成 Zip
        self.download_to_zip(all_progs)
        print(f"\n🚀 任务完成！耗时: {time.time()-start_time:.1f}s | 最终库: {len(self.cache)}")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
