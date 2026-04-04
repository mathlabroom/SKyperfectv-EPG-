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

# 动态获取频道映射
def load_channels():
    raw_data = os.environ.get("CHANNELS_JSON")
    if raw_data:
        try:
            data = json.loads(raw_data)
            return {k: tuple(v) for k, v in data.items()}
        except Exception as e:
            print(f"❌ 环境变量 CHANNELS_JSON 解析出错: {e}")
    print("⚠️ 未发现有效的频道环境变量，请检查 GitHub Settings。")
    return {}

CHANNELS_MAP = load_channels()

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        }
        self.session.headers.update(self.headers)
        self.session.cookies.update({'isAdult': '1', 'age_check': '1', 'adult_auth': 'true'})
        
        self.cache_file = "epg_cache.json"
        self.lock = threading.Lock()
        self.cache = self.load_cache()

    # --- 🎯 核心增强：统一清洗逻辑 ---
    def ultimate_clean(self, text):
        if not text: return ""
        # 1. 全角转半角 (解决 １２３ vs 123)
        text = "".join([chr(ord(c) - 0xfee0) if 0xff01 <= ord(c) <= 0xff5e else c for c in text])
        text = text.replace('　', ' ') 
        
        # 2. 强力移除所有类型的括号及其内容 (解决 【無料】、(1)、[字]、(再) 等)
        text = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）', '', text)
        
        # 3. 移除开头和结尾的危险符号 (解决文件名以 ) 或 # 开头的问题)
        text = text.lstrip(')#★* ') 
        
        # 4. 彻底干掉中间的特殊符号、空格、点号和波浪号
        text = re.sub(r'[\s#★\*\.~～．,，]', '', text)
        
        # 5. 系统级非法字符清理 + 截断
        clean = re.sub(r'[\\/:*?"<>|]', '', text).strip()[:80]
        return clean if clean else "NoTitle"

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except: return {}
        return {}

    def save_cache(self):
        with self.lock:
            if len(self.cache) > 20000:
                self.cache = {k: v for i, (k, v) in enumerate(self.cache.items()) if i > 2000}
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 写入缓存失败: {e}")

    def parse_japanese_time(self, date_raw, time_range_str):
        try:
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_raw)
            if not date_match: return None, None
            month, day = int(date_match.group(1)), int(date_match.group(2))
            now = datetime.datetime.now()
            year = now.year
            if now.month == 12 and month == 1: year += 1
            base_dt = datetime.datetime(year, month, day)
            time_parts = re.findall(r'(\d{1,2}:\d{2})', time_range_str)
            if len(time_parts) < 2: return None, None
            start_hh, start_mm = map(int, time_parts[0].split(':'))
            end_hh, end_mm = map(int, time_parts[1].split(':'))
            start_dt = base_dt + timedelta(hours=start_hh, minutes=start_mm)
            end_dt = base_dt + timedelta(hours=end_hh, minutes=end_mm)
            if end_dt <= start_dt: end_dt += timedelta(days=1)
            return (start_dt.strftime("%Y%m%d%H%M00 +0900"), end_dt.strftime("%Y%m%d%H%M00 +0900"))
        except: return None, None

    def fetch_detail(self, url, srv_ref, referer, icon_url=None):
        if url in self.cache:
            data = self.cache[url].copy()
            if icon_url and 'icon' not in data:
                data['icon'] = icon_url
                with self.lock: self.cache[url]['icon'] = icon_url
            data['ref'] = srv_ref
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
            dt_m = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}).*?(\d{2}:\d{3})', time_el.get_text(strip=True))
            if not dt_m: 
                # 兼容不同格式的正则
                dt_m = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2})', time_el.get_text(strip=True))
                if not dt_m: return None
                start_xml, stop_xml = self.parse_japanese_time(dt_m.group(1), f"{dt_m.group(2)}～{dt_m.group(2)}")
            else:
                start_xml, stop_xml = self.parse_japanese_time(dt_m.group(1), f"{dt_m.group(2)}～{dt_m.group(3)}")

            parts = []
            main_d = soup.find('div', class_='p-info__detail')
            if main_d and main_d.p: parts.append(main_d.p.get_text(strip=True).replace('もっと見る', ''))
            
            desc = "\n\n".join(parts) if parts else title
            STOP_WORDS = ("【お知らせ","【料金案内", "詳細は", "◆視聴料金◆", "0120-")
            cutoff = len(desc)
            for word in STOP_WORDS:
                pos = desc.find(word)
                if pos != -1 and pos < cutoff: cutoff = pos
            desc = desc[:cutoff]

            lines = [l.strip() for l in desc.splitlines() if l.strip()]
            clean_desc = "\n".join(lines)
            clean_desc = "".join(c for c in clean_desc if c.isprintable() or c in "\n\r\t")
            
            result = {'title': title, 'desc': clean_desc, 'start': start_xml, 'stop': stop_xml, 'icon': icon_url}
            with self.lock: self.cache[url] = result.copy()
            result['ref'] = srv_ref
            return result
        except: return None

    def fetch_channel(self, ch_num, srv_ref, name):
        url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            items = soup.find_all('li', class_='p-program__item')
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                seen_urls = set()
                for item in items:
                    a_tag = item.find('a', class_='p-program__link')
                    if not a_tag: continue
                    full_url = self.base_url + a_tag.get('href')
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)
                    img_tag = item.find('img', class_='js-program_thumbnail')
                    icon_url = img_tag.get('data-lazysrc') if img_tag else None
                    futures.append(executor.submit(self.fetch_detail, full_url, srv_ref, url, icon_url))
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data: progs.append(res_data)
            print(f"✅ {name:<20} | 抓取完成: {len(progs)} 条")
        except Exception as e:
            print(f"❌ {name} 错误: {e}")
        return progs

    def download_to_zip(self, all_progs):
        poster_dir = "posters"
        zip_name = 'posters.zip'
        if not os.path.exists(poster_dir): os.makedirs(poster_dir)
        
        now = datetime.datetime.now()
        time_limit = now + timedelta(hours=24)

        def _down(p):
            title, url = p.get('title'), p.get('icon')
            start_time_raw = p.get('start')
            if not title or not url: return

            try:
                clean_start = start_time_raw.split(' ')[0]
                prog_time = datetime.datetime.strptime(clean_start[:14], "%Y%m%d%H%M%S")
                if not (now <= prog_time <= time_limit): return 
            except: return 

            # 🎯 使用统一清洗逻辑生成图片名
            clean_filename = self.ultimate_clean(title)
            path = os.path.join(poster_dir, f"{clean_filename}.jpg")
            
            if os.path.exists(path): return
            try:
                r = self.session.get(url, timeout=10) 
                if r.status_code == 200 and len(r.content) > 1024:
                    with open(path, 'wb') as f: f.write(r.content)
            except: pass

        print(f"📂 同步海报中...")
        with ThreadPoolExecutor(max_workers=50) as executor:
            executor.map(_down, all_progs)

        print(f"📦 打包 {zip_name}...")
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
            success_count = 0
            if os.path.exists(poster_dir):
                for file in os.listdir(poster_dir):
                    file_path = os.path.join(poster_dir, file)
                    z.write(file_path, file)
                    success_count += 1
            if success_count == 0: z.writestr("readme.txt", "No posters.")
        print(f"✅ 海报包完成，共 {success_count} 张")

    def run(self):
        file_name = "epg_ultimate.xml"
        start_time = time.time()
        icon_base = "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/m_{}.gif"
        ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
        all_progs = []
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
            for f in as_completed(tasks):
                res = f.result()
                if res: all_progs.extend(res)

        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
        
        # 频道头
        for ch_num, (ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=f"CH.{ch_num}")
            ET.SubElement(chan, "display-name").text = name
            channel_icon_url = icon_base.format(str(ch_num).zfill(3))
            ET.SubElement(chan, "icon", src=channel_icon_url)
        
        # 节目节点
        for p in all_progs:
            clean_ref = p['ref'].rstrip(':').upper()
            short_id_num = ref_to_id.get(clean_ref, 'Unknown')
            
            # 🎯 关键修改：XML 标题必须和图片名完全一致
            clean_display_title = self.ultimate_clean(p['title'])
            
            prog = ET.SubElement(root, "programme", channel=f"CH.{short_id_num}", start=p['start'], stop=p['stop'])
            ET.SubElement(prog, "title", lang="ja").text = clean_display_title

            if p.get('icon'):
                ET.SubElement(prog, "icon", src=p['icon'])
            
            if p.get('desc'):
                ET.SubElement(prog, "desc", lang="ja").text = p['desc']

        # 排序与保存
        programmes_nodes = root.findall('programme')
        programmes_nodes.sort(key=lambda x: (x.get('channel', ''), x.get('start', '')))
        root[:] = root.findall('channel') + programmes_nodes

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(file_name, encoding="utf-8", xml_declaration=True)
        
        with open(file_name, 'rb') as f_in, gzip.open(f"{file_name}.gz", 'wb') as f_out:
            f_out.writelines(f_in)
        
        self.download_to_zip(all_progs)
        self.save_cache()
        print(f"⏱️ 总耗时: {time.time()-start_time:.1f}s")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
