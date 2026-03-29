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
    "623": ("1:0:19:826F:3019:A:5000000:0:0:0:", "ＷＯＷＯＷシネマ"),
    "625": ("1:0:19:8271:4032:A:4D80000:0:0:0:", "BS10プレミアム"),
    "628": ("1:0:19:8274:3018:A:5000000:0:0:0:", "衛星劇場"),
    "629": ("1:0:19:8275:4031:A:4D80000:0:0:0:", "東映チャンネル"),
    "630": ("1:0:19:8276:3020:A:5000000:0:0:0:", "ＷＯＷＯＷプラス 映画・ドラマ・スポーツ・音乐"),
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
    "608": ("1:0:19:8260:3014:A:5000000:0:0:0:", "日テレジータス"),
    "609": ("1:0:19:8261:3028:A:5000000:0:0:0:", "刺激ストロングチャンネル"),
    "665": ("1:0:19:828F:4032:A:4D80000:0:0:0:", "ダンスチャンネル by エンタメ～テレ"),
    "581": ("1:0:19:8245:3028:A:5000000:0:0:0:", "スカチャン1"),
    "585": ("1:0:19:8249:3017:A:5000000:0:0:0:", "スカチャン5"),
    "586": ("1:0:19:824A:3018:A:5000000:0:0:0:", "スカチャン6"),
    "587": ("1:0:19:824B:3027:A:5000000:0:0:0:", "スカチャン7"),
    "588": ("1:0:19:824D:3020:A:5000000:0:0:0:", "スカチャン8"),
    "589": ("1:0:19:824D:3020:A:5000000:0:0:0:", "スカチャン9"),
    "590": ("1:0:19:824E:3027:A:5000000:0:0:0:", "スカチャン10"),
    "592": ("1:0:19:8250:3017:A:5000000:0:0:0:", "スカチャン12"),
    "611": ("1:0:19:8263:3027:A:5000000:0:0:0:", "テレ朝チャンネル１"),
    "612": ("1:0:19:8264:3027:A:5000000:0:0:0:", "テレ朝チャンネル２"),
    "613": ("1:0:19:8265:4031:A:4D80000:0:0:0:", "フジテレビＮＥＸＴ ライブ・プレミアム"),
    "614": ("1:0:19:8265:4031:A:4D80000:0:0:0:", "フジテレビＯＮＥ スポーツ・バラエティ"),
    "615": ("1:0:19:8267:4031:A:4D80000:0:0:0:", "フジテレビＴＷＯ ドラマ・アニメ"),
    "616": ("1:0:19:8268:3019:A:5000000:0:0:0:", "ＴＢＳチャンネル１ 最新ドラマ・音乐・映画"),
    "617": ("1:0:19:8269:4023:A:4D80000:0:0:0:", "ＴＢＳチャンネル２ 名作ドラマ・スポーツ・アニメ"),
    "618": ("1:0:19:826A:4031:A:4D80000:0:0:0:", "エンタメ～テレ☆シネドラバラエティ"),
    "619": ("1:0:19:826B:4024:A:4D80000:0:0:0:", "日テレプラス ドラマ・アニメ・音乐ライブ"),
    "620": ("1:0:19:826C:4024:A:4D80000:0:0:0:", "ディズニー･チャンネル"),
    "621": ("1:0:19:826D:3019:A:5000000:0:0:0:", "ＷＯＷＯＷプライム"),
    "622": ("1:0:19:826E:3017:A:5000000:0:0:0:", "ＷＯＷＯＷライブ"),
    "664": ("1:0:19:8298:4029:A:4D80000:0:0:0:", "チャンネル银河 历史ドラマ・サスペンス・日本のうた"),
    "638": ("1:0:19:827E:3017:A:5000000:0:0:0:", "ミュージック・エア"),
    "639": ("1:0:19:827F:3026:A:5000000:0:0:0:", "ミュージック・ジャパンTV"),
    "640": ("1:0:19:8280:3028:A:5000000:0:0:0:", "MTV"),
    "641": ("1:0:19:8281:3014:A:5000000:0:0:0:", "MUSIC ON! TV（エムオン!）"),
    "642": ("1:0:19:8282:3020:A:5000000:0:0:0:", "音乐・ライブ！ スペースシャワーＴＶ"),
    "644": ("1:0:19:8284:3019:A:5000000:0:0:0:", "歌谣ポップスチャンネル"),
    "645": ("1:0:19:8285:3017:A:5000000:0:0:0:", "ミュージック・グラフィティＴＶ"),
    "647": ("1:0:19:8287:3014:A:5000000:0:0:0:", "スーパー！ドラマＴＶ #海外ドラマ☆エンタメ"),
    "649": ("1:0:19:8289:4023:A:4D80000:0:0:0:", "ミステリーチャンネル"),
    "650": ("1:0:19:828A:4023:A:4D80000:0:0:0:", "アクションチャンネル"),
    "651": ("1:0:19:828B:4023:A:4D80000:0:0:0:", "Dlife（ディーライフ）"),
    "654": ("1:0:19:828E:3026:A:5000000:0:0:0:", "女性チャンネル♪LaLa TV"),
    "655": ("1:0:19:828F:4032:A:4D80000:0:0:0:", "アジアドラマチックTV（アジドラ）"),
    "656": ("1:0:19:8290:4029:A:4D80000:0:0:0:", "KBS World 韩流専门チャンネル"),
    "657": ("1:0:19:8291:3020:A:5000000:0:0:0:", "ＫＮＴＶ"),
    "658": ("1:0:19:8292:4028:A:4D80000:0:0:0:", "Ｍｎｅｔ"),
    "535": ("1:0:19:8217:4024:A:4D80000:0:0:0:", "大人のイキヌキ！ヌーヴェルパラダイス"),
    "659": ("1:0:19:8293:3020:A:5000000:0:0:0:", "MONDO TV"),
    "660": ("1:0:19:8294:3014:A:5000000:0:0:0:", "ファミリー剧场"),
    "661": ("1:0:19:8295:3018:A:5000000:0:0:0:", "ホームドラマチャンネル 韩流・时代剧・国内ドラマ"),
    "662": ("1:0:19:8296:4031:A:4D80000:0:0:0:", "时代剧専门チャンネル"),
    "663": ("1:0:19:8297:3018:A:5000000:0:0:0:", "アイドル専门チャンネルＰｉｇｏｏ"),
    "667": ("1:0:19:829B:3027:A:5000000:0:0:0:", "アニメシアターX(AT-X)"),
    "668": ("1:0:19:829C:3027:A:5000000:0:0:0:", "カートゥーン ネットワーク 海外アニメ国内アニメ"),
    "669": ("1:0:19:829D:3027:A:5000000:0:0:0:", "キッズステーション テレビアニメ･剧场版･ＯＶＡ"),
    "670": ("1:0:19:829E:4031:A:4D80000:0:0:0:", "アニマックス"),
    "674": ("1:0:19:82A2:3014:A:5000000:0:0:0:", "ヒストリーチャンネル 日本・世界の历史＆エンタメ"),
    "675": ("1:0:19:82A3:4031:A:4D80000:0:0:0:", "ナショナル ジオグラフィック"),
    "676": ("1:0:19:82A4:3026:A:5000000:0:0:0:", "ディスカバリーチャンネル"),
    "677": ("1:0:19:82A5:4032:A:4D80000:0:0:0:", "アニマルプラネット"),
    "560": ("1:0:19:8230:3028:A:5000000:0:0:0:", "ＳＯＲＡ―お天気チャンネル―"),
    "565": ("1:0:19:8235:3018:A:5000000:0:0:0:", "ＢＢＣニュース"),
    "566": ("1:0:19:8236:3020:A:5000000:0:0:0:", "CNNj"),
    "567": ("1:0:19:8237:3020:A:5000000:0:0:0:", "CNN U.S."),
    "568": ("1:0:19:8238:4032:A:4D80000:0:0:0:", "中国テレビ★大富チャンネル"),
    "570": ("1:0:19:823A:3019:A:5000000:0:0:0:", "日経CNBC"),
    "571": ("1:0:19:823B:4024:A:4D80000:0:0:0:", "日テレNEWS24"),
    "572": ("1:0:19:823C:3019:A:5000000:0:0:0:", "TBS NEWS"),
    "529": ("1:0:19:8211:3017:A:5000000:0:0:0:", "ベターライフチャンネル"),
    "536": ("1:0:19:8218:4032:A:4D80000:0:0:0:", "パチンコ★パチスロＴＶ！"),
    "537": ("1:0:19:8219:4028:A:4D80000:0:0:0:", "パチ・スロ サイトセブンＴＶ"),
    "540": ("1:0:19:821C:4023:A:4D80000:0:0:0:", "钓りビジョンＨＤ"),
    "542": ("1:0:19:821E:3019:A:5000000:0:0:0:", "寄席チャンネル"),
    "544": ("1:0:19:8220:3019:A:5000000:0:0:0:", "旅チャンネル"),
    "546": ("1:0:19:8222:4029:A:4D80000:0:0:0:", "铁道チャンネル"),
    "521": ("1:0:19:8209:4032:A:4D80000:0:0:0:", "囲碁・将棋チャンネル"),
    "672": ("1:0:19:82A0:4024:A:4D80000:0:0:0:", "ディズニージュニア"),
    "678": ("1:0:19:82A6:3017:A:5000000:0:0:0:", "南関东地方竞马チャンネル"),
    "680": ("1:0:19:82A8:4031:A:4D80000:0:0:0:", "ＪＬＣ６８０"),
    "681": ("1:0:19:82A9:4023:A:4D80000:0:0:0:", "ＪＬＣ６８１"),
    "682": ("1:0:19:82AA:4029:A:4D80000:0:0:0:", "ＪＬＣ６８２"),
    "683": ("1:0:19:82AB:4029:A:4D80000:0:0:0:", "ＪＬＣ６８３"),
    "684": ("1:0:19:82AC:4023:A:4D80000:0:0:0:", "ＪＬＣ６８４"),
    "688": ("1:0:19:82B0:3027:A:5000000:0:0:0:", "グリーンチャンネル"),
    "689": ("1:0:19:82B1:3027:A:5000000:0:0:0:", "グリーンチャンネル２"),
    "690": ("1:0:19:82B2:4028:A:4D80000:0:0:0:", "ＳＰＥＥＤチャンネル（竞轮ライブ） ６９０"),
    "696": ("1:0:19:82B8:3018:A:5000000:0:0:0:", "ＳＰＥＥＤチャンネル（竞轮ライブ） ６９6"),
    "701": ("1:0:19:82BD:3027:A:5000000:0:0:0:", "地方竞马ナイン ７０１"),
    "702": ("1:0:19:82BE:3019:A:5000000:0:0:0:", "地方竞马ナイン ７０２"),
    "703": ("1:0:19:82BF:3017:A:5000000:0:0:0:", "地方竞马ナイン ７０３"),
    "518": ("1:0:19:8206:4028:A:4D80000:0:0:0:", "フェニックステレビ（凤凰卫视）"),
    "523": ("1:0:19:820B:4029:A:4D80000:0:0:0:", "ショップチャンネル"),
    "525": ("1:0:19:820D:4029:A:4D80000:0:0:0:", "ＱＶＣ（キューヴィーシー）"),
    "527": ("1:0:19:820F:4029:A:4D80000:0:0:0:", "ジュエリー☆ＧＳＴＶ"),
    "528": ("1:0:19:8210:3017:A:5000000:0:0:0:", "セレクトショッピング"),
    "599": ("1:0:19:8257:4024:A:4D80000:0:0:0:", "スカパー！プロモ599"),
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
            html = res.text

            # --- 步骤 1：尝试正则快速提取（追求速度） ---
            title = ""
            desc = ""
            start_xml = stop_xml = None
            
            # 匹配标题
            t_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if t_match:
                title = re.sub(r'<[^>]+>', '', t_match.group(1)).strip()

            # 匹配日期和时间 (例如: 03/29(日) 21:00～23:10)
            dt_match = re.search(r'(\d{1,2}/\d{1,2})\s*\(.*?\)\s*(\d{2}:\d{2}～\d{2}:\d{2})', html)
            
            # --- 步骤 2：如果正则失败，立刻切换到 BeautifulSoup (追求稳定) ---
            if not title or not dt_match:
                soup = BeautifulSoup(html, 'lxml')
                # 提取标题
                if not title:
                    title_tag = soup.find('h1')
                    title = title_tag.get_text(strip=True) if title_tag else "无标题"
                
                # 提取描述
                desc_tag = soup.find('meta', attrs={'name': 'description'}) or \
                           soup.find('meta', attrs={'property': 'og:description'})
                desc = desc_tag['content'].strip() if desc_tag else title
                
                # 提取时间 (针对正则没抓到的情况)
                if not dt_match:
                    # 寻找包含“～”符号的文本块，通常就是时间
                    time_element = soup.find(string=re.compile(r'\d{2}:\d{2}～\d{2}:\d{2}'))
                    if time_element:
                        # 向上找日期，或者直接从文本中提取
                        full_text = time_element.parent.get_text()
                        dt_match = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}～\d{2}:\d{2})', full_text)

            # --- 步骤 3：数据清洗与转换 ---
            if dt_match:
                date_str = dt_match.group(1)
                time_range = dt_match.group(2)
                start_xml, stop_xml = self.parse_japanese_time(date_str, time_range)
            else:
                # 如果到这里还是没拿到时间，这页就废了
                return None

            if not desc: desc = title # 兜底描述

            return {
                'ref': srv_ref,
                'title': title,
                'desc': desc,
                'start': start_xml,
                'stop': stop_xml
            }
        except Exception as e:
            # 依然抓不到可以开启下面这行查原因
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
            with ThreadPoolExecutor(max_workers=15) as detail_executor:
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
