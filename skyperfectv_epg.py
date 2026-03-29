import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import re

# 频道列表
CHANNELS_MAP = {
    "623": ("1:0:19:826F:3019:A:5000000:0:0:0:", "ＷＯＷＯＷシネマ"),
    "625": ("1:0:19:8271:4032:A:4D80000:0:0:0:", "BS10プレミアム"),
    "628": ("1:0:19:8274:3018:A:5000000:0:0:0:", "衛星劇場"),
    "967": ("1:0:19:83C7:3026:A:5000000:0:0:0:", "フラミンゴ"),
    "599": ("1:0:19:8257:4024:A:4D80000:0:0:0:", "スカパー！プロモ599"),
}

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://www.skyperfectv.co.jp/"
        }

    def parse_japanese_time(self, date_str, time_range_str):
        """
        处理详情页可能出现的日期格式：'2026/03/29(日)' 和时间范围 '06:00～07:00'
        """
        try:
            # 提取数字日期部分 (2026/03/29)
            clean_date = date_str.split('(')[0].replace('/', '')
            start_t, end_t = time_range_str.split('～')
            
            base_dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
            
            def convert_hhmm(hhmm, current_date):
                hh, mm = map(int, hhmm.split(':'))
                days_to_add = hh // 24
                actual_hh = hh % 24
                return (current_date + timedelta(days=days_to_add)).replace(hour=actual_hh, minute=mm)

            start_dt = convert_hhmm(start_t, base_dt)
            end_dt = convert_hhmm(end_t, base_dt)
            
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
                
            return start_dt.strftime("%Y%m%d%H%M00 +0900"), end_dt.strftime("%Y%m%d%H%M00 +0900")
        except Exception as e:
            return None, None

    def fetch_detail(self, url, srv_ref):
        """进入详情页抓取描述和精准时间"""
        try:
            time.sleep(random.uniform(0.3, 0.7)) # 礼貌延迟
            res = self.session.get(url, headers=self.headers, timeout=15)
            if res.status_code != 200: return None
            
            soup = BeautifulSoup(res.content, 'lxml')
            
            # 提取标题
            title_node = soup.select_one('.p-program-detail__title') or soup.select_one('h1')
            title = title_node.get_text(strip=True) if title_node else "No Title"
            
            # 提取描述
            desc_node = soup.select_one('.p-program-detail__content') or soup.select_one('.p-program-detail__outline')
            desc = desc_node.get_text(strip=True) if desc_node else title
            
            # 提取日期和时间 (详情页典型结构)
            date_node = soup.select_one('.p-program-detail__date')
            time_node = soup.select_one('.p-program-detail__time')
            
            if date_node and time_node:
                start_xml, stop_xml = self.parse_japanese_time(date_node.text.strip(), time_node.text.strip())
                if start_xml and stop_xml:
                    return {
                        'ref': srv_ref,
                        'title': title,
                        'desc': desc,
                        'start': start_xml,
                        'stop': stop_xml
                    }
        except Exception as e:
            print(f"⚠️ 详情页抓取失败 {url}: {e}")
        return None

    def fetch_channel(self, ch_num, srv_ref, name):
        path_prefix = "adult/premium" if int(ch_num) >= 940 else "premium"
        base_url = f"https://www.skyperfectv.co.jp/program/schedule/{path_prefix}/channel:{ch_num}/"
        
        progs = []
        try:
            res = self.session.get(base_url, headers=self.headers, timeout=20)
            if res.status_code != 200: 
                print(f"❌ {name} 频道页请求失败: {res.status_code}")
                return []
            
            soup = BeautifulSoup(res.content, 'lxml')
            links = soup.select('.p-program-list__title a') 
            
            # 这里的链接通常是相对路径，需要补全
            # 先拿前 10 个测试
            for link in links[:10]: 
                href = link.get('href')
                if not href: continue
                detail_url = "https://www.skyperfectv.co.jp" + href
                
                prog_data = self.fetch_detail(detail_url, srv_ref)
                if prog_data:
                    progs.append(prog_data)
            
            print(f"✅ {name} 深度抓取完成，获取到 {len(progs)} 条详情")
        except Exception as e:
            print(f"💥 {name} 异常: {e}")
        return progs

    def run(self):
        all_results = []
        with ThreadPoolExecutor(max_workers=2) as executor: # 详情页抓取建议进一步降低并发
            tasks = [executor.submit(self.fetch_channel, ch_num, srv_ref, name) 
                     for ch_num, (srv_ref, name) in CHANNELS_MAP.items()]

            for f in as_completed(tasks):
                all_results.extend(f.result())

        if not all_results:
            print("❌ 未抓取到任何节目数据，检查选择器是否失效。")
            return

        # 生成 XMLTV
        root = ET.Element("tv")
        for ch_num, (srv_ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=srv_ref)
            ET.SubElement(chan, "display-name").text = name

        for p in all_results:
            prog = ET.SubElement(root, "programme", start=p['start'], stop=p['stop'], channel=p['ref'])
            ET.SubElement(prog, "title", lang="ja").text = p['title']
            ET.SubElement(prog, "desc", lang="ja").text = p['desc']

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write("epg_ultimate.xml", encoding="utf-8", xml_declaration=True)
        print(f"\n🚀 写入完成！共抓取 {len(all_results)} 条带描述的节目。")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
