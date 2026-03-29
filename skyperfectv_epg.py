
import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import re

# 频道列表：请根据你的需求补充完整
CHANNELS_MAP = {
    "623": ("1:0:19:826F:3019:A:5000000:0:0:0:", "ＷＯＷＯＷシネマ"),
    "625": ("1:0:19:8271:4032:A:4D80000:0:0:0:", "BS10プレミアム"),
    "628": ("1:0:19:8274:3018:A:5000000:0:0:0:", "衛星劇場"),
    "965": ("1:0:19:83C5:3026:A:5000000:0:0:0:", "红樱桃"),
    "967": ("1:0:19:83C7:3026:A:5000000:0:0:0:", "フラミンゴ"),
}

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        }

    def parse_japanese_time(self, date_str, time_range_str):
        """
        处理详情页日期(2026/03/29(日))和跨天时间(23:00～02:00)
        """
        try:
            # 提取日期数字部分
            clean_date = re.sub(r'\(.*?\)', '', date_str).replace('/', '').strip()
            start_t, end_t = time_range_str.split('～')
            
            base_dt = datetime.datetime.strptime(clean_date, "%Y%m%d")
            
            def convert_hhmm(hhmm, ref_date):
                hh, mm = map(int, hhmm.split(':'))
                # 处理 30 小时制 (如 26:00)
                days_to_add = hh // 24
                actual_hh = hh % 24
                return (ref_date + timedelta(days=days_to_add)).replace(hour=actual_hh, minute=mm)

            start_dt = convert_hhmm(start_t, base_dt)
            end_dt = convert_hhmm(end_t, base_dt)
            
            # 关键：处理跨日期进位 (如 23:00 到 02:00)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
                
            return start_dt.strftime("%Y%m%d%H%M00 +0900"), end_dt.strftime("%Y%m%d%H%M00 +0900")
        except Exception as e:
            return None, None

    def fetch_detail(self, url, srv_ref, referer):
        try:
            headers = self.headers.copy()
            headers['Referer'] = referer
            
            # 增加一点点随机延迟，防止被官网识别
            time.sleep(random.uniform(0.3, 0.8))
            res = self.session.get(url, headers=headers, timeout=15)
            if res.status_code != 200: return None
            
            # 使用 html.parser 确保解析稳定性
            dsoup = BeautifulSoup(res.text, 'html.parser')
            
            # 1. 提取标题
            title_node = dsoup.select_one('.p-headline__ttl')
            title = title_node.get_text(strip=True) if title_node else "未知节目"
            
            # 2. 提取时间 (03/30（月）00:30～02:10)
            time_node = dsoup.select_one('.p-headline__info__time')
            if not time_node: return None
            raw_time_text = time_node.get_text(strip=True)
            
            # 3. 提取描述 (合并简介和みどころ)
            short_desc = dsoup.select_one('.p-info__detail p')
            long_desc = dsoup.select_one('.p-info__cast p') # みどころ部分
            
            desc_text = ""
            if short_desc:
                desc_text += short_desc.get_text(strip=True).replace('　もっと見る', '')
            if long_desc:
                desc_text += "\n\n【内容】" + long_desc.get_text(strip=True)
            
            # 如果都没抓到描述，用标题兜底
            final_desc = desc_text if desc_text else title

            # 4. 解析时间逻辑 (需要处理 03/30 这种格式)
            # 因为详情页没有年份，我们需要自动补全当前年份 (2026)
            current_year = datetime.datetime.now().year
            # 正则匹配 03/30 和 00:30～02:10
            date_match = re.search(r'(\d{2}/\d{2})', raw_time_text)
            time_match = re.search(r'(\d{2}:\d{2}～\d{2}:\d{2})', raw_time_text)
            
            if date_match and time_match:
                # 拼接成 2026/03/30
                formatted_date = f"{current_year}/{date_match.group(1)}"
                start_xml, stop_xml = self.parse_japanese_time(formatted_date, time_match.group(1))
                
                if start_xml and stop_xml:
                    return {
                        'ref': srv_ref,
                        'title': title,
                        'desc': final_desc,
                        'start': start_xml,
                        'stop': stop_xml
                    }
        except Exception as e:
            print(f"⚠️ 解析详情页出错: {url} -> {e}")
        return None

    def fetch_channel(self, ch_num, srv_ref, name):
        """访问频道页并分发详情页任务"""
        # 统一使用 Premium 路径入口
        channel_url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        
        progs = []
        try:
            res = self.session.get(channel_url, headers=self.headers, timeout=20)
            if res.status_code != 200:
                print(f"❌ {name} ({ch_num}) 频道页请求失败: {res.status_code}")
                return []
            
            soup = BeautifulSoup(res.content, 'lxml')
            # 提取所有包含 uid 的节目链接
            links = soup.find_all('a', href=re.compile(r'/program/detail/'))
            unique_hrefs = list(set([l.get('href') for l in links if l.get('href')]))
            
            # 使用局部线程池加速详情页抓取
            with ThreadPoolExecutor(max_workers=5) as detail_executor:
                futures = [detail_executor.submit(self.fetch_detail, self.base_url + href, srv_ref, channel_url) 
                           for href in unique_hrefs]
                for f in as_completed(futures):
                    result = f.result()
                    if result: progs.append(result)
            
            print(f"✅ {name} 抓取完成: {len(progs)} 条带描述节目")
        except Exception as e:
            print(f"💥 {name} 异常: {e}")
        return progs

    def run(self):
        all_results = []
        print("开始抓取 SkyPerfectTV Premium EPG...")
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            tasks = [executor.submit(self.fetch_channel, ch_num, srv_ref, name) 
                     for ch_num, (srv_ref, name) in CHANNELS_MAP.items()]

            for f in as_completed(tasks):
                all_results.extend(f.result())

        # 生成 XMLTV 结构
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
        
        # 写入频道信息
        for ch_num, (srv_ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=srv_ref)
            ET.SubElement(chan, "display-name").text = name

        # 写入节目信息
        for p in all_results:
            prog = ET.SubElement(root, "programme", start=p['start'], stop=p['stop'], channel=p['ref'])
            ET.SubElement(prog, "title", lang="ja").text = p['title']
            ET.SubElement(prog, "desc", lang="ja").text = p['desc']

        # 保存文件
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write("epg_ultimate.xml", encoding="utf-8", xml_declaration=True)
        print(f"\n🚀 任务结束！生成 EPG 节目总数: {len(all_results)}")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
