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
    "616": ("1:0:19:8268:3019:A:5000000:0:0:0:", "ＴＢＳチャンネル１ 最新ドラマ・音楽・映画"),
    "617": ("1:0:19:8269:4023:A:4D80000:0:0:0:", "ＴＢＳチャンネル２ 名作ドラマ・スポーツ・アニメ"),
    "618": ("1:0:19:826A:4031:A:4D80000:0:0:0:", "エンタメ～テレ☆シネドラバラエティ"),
    "619": ("1:0:19:826B:4024:A:4D80000:0:0:0:", "日テレプラス ドラマ・アニメ・音楽ライブ"),
    "620": ("1:0:19:826C:4024:A:4D80000:0:0:0:", "ディズニー･チャンネル"),
    "621": ("1:0:19:826D:3019:A:5000000:0:0:0:", "ＷＯＷＯＷプライム"),
    "622": ("1:0:19:826E:3017:A:5000000:0:0:0:", "ＷＯＷＯＷライブ"),
    "664": ("1:0:19:8298:4029:A:4D80000:0:0:0:", "チャンネル銀河 歴史ドラマ・サスペンス・日本のうた"),
    "638": ("1:0:19:827E:3017:A:5000000:0:0:0:", "ミュージック・エア"),
    "639": ("1:0:19:827F:3026:A:5000000:0:0:0:", "ミュージック・ジャパンTV"),
    "640": ("1:0:19:8280:3028:A:5000000:0:0:0:", "MTV"),
    "641": ("1:0:19:8281:3014:A:5000000:0:0:0:", "MUSIC ON! TV（エムオン!）"),
    "642": ("1:0:19:8282:3020:A:5000000:0:0:0:", "音楽・ライブ！ スペースシャワーＴＶ"),
    "644": ("1:0:19:8284:3019:A:5000000:0:0:0:", "歌謡ポップスチャンネル"),
    "645": ("1:0:19:8285:3017:A:5000000:0:0:0:", "ミュージック・グラフィティＴＶ"),
    "647": ("1:0:19:8287:3014:A:5000000:0:0:0:", "スーパー！ドラマＴＶ #海外ドラマ☆エンタメ"),
    "649": ("1:0:19:8289:4023:A:4D80000:0:0:0:", "ミステリーチャンネル"),
    "650": ("1:0:19:828A:4023:A:4D80000:0:0:0:", "アクションチャンネル"),
    "651": ("1:0:19:828B:4023:A:4D80000:0:0:0:", "Dlife（ディーライフ）"),
    "654": ("1:0:19:828E:3026:A:5000000:0:0:0:", "女性チャンネル♪LaLa TV"),
    "655": ("1:0:19:828F:4032:A:4D80000:0:0:0:", "アジアドラマチックTV（アジドラ）"),
    "656": ("1:0:19:8290:4029:A:4D80000:0:0:0:", "KBS World 韓流専門チャンネル"),
    "657": ("1:0:19:8291:3020:A:5000000:0:0:0:", "ＫＮＴＶ"),
    "658": ("1:0:19:8292:4028:A:4D80000:0:0:0:", "Ｍｎｅｔ"),
    "535": ("1:0:19:8217:4024:A:4D80000:0:0:0:", "大人のイキヌキ！ヌーヴェルパラダイス"),
    "659": ("1:0:19:8293:3020:A:5000000:0:0:0:", "MONDO TV"),
    "660": ("1:0:19:8294:3014:A:5000000:0:0:0:", "ファミリー劇場"),
    "661": ("1:0:19:8295:3018:A:5000000:0:0:0:", "ホームドラマチャンネル 韓流・時代劇・国内ドラマ"),
    "662": ("1:0:19:8296:4031:A:4D80000:0:0:0:", "時代劇専門チャンネル"),
    "663": ("1:0:19:8297:3018:A:5000000:0:0:0:", "アイドル専門チャンネルＰｉｇｏｏ"),
    "667": ("1:0:19:829B:3027:A:5000000:0:0:0:", "アニメシアターX(AT-X)"),
    "668": ("1:0:19:829C:3027:A:5000000:0:0:0:", "カートゥーン ネットワーク 海外アニメ国内アニメ"),
    "669": ("1:0:19:829D:3027:A:5000000:0:0:0:", "キッズステーション テレビアニメ･劇場版･ＯＶＡ"),
    "670": ("1:0:19:829E:4031:A:4D80000:0:0:0:", "アニマックス"),
    "674": ("1:0:19:82A2:3014:A:5000000:0:0:0:", "ヒストリーチャンネル 日本・世界の歴史＆エンタメ"),
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
    "540": ("1:0:19:821C:4023:A:4D80000:0:0:0:", "釣りビジョンＨＤ"),
    "542": ("1:0:19:821E:3019:A:5000000:0:0:0:", "寄席チャンネル"),
    "544": ("1:0:19:8220:3019:A:5000000:0:0:0:", "旅チャンネル"),
    "546": ("1:0:19:8222:4029:A:4D80000:0:0:0:", "鉄道チャンネル"),
    "521": ("1:0:19:8209:4032:A:4D80000:0:0:0:", "囲碁・将棋チャンネル"),
    "672": ("1:0:19:82A0:4024:A:4D80000:0:0:0:", "ディズニージュニア"),
    "678": ("1:0:19:82A6:3017:A:5000000:0:0:0:", "南関東地方競馬チャンネル"),
    "680": ("1:0:19:82A8:4031:A:4D80000:0:0:0:", "ＪＬＣ６８０"),
    "681": ("1:0:19:82A9:4023:A:4D80000:0:0:0:", "ＪＬＣ６８１"),
    "682": ("1:0:19:82AA:4029:A:4D80000:0:0:0:", "ＪＬＣ６８２"),
    "683": ("1:0:19:82AB:4029:A:4D80000:0:0:0:", "ＪＬＣ６８３"),
    "684": ("1:0:19:82AC:4023:A:4D80000:0:0:0:", "ＪＬＣ６８４"),
    "688": ("1:0:19:82B0:3027:A:5000000:0:0:0:", "グリーンチャンネル"),
    "689": ("1:0:19:82B1:3027:A:5000000:0:0:0:", "グリーンチャンネル２"),
    "690": ("1:0:19:82B2:4028:A:4D80000:0:0:0:", "ＳＰＥＥＤチャンネル（競輪ライブ） ６９０"),
    "696": ("1:0:19:82B8:3018:A:5000000:0:0:0:", "ＳＰＥＥＤチャンネル（競輪ライブ） ６９6"),
    "701": ("1:0:19:82BD:3027:A:5000000:0:0:0:", "地方競馬ナイン ７０１"),
    "702": ("1:0:19:82BE:3019:A:5000000:0:0:0:", "地方競馬ナイン ７０２"),
    "703": ("1:0:19:82BF:3017:A:5000000:0:0:0:", "地方競馬ナイン ７０３"),
    "518": ("1:0:19:8206:4028:A:4D80000:0:0:0:", "フェニックステレビ（鳳凰衛視）"),
    "523": ("1:0:19:820B:4029:A:4D80000:0:0:0:", "ショップチャンネル"),
    "525": ("1:0:19:820D:4029:A:4D80000:0:0:0:", "ＱＶＣ（キューヴィーシー）"),
    "527": ("1:0:19:820F:4029:A:4D80000:0:0:0:", "ジュエリー☆ＧＳＴＶ"),
    "528": ("1:0:19:8210:3017:A:5000000:0:0:0:", "セレクトショッピング"),
    "942": ("1:0:19:83AE:3028:A:5000000:0:0:0:", "ｋｍｐチャンネル"),
    "943": ("1:0:19:83AF:3014:A:5000000:0:0:0:", "プレイボーイ チャンネル"),
    "944": ("1:0:19:83B0:3028:A:5000000:0:0:0:", "レインボーチャンネル"),
    "945": ("1:0:19:83B1:3026:A:5000000:0:0:0:", "ミッドナイト・ブルー"),
    "946": ("1:0:19:83B2:3028:A:5000000:0:0:0:", "パラダイステレビ"),
    "947": ("1:0:19:83B3:3026:A:5000000:0:0:0:", "チェリーボム"),
    "957": ("1:0:19:83B3:3026:A:5000000:0:0:0:", "ＶＥＮＵＳ"),
    "958": ("1:0:19:83BE:4024:A:4D80000:0:0:0:", "バニラスカイチャンネル"),
    "959": ("1:0:19:83BF:4023:A:4D80000:0:0:0:", "エンタ！９５９"),
    "960": ("1:0:19:83C0:4028:A:4D80000:0:0:0:", "Zaptv"),
    "963": ("1:0:19:83C3:4028:A:4D80000:0:0:0:", "ダイナマイトTV"),
    "964": ("1:0:19:83C4:4028:A:4D80000:0:0:0:", "AV王"),
    "965": ("1:0:19:83C5:3018:A:5000000:0:0:0:", "レッドチェリー"),
    "966": ("1:0:19:83C6:3026:A:5000000:0:0:0:", "Splash"),
    "967": ("1:0:19:83C7:3026:A:5000000:0:0:0:", "フラミンゴ"),
    "599": ("1:0:19:8257:4024:A:4D80000:0:0:0:", "スカパー！プロモ599"),
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
        ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
        all_progs = []
        
        # 记录本次运行新抓取的数量，用于每隔几个频道存一次盘
        count = 0
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
            
            for f in as_completed(tasks):
                result = f.result()
                if result:
                    all_progs.extend(result)
                    count += 1
                
                # 每抓完 5 个频道，就强行存一次盘，防止程序崩溃导致白跑
                if count % 5 == 0:
                    self.save_cache()
                    print(f"📡 已自动存档：当前已完成 {count} 个频道")

        # 最终保存（生成 XML）
        self.save_cache()

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
