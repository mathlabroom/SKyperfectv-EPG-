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
import threading  # 引入锁机制
# 动态获取频道映射
def load_channels():
    # 从 GitHub Actions 注入的环境变量中读取
    raw_data = os.environ.get("CHANNELS_JSON")
    if raw_data:
        try:
            # JSON 只能存列表 []，读取后转回元组 () 以保持原有逻辑兼容
            data = json.loads(raw_data)
            return {k: tuple(v) for k, v in data.items()}
        except Exception as e:
            print(f"❌ 环境变量 CHANNELS_JSON 解析出错: {e}")
    
    # 如果变量不存在或解析失败，返回一个空字典或报错提示
    print("⚠️ 未发现有效的频道环境变量，请检查 GitHub Settings。")
    return {}

CHANNELS_MAP = load_channels()

class SkyPerfectUltimate:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://www.skyperfectv.co.jp"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        }
        self.session.headers.update(self.headers)
        self.session.cookies.update({'isAdult': '1', 'age_check': '1', 'adult_auth': 'true'})
        
        self.cache_file = "epg_cache.json"
        self.lock = threading.Lock() # 线程锁，解决缓存写入丢失问题
        self.cache = self.load_cache()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"📂 已载入历史缓存: {len(data)} 条记录")
                    return data
            except: return {}
        return {}

    def save_cache(self):
        """线程安全的保存逻辑"""
        with self.lock:
            # 清理过期缓存（超过 10 天的删除，防止文件无限增大）
            today = datetime.datetime.now()
            # 这里的简单清理仅作为示例，如果需要更复杂的清理可以根据时间戳判断
            if len(self.cache) > 20000:
                print("🧹 缓存过大，触发自动清理...")
                self.cache = {k: v for i, (k, v) in enumerate(self.cache.items()) if i > 2000}

            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"❌ 写入缓存文件失败: {e}")

    def parse_japanese_time(self, date_raw, time_range_str):
        # ... [解析逻辑保持不变] ...
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
        # 1. 增量对比：如果 URL 在缓存中，直接返回，不再请求网络
        if url in self.cache:
            data = self.cache[url].copy()
            data['ref'] = srv_ref
            return data

        try:
            res = self.session.get(url, headers={"Referer": referer}, timeout=10)
            if res.status_code != 200: return None
            res.encoding = res.apparent_encoding 
            soup = BeautifulSoup(res.text, 'lxml')

            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "No Title"

            time_el = soup.find('p', class_='p-info__time') or soup.find(string=re.compile(r'\d{1,2}/\d{1,2}.*?\d{2}:\d{2}'))
            if not time_el: return None
            dt_m = re.search(r'(\d{1,2}/\d{1,2}).*?(\d{2}:\d{2}).*?(\d{2}:\d{2})', time_el.get_text(strip=True))
            if not dt_m: return None
            start_xml, stop_xml = self.parse_japanese_time(dt_m.group(1), f"{dt_m.group(2)}～{dt_m.group(3)}")

            parts = []
            main_d = soup.find('div', class_='p-info__detail')
            if main_d and main_d.p: parts.append(main_d.p.get_text(strip=True).replace('もっと見る', ''))
            ov_d = soup.find('div', class_='p-info__detail__overflow')
            if ov_d:
                specs = [f"【{it.h3.text}】{it.p.text}" for it in ov_d.find_all('div', class_='p-info__cast') if it.h3 and it.p]
                parts.append("\n".join(specs))
            perf_d = soup.find('div', class_='p-info__performer')
            if perf_d:
                names = [li.get_text(strip=True) for li in perf_d.find_all('li') if li.get_text(strip=True)]
                if names: parts.append("【出演者】" + "、".join(names))

            desc = "\n\n".join(parts) if parts else title
            result = {'title': title, 'desc': desc, 'start': start_xml, 'stop': stop_xml}
            
            # --- 线程安全地写入缓存 ---
            with self.lock:
                self.cache[url] = result.copy()
            
            result['ref'] = srv_ref
            return result
        except: return None

    def fetch_channel(self, ch_num, srv_ref, name):
        url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            # 提取详情页链接
            links = list(set([l.get('href') for l in soup.find_all('a', href=re.compile(r'/program/detail/'))]))
            
            # 嵌套多线程抓取详情
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(self.fetch_detail, self.base_url + h, srv_ref, url) for h in links]
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data: progs.append(res_data)
            
            print(f"✅ {name} ({ch_num}) 处理完成 (含缓存命中)")
        except Exception as e: print(f"❌ {name} 错误: {e}")
        return progs

    def sort_epg(self, file_path):
        """专门负责对生成的 XML 进行清洗和排序"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            # 1. 提取标签
            channels = root.findall('channel')
            programmes = root.findall('programme')

            # 2. 核心排序：先按频道 ID 升序，同频道按时间升序
            programmes.sort(key=lambda x: (x.get('channel', ''), x.get('start', '')))

            # 3. 重组 XML 树
            # 这种写法比循环 remove 更简洁高效
            new_children = channels + programmes
            root[:] = new_children 

            # 4. 写回文件
            tree.write(file_path, encoding='utf-8', xml_declaration=True)
            print(f"✅ EPG 排序完成：已按频道和时间重组 {len(programmes)} 条节目。")
        except Exception as e:
            print(f"❌ 排序失败: {e}")
    
    def run(self):
        file_name = "epg_ultimate.xml" # 先定义
        start_time = time.time()
        ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
        all_progs = []
        count = 0
        
        # 1. 抓取任务
        with ThreadPoolExecutor(max_workers=5) as executor:
            tasks = [executor.submit(self.fetch_channel, k, v[0], v[1]) for k, v in CHANNELS_MAP.items()]
            for f in as_completed(tasks):
                try:
                    result = f.result()
                    if result:
                        # 建议加锁确保列表合并的绝对安全
                        with self.lock:
                            all_progs.extend(result)
                        count += 1
                        if count % 5 == 0:
                            self.save_cache()
                            print(f"📡 已自动存档缓存，当前频道进度: {count}")
                except Exception as e:
                    print(f"⚠️ 频道抓取异常: {e}")

        # 2. 构建最终 XML
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
        
        # 添加频道头
        for ch_num, (ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=f"CH.{ch_num}")
            ET.SubElement(chan, "display-name").text = name

        # 添加节目详情
        for p in all_progs:
            # 1. 映射逻辑不变
            clean_ref = p['ref'].rstrip(':').upper()
            short_id = f"CH.{ref_to_id.get(clean_ref, 'Unknown')}"
            
            # 2. 构建节点（确保 channel 在前以兼容旧插件）
            prog = ET.SubElement(root, "programme", 
                                 channel=short_id, 
                                 start=p['start'], 
                                 stop=p['stop'])
            
            # 3. 清洗标题
            ET.SubElement(prog, "title", lang="ja").text = p['title'].strip() if p['title'] else ""
            
            # 4. 深度清洗描述（去空行 + 杂质过滤）
            desc_text = p.get('desc', '')
            if desc_text:
                # 分行 -> 去空格 -> 过滤空行
                lines = [line.strip() for line in desc_text.splitlines() if line.strip()]
                # 合并并再次确保没有非标准的控制字符
                clean_desc = "\n".join(lines)
                # 这一行能过滤掉 XML 不允许的低位控制字符，防止导入崩溃
                clean_desc = "".join(c for c in clean_desc if c.isprintable() or c in "\n\r\t")
                ET.SubElement(prog, "desc", lang="ja").text = clean_desc
            
            # 5. 备注（既然怕大，可以考虑删掉这行减负）
            # ET.SubElement(prog, "remark").text = "cached_item"

        # 3. 内存排序 (这是最有效率的方式)
        channels = root.findall('channel')
        programmes = root.findall('programme')
        programmes.sort(key=lambda x: (x.get('channel', ''), x.get('start', '')))
        root[:] = channels + programmes
        print(f"✅ 内存排序完成：共计 {len(programmes)} 条节目")

        # 4. 落地保存并压缩
        self.save_cache()
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(file_name, encoding="utf-8", xml_declaration=True)
        
        # 5. 生成压缩包
        with open(file_name, 'rb') as f_in, gzip.open(f"{file_name}.gz", 'wb') as f_out:
            f_out.writelines(f_in)
        
        print(f"\n🚀 全部任务完成！耗时: {time.time()-start_time:.1f}s | 缓存库总量: {len(self.cache)}")
      
if __name__ == "__main__":
    SkyPerfectUltimate().run()
