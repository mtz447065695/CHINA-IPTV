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

def verify_link(item):
    group_name, ch_name, url, *extra = item
    logo_url = extra[0] if len(extra) > 0 else ""
    tvg_id = extra[1] if len(extra) > 1 else ""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for _ in range(2):
        try:
            with requests.head(url, timeout=3, allow_redirects=True, headers=headers) as res:
                if res.status_code in [200, 206]:
                    return group_name, ch_name, url, logo_url, tvg_id
        except Exception: pass
        try:
            with requests.get(url, timeout=3, stream=True, headers=headers) as res:
                if res.status_code in [200, 206]:
                    return group_name, ch_name, url, logo_url, tvg_id
        except Exception: pass
    return None

GLOBAL_TRANSLATE = {
    "CNN International": "🇺🇸 CNN 国际新闻",
    "BBC News": "🇬🇧 BBC 世界新闻",
    "BBC World News": "🇬🇧 BBC 世界新闻频道",
    "Discovery Channel": "🇺🇸 探索频道",
    "National Geographic": "🇺🇸 国家地理",
    "HBO": "🇺🇸 HBO 电影台",
    "CNBC": "🇺🇸 CNBC 财经",
    "Bloomberg TV": "🇺🇸 彭博财经",
    "NHK World Premium": "🇯🇵 NHK 世界精品",
    "KBS World": "🇰🇷 KBS 国际台"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch_with_retry(url, timeout=10, retries=2):
    for _ in range(retries):
        try:
            res = requests.get(url, timeout=timeout, headers=HEADERS)
            if res.status_code == 200: return res
        except Exception: pass
    return None

# =====================================================================
# PART 1: 国内综合源 -> cn.m3u
# =====================================================================
print("========== 开始构建国内综合源 cn.m3u ==========")
cn_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# 1. 家庭组播线
raw_multicast = ""
local_path = "Multicast/chongqing/unicom.txt"
upstream_url = "https://raw.githubusercontent.com/xisohi/CHINA-IPTV/main/Multicast/chongqing/unicom.txt"

if os.path.exists(local_path):
    with open(local_path, "r", encoding="utf-8") as f: raw_multicast = f.read()
else:
    res = fetch_with_retry(upstream_url)
    if res and "rtp://" in res.text: raw_multicast = res.text

multicast_count = 0
if raw_multicast:
    for line in raw_multicast.split('\n'):
        line = line.strip()
        if not line: continue
        idx = line.find(',rtp://')
        if idx == -1:
            idx = line.find(', rtp://')
        if idx == -1:
            idx = line.find(',udp://')
        if idx == -1:
            idx = line.find(', udp://')
        if idx == -1: continue
        name = line[:idx].strip()
        tail = line[idx+1:].strip()
        if not tail.startswith(('rtp://', 'udp://')): continue
        std_name = clean_channel_name(name)
        if not std_name: continue
        logo_url = safe_logo_url(std_name)
        local_url = tail.replace('rtp://', 'http://192.168.1.1:8888/rtp/', 1) \
                        .replace('udp://', 'http://192.168.1.1:8888/udp/', 1)
        cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏠家庭内网组播线 [限家里用]",{name} [家庭组播] 🏠')
        cn_lines.append(local_url)
        multicast_count += 1
    print(f"  家庭组播: {multicast_count} 条")

# 2. 公网源汇聚
public_sources = [
    "https://raw.githubusercontent.com/joevess/IPTV/main/m3u/iptv.m3u",
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u"
]

domestic_pool = []
for url in public_sources:
    res = fetch_with_retry(url)
    if res:
        lines = res.text.split('\n')
        for i in range(len(lines)):
            line = lines[i].strip()
            if not line.startswith("#EXTINF"): continue
            ch_name = line.split(',')[-1].strip()
            if not ch_name: continue
            url_line = ""
            for j in range(i+1, min(i+5, len(lines))):
                l = lines[j].strip()
                if l.startswith("#"): continue
                if l.startswith("http"):
                    url_line = l
                    break
            if not url_line: continue
            if "CCTV" in ch_name or "卫视" in ch_name or "重庆" in ch_name:
                domestic_pool.append((ch_name, url_line))
    else:
        print(f"  跳过: {url}")

# 3. 分流限流
ipv4_by_channel = {}
ipv6_by_channel = {}

for ch_name, stream_url in domestic_pool:
    std_name = clean_channel_name(ch_name)
    if not std_name: continue
    bucket = ipv6_by_channel if ("[" in stream_url and "]" in stream_url) else ipv4_by_channel
    if std_name not in bucket: bucket[std_name] = []
    if len(bucket[std_name]) < 3:
        bucket[std_name].append((ch_name, stream_url))

# 4. 写入外网分组
ipv4_count = 0
for std_name in sorted(ipv4_by_channel.keys()):
    logo_url = safe_logo_url(std_name)
    for ch_name, url in ipv4_by_channel[std_name]:
        cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏢公网IPv4通用线 [公司/外网看这个]",{ch_name} [公网直连-v4] 🏢')
        cn_lines.append(url)
        ipv4_count += 1

ipv6_count = 0
for std_name in sorted(ipv6_by_channel.keys()):
    logo_url = safe_logo_url(std_name)
    for ch_name, url in ipv6_by_channel[std_name]:
        cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🚀公网IPv6备用线 [需网络支持IPv6]",{ch_name} [全网备用-v6] 🚀')
        cn_lines.append(url)
        ipv6_count += 1

with open("cn.m3u", "w", encoding="utf-8") as f: f.write("\n".join(cn_lines))
print(f"⚡ cn.m3u: 组播 {multicast_count} + IPv4 {ipv4_count} + IPv6 {ipv6_count}")


# =====================================================================
# PART 2: 全球精选源 -> qq.m3u
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
    res = fetch_with_retry(url, timeout=15)
    if res:
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
                if l.startswith("#"): continue
                if l.startswith("http"):
                    url_line = l
                    break
            if not url_line: continue

            if ch_name in GLOBAL_TRANSLATE: ch_name = GLOBAL_TRANSLATE[ch_name]
            if count < 150:
                raw_global_items.append((group_name, ch_name, url_line, origin_logo, origin_tvgid))
                count += 1
        print(f"  {group_name}: 抓取 {count} 条")
    else:
        print(f"  {group_name}: 多次失败跳过")

print(f"🚀 并发测速 {len(raw_global_items)} 条全球源...")
valid_global = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_link, raw_global_items)
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
print(f"⚡ qq.m3u: 存活 {len(valid_global)} 条, 去重后 {len(seen_global)} 条")
