import requests
from bs4 import BeautifulSoup
import datetime
from datetime import timedelta
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import random
import re

# 频道配置 (请根据需要继续添加)
CHANNELS_MAP = {
    "965": ("1:0:19:83C5:3026:A:5000000:0:0:0:", "红樱桃"),
    "967": ("1:0:19:83C7:3026:A:5000000:0:0:0:", "フラミンゴ"),
}

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        
        # 【关键：替换为你刚才复制的那一长串 Cookie】
        self.raw_cookie = "_gcl_au=1.1.1303938502.1770984647; _ga=GA1.1.2010907203.1770984648; _ebtd=2.28sjd120fru.1770984649; _yjsu_yjad=1770984648.2588395d-c1c3-4cdc-8f3f-c236ab421cf4; __lt__cid=47d05e67-f596-4985-b7d9-aab748ab7518; skyperfectv.timetech_user_id=si2yr85hmlkuj9zu; _tt_enable_cookie=1; _ttp=01KHBEJDXWWSKGVD003V1EWSF3_.tt.2; __ulfpc=202602132014353884; PHPSESSID=jhqtqool8oqqq5135ubof6dsra; login=0; __lt__sid=444648a8-ad668f82; cto_bundle=57h-YF9LN1ROYXNiMGZIWnNFbm9wT2MlMkJQUEFjV0dVV3hSMFptSXVWSVdkN3pOem5BJTJCMEhYT200VUpHdE5KNkFERUN3VFYxYUxsYjEzMXVlQzRBaXMlMkY0elQlMkYyTU1zcUV3QUY1NjlzT005NzM0elpMSVVsT1J1UXk0SEgxJTJCak1SOSUyRjQxWEROczY0dUZZJTJGV0FsZnFIUiUyQnNTc0JFTUNJJTJCanBmUm5Fd0gxMDBVVyUyQjJ1Qk5tNERmR1h5OFhxYXQ0WFlkZSUyQnhS; adult_auth=true; adlpo=PC#1770984649566-136656-543370#1782550197|check#true#1774774257; _uetsid=d56224e02b4611f1a90a1da3db2873d9; _uetvid=08f8653008d511f1a48d01bb403063a4; __rtbh.lid=%7B%22eventType%22%3A%22lid%22%2C%22id%22%3A%22aaQzn5Gr2U1mwUgX5E2s%22%2C%22expiryDate%22%3A%222027-03-29T08%3A49%3A56.636Z%22%7D; __rtbh.uid=%7B%22eventType%22%3A%22uid%22%2C%22id%22%3A%22unknown%22%2C%22expiryDate%22%3A%222027-03-29T08%3A49%3A56.637Z%22%7D; ttcsid_CKOUVPRC77U5FRI5MHNG=1774771859661::pU-QQxZ8IopDn6D_XtWR.13.1774774196933.1; ttcsid_CMFRQ03C77U58IR17CJ0=1774771859662::k_LAnjujBwkGE1NdkPGS.13.1774774196933.1; skyperfectv.page_view=10; ttcsid=1774771859662::_WTWNRItdJUlIno140-7.13.1774774196933.0::1.2335819.2337055::2325078.2.923.504::3127869.18.0; _dd_s=logs=1&id=426e1c8b-e2b9-4515-ae1f-2b792ad92df2&created=1774774064533&expire=1774776073440; _ga_WWBP9C5VMM=GS2.1.s1774771855$o14$g1$t1774775179$j60$l0$h140969438"

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Cookie": self.raw_cookie, # 直接把整串 Cookie 塞进 Header
            "Referer": "https://www.skyperfectv.co.jp/"
        }

    def parse_japanese_time(self, date_raw, time_range_str):
        """
        利用 datetime 运算解决月末跨月、跨年及 30 小时制问题
        """
        try:
            # 提取月/日 (支持 03/31 或 2026/03/31)
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_raw)
            if not date_match: return None, None
            
            month, day = int(date_match.group(1)), int(date_match.group(2))
            
            # 确定年份 (处理 12 月跨 1 月的情况)
            now = datetime.datetime.now()
            year = now.year
            if month == 1 and now.month == 12:
                year += 1
            
            # 建立基准时间 (该日凌晨 00:00)
            base_dt = datetime.datetime(year, month, day)
            
            # 解析时间范围 (如 26:00～28:30)
            start_t, end_t = time_range_str.split('～')
            
            def get_actual_dt(hhmm, ref_date):
                hh, mm = map(int, hhmm.split(':'))
                # 利用 timedelta 自动处理进位 (如 3月31日 + 26小时 = 4月1日 02:00)
                return ref_date + timedelta(hours=hh, minutes=mm)

            start_dt = get_actual_dt(start_t, base_dt)
            end_dt = get_actual_dt(end_t, base_dt)
            
            # 如果结束时间数值上小于开始时间 (如 23:00～01:00)，手动加一天
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
                
            return (start_dt.strftime("%Y%m%d%H%M00 +0900"), 
                    end_dt.strftime("%Y%m%d%H%M00 +0900"))
        except:
            return None, None

    def fetch_detail(self, url, srv_ref, referer):
        """深度抓取详情页：描述 + 精准时间"""
        try:
            headers = self.headers.copy()
            headers['Referer'] = referer
            time.sleep(random.uniform(0.2, 0.5))
            
            res = self.session.get(url, headers=headers, cookies=self.auth_cookies, timeout=12)
            if res.status_code != 200: return None
            
            dsoup = BeautifulSoup(res.text, 'html.parser')
            
            # 提取标题与时间节点
            title_node = dsoup.select_one('.p-headline__ttl') or dsoup.select_one('h1')
            time_node = dsoup.select_one('.p-headline__info__time')
            if not title_node or not time_node: return None
            
            # 提取并拼接长描述
            desc_parts = []
            short_node = dsoup.select_one('.p-info__detail p')
            if short_node:
                desc_parts.append(short_node.get_text(strip=True).replace('　もっと見る', ''))
            
            long_node = dsoup.select_one('.p-info__cast p') # みどころ
            if long_node:
                desc_parts.append("【内容】" + long_node.get_text(strip=True))
            
            # 解析日期时间
            raw_time = time_node.get_text(strip=True)
            # 详情页通常包含日期 03/30(月)
            date_node = dsoup.select_one('.p-program-detail__date')
            date_str = date_node.get_text(strip=True) if date_node else raw_time
            
            # 提取时间范围正则
            time_match = re.search(r'(\d{2}:\d{2}～\d{2}:\d{2})', raw_time)
            if not time_match: return None
            
            start_xml, stop_xml = self.parse_japanese_time(date_str, time_match.group(1))
            
            if start_xml and stop_xml:
                return {
                    'ref': srv_ref,
                    'title': title_node.get_text(strip=True),
                    'desc': "\n\n".join(desc_parts) if desc_parts else title_node.get_text(strip=True),
                    'start': start_xml,
                    'stop': stop_xml
                }
        except:
            return None

    def fetch_channel(self, ch_num, srv_ref, name):
        channel_url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        try:
            # 使用 self.headers 里的全量 Cookie 访问
            res = self.session.get(channel_url, headers=self.headers, timeout=20)
            
            # 调试：如果在 Actions 日志里看到这个，说明 Cookie 填错了或者过期了
            if "年齢確認" in res.text:
                print(f"❌ {name} 依然被拦截，请检查 Cookie 字符串是否包含 PHPSESSID 等关键信息")
                return []

            soup = BeautifulSoup(res.text, 'html.parser')
            # 这里的链接提取逻辑保持不变
            links = soup.find_all('a', href=re.compile(r'/program/detail/'))

            soup = BeautifulSoup(res.text, 'html.parser')
            # 提取所有 uid 详情链接并去重
            links = soup.find_all('a', href=re.compile(r'/program/detail/'))
            unique_hrefs = list(set([l.get('href') for l in links if l.get('href')]))
            
            with ThreadPoolExecutor(max_workers=5) as detail_executor:
                futures = [detail_executor.submit(self.fetch_detail, self.base_url + h, srv_ref, channel_url) 
                           for h in unique_hrefs]
                for f in as_completed(futures):
                    result = f.result()
                    if result: progs.append(result)
            
            print(f"✅ {name} ({ch_num}) 抓取完成: {len(progs)} 条")
        except Exception as e:
            print(f"💥 {name} 异常: {e}")
        return progs

    def run(self):
        all_results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            tasks = [executor.submit(self.fetch_channel, ch_num, srv_ref, name) 
                     for ch_num, (srv_ref, name) in CHANNELS_MAP.items()]
            for f in as_completed(tasks):
                all_results.extend(f.result())

        # 构建 XMLTV
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
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
        print(f"\n🚀 任务结束！共计生成 {len(all_results)} 条带描述的节目数据。")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
