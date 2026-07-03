import os
import requests
import re
import concurrent.futures
import urllib.parse

# =====================================================================
# ⚙️ 核心工具函数
# =====================================================================

def clean_channel_name(name):
    if not name: return ""
    name = name.strip()
    name = re.sub(r'(HD|高清|超清|标清|频道|综合|[-—_ ‐\s]+|[\[\(].*?[\]\)])', '', name, flags=re.IGNORECASE)
    name = name.strip()
    if not name: return "Unknown"
    cctv_match = re.search(r'CCTV(\d+\+?)', name, flags=re.IGNORECASE)
    if cctv_match: return f"CCTV{cctv_match.group(1).upper()}"
    return name

def safe_logo_url(std_name):
    if not std_name: return ""
    safe = urllib.parse.quote(std_name, safe='')
    return f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{safe}.png"

def verify_link_global(item):
    group_name, ch_name, url, logo, tvgid = item
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with requests.head(url, timeout=3, allow_redirects=True, headers=headers) as r:
            if r.status_code in [200, 206]: return item
    except: pass
    try:
        with requests.get(url, timeout=3, stream=True, headers=headers) as r:
            if r.status_code in [200, 206]: return item
    except: pass
    return None

GLOBAL_TRANSLATE = {
    "CNN International": "🇺🇸 CNN 国际新闻", "BBC News": "🇬🇧 BBC 世界新闻",
    "BBC World News": "🇬🇧 BBC 世界新闻频道", "Discovery Channel": "🇺🇸 探索频道",
    "National Geographic": "🇺🇸 National Geographic", "HBO": "🇺🇸 HBO 电影台",
    "CNBC": "🇺🇸 CNBC 财经", "Bloomberg TV": "🇺🇸 彭博财经",
    "NHK World Premium": "🇯🇵 NHK 世界精品", "KBS World": "🇰🇷 KBS 国际台"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# =====================================================================
# PART 1: 纯净重庆联通组播源 -> cn.m3u (独占构建，绝无单播污染)
# =====================================================================
print("========== 开始构建纯净重庆联通组播源 cn.m3u ==========")
cn_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# 🎯 核心改动：直接拥抱你找来的全新 CQCU 联通组播大库
cqcu_multicast_url = "https://raw.githubusercontent.com/1715173329/CQCU-IPTV/master/cqcu-multicast.m3u"

try:
    print("正在从全新的 CQCU 仓库抓取最新重庆联通组播流...")
    res = requests.get(cqcu_multicast_url, timeout=10, headers=HEADERS)
    if res.status_code == 200 and "#EXTINF" in res.text:
        lines = res.text.split('\n')
        multicast_count = 0
        
        for i in range(len(lines)):
            line = lines[i].strip()
            if not line.startswith("#EXTINF"): continue
            
            # 1. 提取频道原始名称
            raw_ch_name = line.split(',')[-1].strip()
            if not raw_ch_name: continue
            
            # 2. 向上扫描并提取原本 M3U 里自带的分组属性（如：央视频道、卫视频道等）
            group_match = re.search(r'group-title="([^"]+)"', line)
            origin_group = group_match.group(1) if group_match else "重庆联通组播"
            
            # 3. 寻找对应的底层组播播放链接 (rtp:// 或 udp://)
            url_line = ""
            for j in range(i+1, min(i+5, len(lines))):
                l = lines[j].strip()
                if l.startswith("#") or not l: continue
                if "rtp://" in l or "udp://" in l:
                    url_line = l
                    break
            if not url_line: continue
            
            # 4. 洗白电视频道名，生成高清匹配台标
            std_name = clean_channel_name(raw_ch_name)
            logo_url = safe_logo_url(std_name)
            
            # 5. 【关键】翻译并重写为你家爱快内网 udpxy 的高级网关形式
            local_url = url_line.replace('rtp://', 'http://192.168.1.1:8888/rtp/', 1).replace('udp://', 'http://192.168.1.1:8888/udp/', 1)
            
            # 6. 装配写入，打上纯净的 🏠 组播分组标签
            cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏠 重庆联通·{origin_group}",{raw_ch_name}')
            cn_lines.append(local_url)
            multicast_count += 1
            
        print(f"🎉 成功从 CQCU 库中洗白提取出 {multicast_count} 条原画组播线！")
except Exception as e:
    print(f"❌ 抓取全新 CQCU 组播源失败: {e}")

with open("cn.m3u", "w", encoding="utf-8") as f: f.write("\n".join(cn_lines))


# =====================================================================
# PART 2: 全球精选源 -> qq.m3u (保持不变，确保外网能看)
# =====================================================================
print("\n========== 开始构建全球精选源 qq.m3u ==========")
iptv_org_urls = {
    "全球新闻网": "https://iptv-org.github.io/iptv/categories/news.m3u",
    "全球纪录片": "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "全球体育台": "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "全球电影台": "https://iptv-org.github.io/iptv/categories/movies.m3u"
}

raw_global_items = []
for group_name, url in iptv_org_urls.items():
    try:
        res = requests.get(url, timeout=15, headers=HEADERS)
        if res.status_code == 200:
            lines = res.text.split('\n')
            count = 0
            for i in range(len(lines)):
                line = lines[i].strip()
                if not line.startswith("#EXTINF"): continue
                logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                origin_logo = logo_match.group(1) if logo_match else ""
                tvgid_match = re.search(r'tvg-id="([^"]+)"', line)
                origin_tvgid = tvgid_match.group(1) if tvgid_match else ""

                ch_name = line.split(',')[-1].strip()
                if not ch_name: continue
                url_line = ""
                for j in range(i+1, min(i+5, len(lines))):
                    l = lines[j].strip()
                    if l.startswith("#") or not l: continue
                    if l.startswith("http"):
                        url_line = l
                        break
                if not url_line: continue

                if ch_name in GLOBAL_TRANSLATE: ch_name = GLOBAL_TRANSLATE[ch_name]
                if count < 100:
                    raw_global_items.append((group_name, ch_name, url_line, origin_logo, origin_tvgid))
                    count += 1
            print(f"  {group_name}: 抓取 {count} 条")
    except: pass

print(f"🚀 并发测速 {len(raw_global_items)} 条全球源...")
valid_global = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_link_global, raw_global_items)
    for r in results:
        if r: valid_global.append(r)

seen_global = set()
qq_lines = ["#EXTM3U"]
for group_name, ch_name, stream_url, logo_url, tvg_id in valid_global:
    key = f"{group_name}|{ch_name}"
    if key in seen_global: continue
    seen_global.add(key)
    logo_attr = f' tvg-logo="{logo_url}"' if logo_url else ""
    tvgid_attr = f' tvg-id="{tvg_id}"' if tvg_id else ""
    qq_lines.append(f'#EXTINF:-1{tvgid_attr}{logo_attr} group-title="{group_name}",{ch_name} 🌐')
    qq_lines.append(stream_url)

with open("qq.m3u", "w", encoding="utf-8") as f: f.write("\n".join(qq_lines))
print(f"⚡ qq.m3u 构建完成！")
