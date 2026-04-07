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
import threading
import zipfile

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
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."}
        self.session.headers.update(self.headers)
        self.session.cookies.update({'isAdult': '1', 'age_check': '1', 'adult_auth': 'true'})
        self.cache_file = "epg_cache.json"
        self.lock = threading.Lock()
        self.cache = self.load_cache()

    def ultimate_clean(self, text):
        if not text: return ""
        text = "".join([chr(ord(c) - 0xfee0) if 0xff01 <= ord(c) <= 0xff5e else c for c in text])
        text = text.replace('　', ' ')
        text = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|（.*?）', '', text)
        text = text.lstrip(')#★* ').replace(' ', '')
        clean = re.sub(r'[\\/:*?"<>|#★\*\.~～．,，]', '', text).strip()[:80]
        return clean if clean else "NoTitle"

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
        try:
            # 1. 提取月/日
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_raw)
            if not date_match: return None, None
            month, day = int(date_match.group(1)), int(date_match.group(2))
            
            # 2. 强制使用日本时区确定年份，防止 GitHub 服务器时差导致跨年失败
            # JST 是 UTC+9
            jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
            year = jst_now.year
            
            # 核心跨年逻辑：如果现在是 12 月，抓到的是 1 月，年份 +1
            if jst_now.month == 12 and month == 1:
                year += 1
            # 防御逻辑：如果现在是 1 月，抓到的是 12 月（历史数据），年份 -1
            elif jst_now.month == 1 and month == 12:
                year -= 1
                
            base_dt = datetime.datetime(year, month, day)

            # 3. 提取时间
            time_parts = re.findall(r'(\d{1,2}:\d{2})', time_range_str)
            if len(time_parts) < 2: return None, None
            
            sh, sm = map(int, time_parts[0].split(':'))
            eh, em = map(int, time_parts[1].split(':'))
            
            # 4. 使用 timedelta 替代 replace，这样即使 sh >= 24 也能自动进位，更稳健
            start_dt = base_dt + datetime.timedelta(hours=sh, minutes=sm)
            end_dt = base_dt + datetime.timedelta(hours=eh, minutes=em)
            
            # 5. 处理跨子夜 (例如 23:00 ～ 01:00)
            if sh > eh:
                end_dt += datetime.timedelta(days=1)
                
            return (start_dt.strftime("%Y%m%d%H%M00 +0900"), 
                    end_dt.strftime("%Y%m%d%H%M00 +0900"))
        except:
            return None, None

    def fetch_detail(self, url, srv_ref, referer, icon_url, ch_num):
        if url in self.cache:
            data = self.cache[url].copy()
            data['ref'] = srv_ref
            data['ch_num'] = ch_num
            
            # 🚩 关键修改：如果这次从列表页传来了 icon_url，而缓存里没有或为空，一定要补上
            if icon_url and not data.get('icon'):
                data['icon'] = icon_url
                with self.lock:
                    self.cache[url]['icon'] = icon_url # 同步更新持久化缓存
            return data

        try:
            res = self.session.get(url, headers={"Referer": referer}, timeout=10)
            if res.status_code != 200: return None
            res.encoding = res.apparent_encoding 
            soup = BeautifulSoup(res.text, 'lxml')

            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "No Title"

            # --- 替换开始 ---
            time_el = soup.find('p', class_='p-info__time') or soup.find(string=re.compile(r'\d{1,2}/\d{1,2}.*?\d{2}:\d{2}'))
            if not time_el: return None
            
            raw_time_text = time_el.get_text(strip=True)
            
            # 1. 精准提取日期 (例如 04/06)
            date_match = re.search(r'(\d{1,2}/\d{1,2})', raw_time_text)
            if not date_match: return None
            date_raw = date_match.group(1)
            
            # 2. 限制搜索范围：只在日期后的 30 个字符内找【开始】和【结束】时间
            # 这样绝对不会勾到页面底部的 UID、URL 或其他节目的数字
            search_area = raw_time_text[date_match.end() : date_match.end() + 35]
            times = re.findall(r'(\d{1,2}:\d{2})', search_area)
            
            if len(times) < 2: return None
            
            # 3. 此时 times[0] 是 15:00, times[1] 是 18:00
            start_xml, stop_xml = self.parse_japanese_time(date_raw, f"{times[0]}～{times[1]}")
            # --- 替换结束 ---
            
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
            'icon': icon_url,
            'ch_num': ch_num,  # 🚩 核心：存入频道 ID，用于图片命名
            'ref': srv_ref     # 🚩 核心：存入 Ref，用于 XML 匹配
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
                    futures.append(executor.submit(self.fetch_detail, full_url, srv_ref, url, icon_url, ch_num))
                
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
            
    def download_to_zip(self, all_progs):
        import os
        import datetime
        import zipfile
        from concurrent.futures import ThreadPoolExecutor

        poster_dir = "posters"
        zip_name = "posters.zip"
        if not os.path.exists(poster_dir): os.makedirs(poster_dir)
        
        now = datetime.datetime.now()
        # 保持 48 小时活跃期
        time_limit = datetime.timedelta(hours=48)

        def _down(p):
            url = p.get('icon')
            start_raw = p.get('start') 
            ch_num = p.get('ch_num') 
            
            if not url or not start_raw or not ch_num: return
            
            try:
                time_digits = "".join(filter(str.isdigit, start_raw))[:12]
                prog_time = datetime.datetime.strptime(time_digits, "%Y%m%d%H%M")

                # 【逻辑 1】只处理 48 小时内的节目图片，太旧或太远的都不下
                if abs((now - prog_time).total_seconds()) > (time_limit.total_seconds() + 28800):
                    return 

                filename = f"CH.{ch_num}_{time_digits}.jpg"
                path = os.path.join(poster_dir, filename)
                
                # 【逻辑 2】双轨制核心：只要文件夹里没有，就算缓存里有过也要重下
                # 配合 .yml 里的 rm -rf，这就是“强制全量刷新”的开关
                if os.path.exists(path): return
                
                # 这里的 session 抓取不会受到 epg_cache.json 的干扰
                r = self.session.get(url, timeout=10)
                if r.status_code == 200:
                    with open(path, 'wb') as f: 
                        f.write(r.content)
            except: pass 

        # 过滤并去重
        valid_progs = [p for p in all_progs if p and p.get('icon') and p.get('ch_num') and p.get('start')]
        # 以 (频道, 时间) 为唯一标识
        unique_progs = { (p['ch_num'], p['start']): p for p in valid_progs }.values()

        print(f"🚀 正在核对本地文件并补全图片 (目标: {len(unique_progs)})...")
        
        with ThreadPoolExecutor(max_workers=15) as executor:
            executor.map(_down, unique_progs)
        
        # 打包逻辑保持不变
        if os.path.exists(poster_dir) and os.listdir(poster_dir):
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
                for file in os.listdir(poster_dir):
                    z.write(os.path.join(poster_dir, file), file)
            print(f"📦 打包完成: {zip_name} (含 {len(os.listdir(poster_dir))} 张图片)")
            
    def run(self):
        # --- 智能重试与退出逻辑开始 (仅修改此处) ---
        max_tries = 3
        last_cache_count = len(self.cache)
        
        for i in range(max_tries):
            print(f"\n🔄 开始第 {i+1}/{max_tries} 轮 EPG 扫描...")
            
            # 建立映射表
            ref_to_id = {v[0].rstrip(':').upper(): k for k, v in CHANNELS_MAP.items()}
            all_progs = []
            count = 0
            
            # 执行抓取任务
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
                    except Exception as e:
                        print(f"⚠️ 频道抓取异常: {e}")

            current_cache_count = len(self.cache)
            new_records = current_cache_count - last_cache_count
            
            if i < max_tries - 1: # 如果不是最后一轮，判断是否需要继续
                if new_records > 0:
                    print(f"✨ 本轮新抓获 {new_records} 条节目详情，准备进行下一轮补漏...")
                    last_cache_count = current_cache_count
                    time.sleep(5) # 稍作停顿，避免请求过快
                else:
                    print("✅ 数据已全部对齐，未发现新节目，提前结束扫描。")
                    break
            else:
                print("🏁 已完成 3 轮扫描，进入最终打包流程。")
        # --- 智能重试与退出逻辑结束 ---

        # 2. 构建最终 XML (以下代码完全不动)
        file_name = "epg_ultimate.xml" 
        start_time = time.time()
        icon_base = "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/m_{}.gif"
        
        root = ET.Element("tv", {"generator-info-name": "SkyPerfectUltimate"})
        
        # --- 步骤 A: 添加频道头 ---
        for ch_num, (ref, name) in CHANNELS_MAP.items():
            chan = ET.SubElement(root, "channel", id=f"CH.{ch_num}")
            ET.SubElement(chan, "display-name").text = name
            channel_icon_url = icon_base.format(ch_num)
            ET.SubElement(chan, "icon", src=channel_icon_url)
        
        # --- 步骤 B: 生成节目节点 ---
        for p in all_progs:
            clean_ref = p['ref'].rstrip(':').upper()
            short_id_num = ref_to_id.get(clean_ref, p.get('ch_num', 'Unknown'))
            short_id = f"CH.{short_id_num}"
            
            prog = ET.SubElement(root, "programme", channel=short_id, start=p['start'], stop=p['stop'])
            ET.SubElement(prog, "title", lang="ja").text = p['title'].strip() if p['title'] else "No Title"

            if p.get('icon'):
                ET.SubElement(prog, "icon", src=p['icon'])
            
            desc_val = p.get('desc', '')
            if desc_val:
                ET.SubElement(prog, "desc", lang="ja").text = desc_val
    
        # 3. 内存排序
        channels = root.findall('channel')
        programmes = root.findall('programme')
        programmes.sort(key=lambda x: (x.get('channel', ''), x.get('start', '')))
        root[:] = channels + programmes
        print(f"✅ 内存排序完成：共计 {len(programmes)} 条节目")

        # 4. 落地保存
        self.save_cache()
        tree = ET.ElementTree(root)
        if hasattr(ET, 'indent'):
            ET.indent(tree, space="  ")
        tree.write(file_name, encoding="utf-8", xml_declaration=True)
        
        # 5. 生成 Gzip
        with open(file_name, 'rb') as f_in, gzip.open(f"{file_name}.gz", 'wb') as f_out:
            f_out.writelines(f_in)
        
        # 6. 下载图片
        self.download_to_zip(all_progs)
        
        print(f"\n🚀 全部任务完成！耗时: {time.time()-start_time:.1f}s | 缓存库总量: {len(self.cache)}")

if __name__ == "__main__":
    SkyPerfectUltimate().run()
