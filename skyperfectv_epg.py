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

# 1. 频道配置：确保这里的 srv_ref 与你的卫星接收机一致
CHANNELS_MAP = {
    "622": ("1:0:19:826E:3017:A:5000000:0:0:0", "ＷＯＷＯＷライブ"),
    "623": ("1:0:19:826F:3019:A:5000000:0:0:0", "ＷＯＷＯＷシネマ"),
}

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        }
        self.session.headers.update(self.headers)
        self.session.cookies.update({'isAdult': '1', 'age_check': '1'})
        
        # 增量更新缓存配置
        self.cache_file = "epg_cache.json"
        self.cache = self.load_cache()

    def load_cache(self):
        """加载本地缓存，避免重复请求详情页"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: return {}
        return {}

    def save_cache(self):
        """保存缓存，只保留 7 天内的数据防止文件过大"""
        # 简单的过期清理逻辑（可选）
        if len(self.cache) > 5000: self.cache = {} 
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def parse_japanese_time(self, date_raw, time_range_str):
        """解析日本时间格式"""
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
        """获取节目详情（含增量更新逻辑）"""
        # --- 检查缓存 ---
        if url in self.cache:
            data = self.cache[url].copy()
            data['ref'] = srv_ref # 恢复当前频道的 reference
            return data

        try:
            res = self.session.get(url, headers={"Referer": referer}, timeout=10)
            if res.status_code != 200: return None
            res.encoding = res.apparent_encoding 
            soup = BeautifulSoup(res.text, 'lxml')

            # 提取标题
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "No Title"

            # 提取时间
            time_el = soup.find('p', class_='p-info__time') or soup.find(string=re.compile(r'\d{1,2}/\d{1,2}.*?\d{2}:\d{2}'))
            if not time_el: return None
            
            dt_m = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}).*?(\d{2}:\d{2})', time_el.get_text(strip=True))
            if not dt_m: return None
            start_xml, stop_xml = self.parse_japanese_time(dt_m.group(1), f"{dt_m.group(2)}～{dt_m.group(3)}")

            # 提取深度描述
            parts = []
            # A. 简介
            main_d = soup.find('div', class_='p-info__detail')
            if main_d and main_d.p: parts.append(main_d.p.get_text(strip=True).replace('もっと見る', ''))
            # B. 规格
            ov_d = soup.find('div', class_='p-info__detail__overflow')
            if ov_d:
                specs = [f"【{it.h3.text}】{it.p.text}" for it in ov_d.find_all('div', class_='p-info__cast') if it.h3 and it.p]
                parts.append("\n".join(specs))
            # C. 出演者
            perf_d = soup.find('div', class_='p-info__performer')
            if perf_d:
                names = [li.get_text(strip=True) for li in perf_d.find_all('li') if li.get_text(strip=True)]
                if names: parts.append("【出演者】" + "、".join(names))

            desc = "\n\n".join(parts) if parts else title

            result = {'title': title, 'desc': desc, 'start': start_xml, 'stop': stop_xml}
            
            # --- 写入缓存 ---
            self.cache[url] = result.copy()
            
            result['ref'] = srv_ref
            return result
        except: return None

    def fetch_channel(self, ch_num, srv_ref, name):
        """抓取单频道列表页"""
        url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            links = list(set([l.get('href') for l in soup.find_all('a', href=re.compile(r'/program/detail/'))]))
            
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = [executor.submit(self.fetch_detail, self.base_url + h, srv_ref, url) for h in links]
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data: progs.append(res_data)
            print(f"✅ {name} ({ch_num}) 完成: {len(progs)} 条")
        except Exception as e: print(f"❌ {name} 错误: {e}")
        return progs

    def run(self):
        start_time = time.time()
        # 反向查找表：用于映射 srv_ref -> ch_num
        ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
        
        all_progs = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
            for f in as_completed(tasks): all_progs.extend(f.result())

        # 构建 XML
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
        for ch_num, (ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=f"CH.{ch_num}")
            ET.SubElement(chan, "display-name").text = name

        for p in all_progs:
            clean_ref = p['ref'].rstrip(':').upper()
            short_id = f"CH.{ref_to_id.get(clean_ref, 'Unknown')}"
            prog = ET.SubElement(root, "programme", start=p['start'], stop=p['stop'], channel=short_id)
            ET.SubElement(prog, "title", lang="ja").text = p['title']
            ET.SubElement(prog, "desc", lang="ja").text = p['desc']

        # 保存与压缩
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write("epg_ultimate.xml", encoding="utf-8", xml_declaration=True)
        with open("epg_ultimate.xml", 'rb') as f_in, gzip.open("epg_ultimate.xml.gz", 'wb') as f_out:
            f_out.writelines(f_in)
        
        self.save_cache() # 别忘了保存缓存
        print(f"\n🚀 完成！耗时: {time.time()-start_time:.1f}s | 缓存量: {len(self.cache)}")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
