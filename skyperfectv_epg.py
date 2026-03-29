import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random

# 频道列表 (示例，请根据你的需求补充完整)
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
        处理 30 小时制逻辑。
        输入: date_str='20260328', time_range_str='26:00～27:30'
        输出: 标准 XMLTV 时间格式
        """
        try:
            start_t, end_t = time_range_str.split('～')
            base_dt = datetime.datetime.strptime(date_str, "%Y%m%d")
            
            def convert_hhmm(hhmm, current_date):
                hh, mm = map(int, hhmm.split(':'))
                days_to_add = hh // 24
                actual_hh = hh % 24
                return (current_date + timedelta(days=days_to_add)).replace(hour=actual_hh, minute=mm)

            start_dt = convert_hhmm(start_t, base_dt)
            end_dt = convert_hhmm(end_t, base_dt)
            
            # 如果结束时间早于开始时间，说明跨天
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
                
            return start_dt.strftime("%Y%m%d%H%M00 +0900"), end_dt.strftime("%Y%m%d%H%M00 +0900")
        except:
            return None, None

    def fetch_channel(self, ch_num, srv_ref, name):
        # 自动切换普通和成人路径
        path_prefix = "adult/premium" if int(ch_num) >= 940 else "premium"
        base_url = f"https://www.skyperfectv.co.jp/program/schedule/{path_prefix}/channel:{ch_num}/"
        
        progs = []
        try:
            res = self.session.get(base_url, timeout=20)
            if res.status_code != 200: return []
            
            soup = BeautifulSoup(res.content, 'lxml')
            # 拿到主页上所有的节目方块链接
            links = soup.select('.p-program-list__title a') 
            
            # 睡醒后可以先拿 5-10 个节目做测试，跑通了再全开
            for link in links[:15]: 
                detail_url = "https://www.skyperfectv.co.jp" + link.get('href')
                prog_data = self.fetch_detail(detail_url, srv_ref)
                if prog_data:
                    progs.append(prog_data)
            
            print(f"✅ {name} 深度抓取完成")
        except Exception as e:
            print(f"💥 {name} 异常: {e}")
        return progs

    def fetch_detail(self, url, srv_ref):
        """进入详情页拿真数据"""
        try:
            res = self.session.get(url, timeout=10)
            soup = BeautifulSoup(res.content, 'lxml')
            
            # 详情页的选择器通常更稳固
            title = soup.select_one('h1').text.strip()
            desc = soup.select_one('.p-program-detail__content').text.strip() # 这里就是你要的描述
            # 时间逻辑...
            return {'ref': srv_ref, 'title': title, 'desc': desc, ...}
        except:
            return None
    def run(self):
        all_results = []
        # 聚合页信息量大，建议保持低并发
        with ThreadPoolExecutor(max_workers=3) as executor:
            tasks = [executor.submit(self.fetch_channel, ch_num, srv_ref, name) 
                     for ch_num, (srv_ref, name) in CHANNELS_MAP.items()]

            for f in as_completed(tasks):
                all_results.extend(f.result())

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
        print(f"\n🚀 任务完成！总计抓取 {len(all_results)} 条节目。")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
