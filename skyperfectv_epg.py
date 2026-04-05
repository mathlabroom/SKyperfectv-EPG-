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

def load_channels():
    raw_data = os.environ.get("CHANNELS_JSON")
    if raw_data:
        try:
            data = json.loads(raw_data)
            return {k: tuple(v) for k, v in data.items()}
        except Exception as e:
            print(f"❌ CHANNELS_JSON 解析出错: {e}")
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
        self.cache = self.load_cache()

    def ultimate_clean(self, text):
        if not text: return ""
        text = "".join([chr(ord(c) - 0xfee0) if 0xff01 <= ord(c) <= 0xff5e else c for c in text])
        text = text.replace('　', ' ')
        text = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）', '', text)
        text = text.lstrip(')#★* ').replace(' ', '')
        clean = re.sub(r'[\\/:*?"<>|#★\*\.~～．,，]', '', text).strip()[:80]
        return clean if clean else "NoTitle"

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f: return json.load(f)
            except: return {}
        return {}

    def save_cache(self):
        with self.lock:
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
            except: pass

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
            start_hh, start_mm = map(int, time_parts[0].split(':'))
            end_hh, end_mm = map(int, time_parts[1].split(':'))
            start_dt = base_dt + timedelta(hours=start_hh, minutes=start_mm)
            end_dt = base_dt + timedelta(hours=end_hh, minutes=end_mm)
            if end_dt <= start_dt: end_dt += timedelta(days=1)
            return (start_dt.strftime("%Y%m%d%H%M00 +0900"), end_dt.strftime("%Y%m%d%H%M00 +0900"))
        except: return None, None

    def fetch_detail(self, url, srv_ref, referer, icon_url, ch_num):
        if url in self.cache:
            data = self.cache[url].copy()
            data['ref'] = srv_ref
            data['ch_num'] = ch_num
            return data
        try:
            res = self.session.get(url, headers={"Referer": referer}, timeout=10)
            res.encoding = res.apparent_encoding 
            soup = BeautifulSoup(res.text, 'lxml')
            title = soup.find('h1').get_text(strip=True) if soup.find('h1') else "No Title"
            time_el = soup.find('p', class_='p-info__time')
            dt_m = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}).*?(\d{2}:\d{2})', time_el.get_text(strip=True))
            start_xml, stop_xml = self.parse_japanese_time(dt_m.group(1), f"{dt_m.group(2)}～{dt_m.group(3)}")
            result = {'title': title, 'start': start_xml, 'stop': stop_xml, 'icon': icon_url, 'ch_num': ch_num}
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
                for item in items:
                    a_tag = item.find('a', class_='p-program__link')
                    if not a_tag: continue
                    full_url = self.base_url + a_tag.get('href')
                    img_tag = item.find('img', class_='js-program_thumbnail')
                    icon_url = img_tag.get('data-lazysrc') if img_tag else None
                    futures.append(executor.submit(self.fetch_detail, full_url, srv_ref, url, icon_url, ch_num))
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data: progs.append(res_data)
            print(f"✅ {name} 抓取完成")
        except: pass
        return progs

    def download_to_zip(self, all_progs):
        poster_dir = "posters"
        if not os.path.exists(poster_dir): os.makedirs(poster_dir)
        now = datetime.datetime.now()
        
        def _down(p):
            url, start_raw, ch_num = p.get('icon'), p.get('start'), p.get('ch_num')
            if not url or not start_raw: return
            try:
                time_tag = start_raw.split(' ')[0][:12] # 202604051800
                filename = f"CH.{ch_num}_{time_tag}.jpg"
                path = os.path.join(poster_dir, filename)
                if os.path.exists(path): return
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    with open(path, 'wb') as f: f.write(r.content)
            except: pass

        with ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(_down, all_progs)
        
        with zipfile.ZipFile('posters.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for file in os.listdir(poster_dir):
                z.write(os.path.join(poster_dir, file), file)

    def run(self):
        all_progs = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
            for f in as_completed(tasks): all_progs.extend(f.result())
        
        root = ET.Element("tv")
        for p in all_progs:
            prog = ET.SubElement(root, "programme", channel=f"CH.{p['ch_num']}", start=p['start'], stop=p['stop'])
            ET.SubElement(prog, "title", lang="ja").text = self.ultimate_clean(p['title'])
        
        tree = ET.ElementTree(root)
        tree.write("epg_ultimate.xml", encoding="utf-8", xml_declaration=True)
        with open("epg_ultimate.xml", 'rb') as f_in, gzip.open("epg_ultimate.xml.gz", 'wb') as f_out:
            f_out.writelines(f_in)
            
        self.download_to_zip(all_progs)
        self.save_cache()

if __name__ == "__main__":
    SkyPerfectUltimate().run()
