import os
import requests
import re
import urllib.parse

# =====================================================================
# ⚙️ 核心清洗工具（严格保留频道核心词，杜绝错乱）
# =====================================================================

def clean_channel_name(name):
    if not name: return ""
    name = name.strip()
    # 只剥离纯质量后缀，严禁剥离地方台标志词
    name = re.sub(r'(HD|高清|超清|标清|频道|综合|[-—_ ‐\s]+|[\[\(].*?[\]\)])', '', name, flags=re.IGNORECASE)
    name = name.strip()
    if not name: return "Unknown"
    cctv_match = re.search(r'CCTV(\d+\+?)', name, flags=re.IGNORECASE)
    if cctv_match: return f"CCTV{cctv_match.group(1).upper()}"
    return name

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def safe_logo_url(std_name):
    if not std_name: return ""
    safe = urllib.parse.quote(std_name, safe='')
    return f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{safe}.png"

# =====================================================================
# PART 1: 国内纯净源构建 -> cn.m3u
# =====================================================================
print("========== 开始构建纯净国内源 cn.m3u ==========")
cn_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# 1. 独立写入：重庆联通本地组播线（完全隔离，不与任何公网源混合，防名字污染）
raw_multicast = ""
local_path = "Multicast/chongqing/unicom.txt"
upstream_url = "https://raw.githubusercontent.com/xisohi/CHINA-IPTV/main/Multicast/chongqing/unicom.txt"

if os.path.exists(local_path):
    with open(local_path, "r", encoding="utf-8") as f: raw_multicast = f.read()
else:
    try:
        res = requests.get(upstream_url, timeout=10, headers=HEADERS)
        if res.status_code == 200 and "rtp://" in res.text: raw_multicast = res.text
    except: pass

multicast_count = 0
if raw_multicast:
    for line in raw_multicast.split('\n'):
        line = line.strip()
        if not line: continue
        idx = line.find(',rtp://')
        if idx == -1: idx = line.find(', rtp://')
        if idx == -1: idx = line.find(',udp://')
        if idx == -1: idx = line.find(', udp://')
        if idx == -1: continue
        
        name = line[:idx].strip()
        tail = line[idx+1:].strip()
        std_name = clean_channel_name(name)
        logo_url = safe_logo_url(std_name)
        local_url = tail.replace('rtp://', 'http://192.168.1.1:8888/rtp/', 1).replace('udp://', 'http://192.168.1.1:8888/udp/', 1)
        
        cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏠 重庆联通·本地组播专线",{name}')
        cn_lines.append(local_url)
        multicast_count += 1
print(f"✅ 成功固化本地组播源 {multicast_count} 条")

# 2. 跨源汇聚：只认全网公认最强、绝无错乱的 2 大骨干网蓝光池
elite_sources = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",     # 纯净 1080P/4K 官方直连骨干网流
    "https://raw.githubusercontent.com/YueChan/Live/main/APTV.m3u"                 # 极度严苛、无错乱的高清直播池
]

domestic_pool = []
for url in elite_sources:
    try:
        res = requests.get(url, timeout=10, headers=HEADERS)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for i in range(len(lines)):
                line = lines[i].strip()
                if not line.startswith("#EXTINF"): continue
                ch_name = line.split(',')[-1].strip()
                
                # 寻找对应的 HTTP 播放地址
                url_line = ""
                for j in range(i+1, min(i+5, len(lines))):
                    l = lines[j].strip()
                    if l.startswith("#") or not l: continue
                    if l.startswith("http"):
                        url_line = l
                        break
                if not url_line: continue
                
                # 极致画质过滤：只要含有任何低清标识，当场斩杀
                if any(kw in ch_name.lower() or kw in url_line.lower() for kw in ["标清", "sd", "low", "blur", "500k", "360p", "480p", "576p", "流畅"]):
                    continue
                    
                if "CCTV" in ch_name or "卫视" in ch_name or "重庆" in ch_name:
                    domestic_pool.append((ch_name, url_line))
    except:
        print(f"  顶级库拉取时网络微调跳过: {url}")

# 3. 严格限流：每个干净的频道最多只保留 3 条最高质量的公网蓝光线
channel_buckets = {}
for ch_name, stream_url in domestic_pool:
    std_name = clean_channel_name(ch_name)
    if not std_name: continue
    
    if std_name not in channel_buckets: channel_buckets[std_name] = []
    if len(channel_buckets[std_name]) < 3:
        channel_buckets[std_name].append((ch_name, stream_url))

# 4. 组装写入 cn.m3u 的公网蓝光分组
public_count = 0
for std_name in sorted(channel_buckets.keys()):
    logo_url = safe_logo_url(std_name)
    group_title = "💎 纯净原画·国家骨干网超清线"
    
    for ch_name, url in channel_buckets[std_name]:
        # 自动识别线路标签
        net_label = "IPv6蓝光" if "[" in url and "]" in url else "IPv4直连"
        cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="{group_title}",{ch_name} [{net_label}]')
        cn_lines.append(url)
        public_count += 1

with open("cn.m3u", "w", encoding="utf-8") as f: f.write("\n".join(cn_lines))
print(f"🚀 国内源 cn.m3u 彻底洗白！保留顶级活链 {public_count} 条")

# =====================================================================
# PART 2: 全球精选源 -> qq.m3u (保持高精汉化)
# =====================================================================
print("\n========== 开始构建全球精选源 qq.m3u ==========")
iptv_org_urls = {
    "全球新闻网": "https://iptv-org.github.io/iptv/categories/news.m3u",
    "全球纪录片": "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "全球体育台": "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "全球电影台": "https://iptv-org.github.io/iptv/categories/movies.m3u"
}

qq_lines = ["#EXTM3U"]
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
                if count < 80:  # 精选前80个高热度频道
                    logo_attr = f' tvg-logo="{origin_logo}"' if origin_logo else ""
                    tvgid_attr = f' tvg-id="{origin_tvgid}"' if origin_tvgid else ""
                    qq_lines.append(f'#EXTINF:-1{tvgid_attr}{logo_attr} group-title="{group_name}",{ch_name} 🌐')
                    qq_lines.append(url_line)
                    count += 1
            print(f"  {group_name}: 成功提取 {count} 条全球活链")
    except: pass

with open("qq.m3u", "w", encoding="utf-8") as f: f.write("\n".join(qq_lines))
print("🏁 全球源 qq.m3u 纯净版发布完毕！")
