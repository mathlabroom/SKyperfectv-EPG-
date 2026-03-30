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
            # 确保使用正确的编码，防止日文乱码
            res.encoding = res.apparent_encoding 
            html = res.text

            soup = BeautifulSoup(html, 'lxml')

            # --- 1. 提取标题 (Title) ---
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "无标题"

            # --- 2. 提取时间 (Time) ---
            # 依然保留正则，因为时间格式在 HTML 中通常比较固定
            dt_match = re.search(r'(\d{1,2}/\d{1,2})\s*\(.*?\)\s*(\d{2}:\d{2}～\d{2}:\d{2})', html)
            if dt_match:
                date_str = dt_match.group(1)
                time_range = dt_match.group(2)
                start_xml, stop_xml = self.parse_japanese_time(date_str, time_range)
            else:
                return None # 没时间就无法生成 EPG 条目

            # --- 3. 提取深度描述 (Description) ---
            desc_parts = []

            # A. 提取主简介 (p-info__detail)
            main_detail = soup.find('div', class_='p-info__detail')
            if main_detail and main_detail.p:
                # 过滤掉“更多”按钮文字
                main_text = main_detail.p.get_text(strip=True).replace('もっと見る', '')
                if main_text:
                    desc_parts.append(main_text)

            # B. 提取详细规格 (p-info__detail__overflow)
            overflow_div = soup.find('div', class_='p-info__detail__overflow')
            if overflow_div:
                spec_list = []
                # 找到所有的项目：举办日、实况、解说等
                for item in overflow_div.find_all('div', class_='p-info__cast'):
                    h3 = item.h3.get_text(strip=True) if item.h3 else ""
                    p = item.p.get_text(strip=True) if item.p else ""
                    if h3 and p:
                        spec_list.append(f"【{h3}】{p}")
                if spec_list:
                    desc_parts.append("\n".join(spec_list))

            # C. 提取演职人员 (p-info__performer)
            performer_div = soup.find('div', class_='p-info__performer')
            if performer_div:
                names = [li.get_text(strip=True) for li in performer_div.find_all('li') if li.get_text(strip=True)]
                if names:
                    desc_parts.append("【出演者】" + "、".join(names))

            # 合并所有部分，用双换行符隔开，在 Enigma2 上显示更清晰
            desc = "\n\n".join(desc_parts)
            if not desc:
                desc = title # 兜底

            return {
                'ref': srv_ref,
                'title': title,
                'desc': desc,
                'start': start_xml,
                'stop': stop_xml
            }
        except Exception as e:
            # print(f"Error on {url}: {e}")
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
        for ch_num, (srv_ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=srv_ref)
            ET.SubElement(chan, "display-name").text = name
        for p in all_results:
            prog = ET.SubElement(root, "programme", start=p['start'], stop=p['stop'], channel=p['ref'])
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
