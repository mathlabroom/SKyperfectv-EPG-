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

    def fetch_detail(self, url, srv_ref, referer, icon_url=None):
        if url in self.cache:
            data = self.cache[url].copy()
            # 如果旧缓存没图片，这次顺便补上
            if icon_url and 'icon' not in data:
                data['icon'] = icon_url
                with self.lock: self.cache[url]['icon'] = icon_url
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

            # --- ✨ 核心修改：抓取时即刻清洗 ---
            desc = "\n\n".join(parts) if parts else title
            
            # 1. 关键词截断逻辑
            STOP_WORDS = ("【お知らせ","お知らせ",  "【料金案内", "料金案内", "【■セットご案内", "【■セット案内", "詳細は", "◆視聴料金◆", "◆オススメ◆", "公式HP", "0120-")
            cutoff = len(desc)
            for word in STOP_WORDS:
                pos = desc.find(word)
                if pos != -1 and pos < cutoff:
                    cutoff = pos
            desc = desc[:cutoff]

            # 2. 删除空行 + 删除不可见字符（针对 Enigma2 优化）
            lines = [l.strip() for l in desc.splitlines() if l.strip()]
            clean_desc = "\n".join(lines)
            # 仅保留可打印字符，彻底防止 Enigma2 报错
            clean_desc = "".join(c for c in clean_desc if c.isprintable() or c in "\n\r\t")
            
            result = {
            'title': title, 
            'desc': clean_desc, 
            'start': start_xml, 
            'stop': stop_xml,
            'icon': icon_url  # 🎯 存入图片
        }
            
            # --- 线程安全地写入缓存 ---
            with self.lock:
                self.cache[url] = result.copy()
            
            result['ref'] = srv_ref
            return result
        except: return None

    def fetch_channel(self, ch_num, srv_ref, name):
        # 基础 URL
        url = f"{self.base_url}/program/schedule/premium/channel:{ch_num}/"
        progs = []
        print(f"⏳ 正在同步: {name:<20} (ID: {ch_num})", flush=True)
        
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            
            # 1. 锁定所有的节目容器 li
            items = soup.find_all('li', class_='p-program__item')
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                seen_urls = set()  # 用于在单频道内去重
                cached_count = 0
                
                for item in items:
                    a_tag = item.find('a', class_='p-program__link')
                    if not a_tag: continue
                    
                    href = a_tag.get('href')
                    full_url = self.base_url + href
                    
                    # 避免同一个页面里重复抓取相同的 URL
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)

                    # 🎯 提取图片链接 (data-lazysrc)
                    img_tag = item.find('img', class_='js-program_thumbnail')
                    icon_url = img_tag.get('data-lazysrc') if img_tag else None

                    # 2. 预检缓存命中情况（仅用于输出统计）
                    if full_url in self.cache:
                        cached_count += 1
                    
                    # 3. 提交任务给 fetch_detail (它会处理剩下的详情页抓取和清洗)
                    futures.append(executor.submit(self.fetch_detail, full_url, srv_ref, url, icon_url))
                
                # 收集结果
                for f in as_completed(futures):
                    res_data = f.result()
                    if res_data:
                        progs.append(res_data)
            
            # 实时总结
            new_fetched = len(seen_urls) - cached_count
            print(f"✅ {name:<20} | 总计: {len(progs):>2} | 缓存: {cached_count:>2} | 新抓: {new_fetched:>2}", flush=True)
            
        except Exception as e:
            print(f"❌ {name:<20} 发生错误: {e}", flush=True)
            
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
        file_name = "epg_ultimate.xml" 
        start_time = time.time()
        icon_base = "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/m_{}.gif"
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
            
            # 🎯 自动合成频道图标 URL
            # 假设 ch_num 是 '528' 这种字符串或数字
            channel_icon_url = icon_base.format(ch_num)
            ET.SubElement(chan, "icon", src=channel_icon_url)
        
        # --- ✨ 简化后的 programme 节点生成 ---
        for p in all_progs:
            clean_ref = p['ref'].rstrip(':').upper()
            short_id_num = ref_to_id.get(clean_ref, 'Unknown')
            short_id = f"CH.{short_id_num}"
            
            prog = ET.SubElement(root, "programme", channel=short_id, start=p['start'], stop=p['stop'])
            ET.SubElement(prog, "title", lang="ja").text = p['title'].strip() if p['title'] else ""

            # 🎯 插入图标节点
            if p.get('icon'):
                ET.SubElement(prog, "icon", src=p['icon'])
            # 因为抓取时已经洗干净了，这里直接写入
            desc_val = p.get('desc', '')
            if desc_val:
                ET.SubElement(prog, "desc", lang="ja").text = desc_val
            

        # 3. 内存排序
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
