import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import re
import gzip
import os

# 频道配置保持不变
CHANNELS_MAP = {
    "622": ("1:0:19:826E:3017:A:5000000:0:0:0:", "ＷＯＷＯＷライブ"),
}

class SkyPerfectUltimate:
    def __init__(self):
        # 使用 Session 复用 TCP 连接
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate",
        }
        self.auth_cookies = {
            'isAdult': '1', 'age_check': '1', 'skp_adult_view': '1', 'ST_ADULT_FLG': '1'
        }
        self.session.headers.update(self.headers)
        self.session.cookies.update(self.auth_cookies)

    def parse_japanese_time(self, date_raw, time_range_str):
        try:
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_raw)
            if not date_match: return None, None
            month, day = int(date_match.group(1)), int(date_match.group(2))
            now = datetime.datetime.now()
            year = now.year
            if now.month == 12 and month == 1: year += 1
            elif now.month == 1 and month == 12: year -= 1
            base_dt = datetime.datetime(year, month, day)
            time_parts = re.findall(r'(\d{1,2}:\d{2})', time_range_str)
            if len(time_parts) < 2: return None, None
            start_t, end_t = time_parts[0], time_parts[1]
            
            def get_actual_dt(hhmm, ref_date):
                hh, mm = map(int, hhmm.split(':'))
                return ref_date + timedelta(hours=hh, minutes=mm)

            start_dt = get_actual_dt(start_t, base_dt)
            end_dt = get_actual_dt(end_t, base_dt)
            if end_dt <= start_dt: end_dt += timedelta(days=1)
            return (start_dt.strftime("%Y%m%d%H%M00 +0900"), end_dt.strftime("%Y%m%d%H%M00 +0900"))
        except: return None, None

    def fetch_detail(self, url, srv_ref, referer):
        try:
            res = self.session.get(url, headers={"Referer": referer}, timeout=10)
            if res.status_code != 200: return None
            
            # 解决乱码问题（非常重要）
            res.encoding = res.apparent_encoding 
            html = res.text
            soup = BeautifulSoup(html, 'lxml')

            # 1. 抓取标题 (Title)
            # 先找 h1，没有就找 meta 里的标题
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                title = soup.find('meta', property='og:title')['content'].split('|')[0].strip()

            # 2. 抓取时间 (DateTime) - 增强版匹配
            # 不再单纯依赖正则，先找包含时间的 p 标签
            start_xml = stop_xml = None
            
            # 尝试在页面上找包含 "～" 且包含数字的时间块
            time_str = ""
            time_element = soup.find('p', class_='p-info__time') # 常见类名
            if not time_element:
                time_element = soup.find(string=re.compile(r'\d{1,2}/\d{1,2}.*?\d{2}:\d{2}'))

            if time_element:
                time_str = time_element.get_text(strip=True)
                # 兼容全角/半角括号和空格
                dt_match = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}).*?(\d{2}:\d{2})', time_str)
                if dt_match:
                    date_str = dt_match.group(1)
                    # 重新拼凑成 parse_japanese_time 喜欢的格式：21:00～23:10
                    time_range = f"{dt_match.group(2)}～{dt_match.group(3)}"
                    start_xml, stop_xml = self.parse_japanese_time(date_str, time_range)

            # 如果还是拿不到时间，这页没法生成 EPG，直接放弃
            if not start_xml:
                return None

            # 3. 抓取内容 (之前给你的增强版代码)
            desc_parts = []
            
            # A. 简介
            main_detail = soup.find('div', class_='p-info__detail')
            if main_detail and main_detail.p:
                desc_parts.append(main_detail.p.get_text(strip=True).replace('もっと見る', ''))

            # B. 规格详情 (举办日、实况等)
            overflow_div = soup.find('div', class_='p-info__detail__overflow')
            if overflow_div:
                specs = [f"【{it.h3.text}】{it.p.text}" for it in overflow_div.find_all('div', class_='p-info__cast') if it.h3 and it.p]
                desc_parts.append("\n".join(specs))

            # C. 出演者
            performer_div = soup.find('div', class_='p-info__performer')
            if performer_div:
                names = [li.get_text(strip=True) for li in performer_div.find_all('li') if li.get_text(strip=True)]
                if names: desc_parts.append("【出演者】" + "、".join(names))

            desc = "\n\n".join(desc_parts) if desc_parts else title

            return {
                'ref': srv_ref,
                'title': title,
                'desc': desc,
                'start': start_xml,
                'stop': stop_xml
            }
        except Exception:
            return None
            
    def fetch_channel(self, ch_num, srv_ref, name):
        channel_url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        try:
            res = self.session.get(channel_url, timeout=20)
            if "年齢確認" in res.text:
                gate_url = f"{self.base_url}/program/schedule/adult/gate.php?url={channel_url}"
                self.session.get(gate_url, timeout=10)
                res = self.session.get(channel_url, timeout=20)

            soup = BeautifulSoup(res.text, 'lxml')
            links = soup.find_all('a', href=re.compile(r'/program/detail/'))
            unique_hrefs = list(set([l.get('href') for l in links if l.get('href')]))
            
            # 详情页并发数可稍高
            with ThreadPoolExecutor(max_workers=25) as detail_executor:
                futures = [detail_executor.submit(self.fetch_detail, self.base_url + h, srv_ref, channel_url) for h in unique_hrefs]
                for f in as_completed(futures):
                    result = f.result()
                    if result: progs.append(result)
            
            print(f"✅ {name} ({ch_num}) 抓取完成: {len(progs)} 条", flush=True)
        except Exception as e:
            print(f"💥 {name} 异常: {e}", flush=True)
        return progs

    def run(self):
        start_global = time.time()
        all_results = []
        # 1. 并发抓取频道
        with ThreadPoolExecutor(max_workers=8) as executor:
            tasks = [executor.submit(self.fetch_channel, ch_num, srv_ref, name) for ch_num, (srv_ref, name) in CHANNELS_MAP.items()]
            for f in as_completed(tasks):
                all_results.extend(f.result())

       # 2. 构建 XML
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})

        # 创建一个反向查询字典，用来通过 Service Ref 找到 频道号
        # 假设 CHANNELS_MAP 结构是 {"622": ("1:0:19...", "NAME"), ...}
        ref_to_id = {v[0]: k for k, v in CHANNELS_MAP.items()}

        # 写入频道定义
        for ch_num, (srv_ref, name) in CHANNELS_MAP.items():
            chan_id = f"CH.{ch_num}" 
            chan = ET.SubElement(root, "channel", id=chan_id)
            ET.SubElement(chan, "display-name").text = name

        # 写入节目内容
        for p in all_results:
            # 核心修正：通过 p['ref'] 找到对应的频道号
            raw_ref = p['ref']
            # 如果 p['ref'] 结尾有冒号，记得去掉再查，否则匹配不到
            clean_ref = raw_ref.rstrip(':') 
    
            # 查找对应的简写 ID (如 CH.622)
            short_id = f"CH.{ref_to_id.get(clean_ref, 'Unknown')}"
    
            # 如果你在 fetch_detail 时已经直接传了频道号（如 "622"），则直接用：
            # short_id = f"CH.{p['ref']}"

            prog = ET.SubElement(root, "programme", 
                                 start=p['start'], 
                                 stop=p['stop'], 
                                 channel=short_id) # 这里必须是 CH.622
    
            ET.SubElement(prog, "title", lang="ja").text = p['title']
            ET.SubElement(prog, "desc", lang="ja").text = p['desc']
        # 3. 高效保存与流式压缩
        xml_file = "epg_ultimate.xml"
        gz_file = "epg_ultimate.xml.gz"
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        
        # 写入 XML 并直接生成 GZ (流式处理，更快)
        tree.write(xml_file, encoding="utf-8", xml_declaration=True)
        with open(xml_file, 'rb') as f_in, gzip.open(gz_file, 'wb') as f_out:
            f_out.writelines(f_in)
        
        duration = time.time() - start_global
        print(f"\n🚀 全部完成！耗时: {duration:.2f}s | 总数: {len(all_results)} 条", flush=True)
        print(f"📦 已打包压缩为: {gz_file} ({os.path.getsize(gz_file)/1024:.1f} KB)")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
