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
import threading  # 引入锁机制

CHANNELS_MAP = {
    "623": ("1:0:19:826F:3019:A:5000000:0:0:0:", "ＷＯＷＯＷシネマ"),
    "625": ("1:0:19:8271:4032:A:4D80000:0:0:0:", "BS10プレミアム"),
    "628": ("1:0:19:8274:3018:A:5000000:0:0:0:", "衛星劇場"),
    "629": ("1:0:19:8275:4031:A:4D80000:0:0:0:", "東映チャンネル"),
    "630": ("1:0:19:8276:3020:A:5000000:0:0:0:", "ＷＯＷＯＷプラス 映画・ドラマ・スポーツ・音楽"),
    "631": ("1:0:19:8277:3014:A:5000000:0:0:0:", "ザ・シネマ"),
    "632": ("1:0:19:8278:3026:A:5000000:0:0:0:", "ムービープラス"),
    "633": ("1:0:19:8279:3014:A:5000000:0:0:0:", "映画・チャンネルNECO"),
    "634": ("1:0:19:827A:4031:A:4D80000:0:0:0:", "日本映画専門チャンネル"),
    "635": ("1:0:19:827B:3028:A:5000000:0:0:0:", "Ｖ☆パラダイス"),
    "636": ("1:0:19:827C:3018:A:5000000:0:0:0:", "エキサイティング・グランプリ"),
    "580": ("1:0:19:8244:4028:A:4D80000:0:0:0:", "スポーツライブ＋"),
    "584": ("1:0:19:8248:3019:A:5000000:0:0:0:", "スポーツライブ＋ ２"),
    "600": ("1:0:19:8258:3020:A:5000000:0:0:0:", "FIGHTING TV サムライ"),
    "601": ("1:0:19:8259:3020:A:5000000:0:0:0:", "ゴルフネットワーク"),
    "602": ("1:0:19:825A:3020:A:5000000:0:0:0:", "GAORA SPORTS"),
    "603": ("1:0:19:825B:3014:A:5000000:0:0:0:", "J SPORTS 1"),
    "604": ("1:0:19:825C:3018:A:5000000:0:0:0:", "J SPORTS 2"),
    "605": ("1:0:19:825D:3028:A:5000000:0:0:0:", "J SPORTS 4"),
    "606": ("1:0:19:825E:3026:A:5000000:0:0:0:", "J SPORTS 3"),
    "607": ("1:0:19:825F:3018:A:5000000:0:0:0:", "スカイA"),
}

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
        self.lock = threading.Lock() # 线程锁，解决缓存写入丢失问题
        self.cache = self.load_cache()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"📂 已载入历史缓存: {len(data)} 条记录")
                    return data
            except: return {}
        return {}

    def save_cache(self):
        """线程安全的保存逻辑"""
        with self.lock:
            # 清理过期缓存（超过 10 天的删除，防止文件无限增大）
            today = datetime.datetime.now()
            # 这里的简单清理仅作为示例，如果需要更复杂的清理可以根据时间戳判断
            if len(self.cache) > 10000:
                print("🧹 缓存过大，触发自动清理...")
                self.cache = {k: v for i, (k, v) in enumerate(self.cache.items()) if i > 2000}

            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 写入缓存文件失败: {e}")

    def parse_japanese_time(self, date_raw, time_range_str):
        # ... [解析逻辑保持不变] ...
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

    def fetch_detail(self, url, srv_ref, referer):
        # 1. 增量对比：如果 URL 在缓存中，直接返回，不再请求网络
        if url in self.cache:
            data = self.cache[url].copy()
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
            dt_m = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}).*?(\d{2}:\d{2})', time_el.get_text(strip=True))
            if not dt_m: return None
            start_xml, stop_xml = self.parse_japanese_time(dt_m.group(1), f"{dt_m.group(2)}～{dt_m.group(3)}")

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
            result = {'title': title, 'desc': desc, 'start': start_xml, 'stop': stop_xml}
            
            # --- 线程安全地写入缓存 ---
            with self.lock:
                self.cache[url] = result.copy()
            
            result['ref'] = srv_ref
            return result
        except: return None

    def fetch_channel(self, ch_num, srv_ref, name):
        url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            # 提取详情页链接
            links = list(set([l.get('href') for l in soup.find_all('a', href=re.compile(r'/program/detail/'))]))
            
            # 嵌套多线程抓取详情
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self.fetch_detail, self.base_url + h, srv_ref, url) for h in links]
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data: progs.append(res_data)
            
            print(f"✅ {name} ({ch_num}) 处理完成 (含缓存命中)")
        except Exception as e: print(f"❌ {name} 错误: {e}")
        return progs

    def run(self):
        start_time = time.time()
        ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
        all_progs = []
        count = 0
        
        # 1. 抓取任务
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
            for f in as_completed(tasks):
                try:
                    result = f.result()
                    if result:
                        all_progs.extend(result)
                        count += 1
                        if count % 5 == 0:
                            self.save_cache()
                            print(f"📡 已自动存档缓存，当前频道进度: {count}")
                except Exception as e:
                    print(f"⚠️ 频道抓取异常: {e}")

        # 2. 构建最终 XML
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
        
        # 添加频道头
        for ch_num, (ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=f"CH.{ch_num}")
            ET.SubElement(chan, "display-name").text = name

        # 添加节目详情
        for p in all_progs:
            clean_ref = p['ref'].rstrip(':').upper()
            short_id = f"CH.{ref_to_id.get(clean_ref, 'Unknown')}"
            prog = ET.SubElement(root, "programme", start=p['start'], stop=p['stop'], channel=short_id)
            ET.SubElement(prog, "title", lang="ja").text = p['title']
            ET.SubElement(prog, "desc", lang="ja").text = p['desc']
            # 加入 UID 标签，方便后续追踪
            # 虽然 XMLTV 标准没有专门的 uid 标签，但通常放入 <origin> 或自定义标签
            ET.SubElement(prog, "remark").text = "cached_item" 

        # 3. 落地保存
        self.save_cache()
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write("epg_ultimate.xml", encoding="utf-8", xml_declaration=True)
        
        with open("epg_ultimate.xml", 'rb') as f_in, gzip.open("epg_ultimate.xml.gz", 'wb') as f_out:
            f_out.writelines(f_in)
        
        print(f"\n🚀 全部任务完成！耗时: {time.time()-start_time:.1f}s | 最终缓存库总量: {len(self.cache)}")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
