import os
import requests
import re
import concurrent.futures

# =====================================================================
# ⚙️ 顶级优化字典与函数定义
# =====================================================================

# 汉化字典：将全球高热度大台自动翻译为中文
GLOBAL_TRANSLATE = {
    "CNN International": "🇺🇸 CNN 国际新闻",
    "BBC News": "🇬🇧 BBC 世界新闻",
    "BBC World News": "🇬🇧 BBC 世界新闻",
    "Discovery Channel": "🇺🇸 探索频道",
    "National Geographic": "🇺🇸 国家地理",
    "HBO": "🇺🇸 HBO 电影台",
    "CNBC": "🇺🇸 CNBC 财经",
    "Bloomberg TV": "🇺🇸 彭博财经",
    "NHK World Premium": "🇯🇵 NHK 世界精品",
    "KBS World": "🇰🇷 KBS 国际台"
}

def clean_channel_name(name):
    name = name.strip()
    name = re.sub(r'(HD|高清|超清|标清|频道|综合|字幕|[-—_ ‐一\s]+|[\[\(].*?[\]\)])', '', name, flags=re.IGNORECASE)
    cctv_match = re.search(r'CCTV(\d+\+?)', name, flags=re.IGNORECASE)
    if cctv_match:
        return f"CCTV{cctv_match.group(1).upper()}"
    return name

def verify_global_link(item):
    group_name, ch_name, url = item
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.head(url, timeout=2, allow_redirects=True, headers=headers)
        if res.status_code in [200, 206, 301, 302]: return group_name, ch_name, url
    except: pass
    try:
        res = requests.get(url, timeout=2, stream=True, headers=headers)
        if res.status_code in [200, 206]: return group_name, ch_name, url
    except: pass
    return None

# =====================================================================
# PART 1: 国内综合源 -> zh.m3u (多源同名无感聚合)
# =====================================================================
print("正在构建国内无感融合源...")
raw_multicast = ""
try:
    response = requests.get("https://raw.githubusercontent.com/xisohi/CHINA-IPTV/main/Multicast/chongqing/unicom.txt", timeout=10)
    if response.status_code == 200: raw_data = response.text
except:
    if os.path.exists("Multicast/chongqing/unicom.txt"):
        with open("Multicast/chongqing/unicom.txt", "r", encoding="utf-8") as f: raw_data = f.read()

# 解析家庭组播数据存入字典
multicast_dict = {}
if raw_data:
    for line in raw_data.split('\n'):
        line = line.strip()
        if ",rtp://" in line:
            name, rtp_url = line.split(',', 1)
            standard_name = clean_channel_name(name)
            multicast_dict[standard_name] = rtp_url.replace("rtp://", "http://192.168.1.1:8888/rtp/")

# 抓取公网 IPv6 移动源并进行同名合并
zh_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']
try:
    res = requests.get("https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u", timeout=15)
    if res.status_code == 200:
        lines = res.text.split('\n')
        for i in range(len(lines)):
            line = lines[i].strip()
            if line.startswith("#EXTINF"):
                group_match = re.search(r'group-title="([^"]+)"', line)
                pub_group = group_match.group(1) if group_match else "各地卫视"
                ch_name = line.split(',')[-1].strip()
                
                if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                    public_url = lines[i+1].strip()
                    
                    if "CCTV" in ch_name or "卫视" in ch_name:
                        standard_name = clean_channel_name(ch_name)
                        logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{standard_name}.png"
                        
                        # 【神仙级改动】如果这个台在家里有组播源，让组播当线路1，公网当线路2，名字保持绝对一致！
                        if standard_name in multicast_dict:
                            zh_lines.append(f'#EXTINF:-1 tvg-id="{standard_name}" tvg-name="{standard_name}" tvg-logo="{logo_url}" group-title="{pub_group}",{ch_name}')
                            zh_lines.append(multicast_dict[standard_name])
                            del multicast_dict[standard_name] # 避免重复打印
                        
                        # 写入外网线路（作为备线）
                        zh_lines.append(f'#EXTINF:-1 tvg-id="{standard_name}" tvg-name="{standard_name}" tvg-logo="{logo_url}" group-title="{pub_group}",{ch_name}')
                        zh_lines.append(public_url)
except Exception as e:
    print(f"公网源聚合异常: {e}")

# 兜底：把剩下的只有家庭组播有的地方台也写进去
for std_name, local_url in multicast_dict.items():
    logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
    zh_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="重庆地方台",{std_name}')
    zh_lines.append(local_url)

with open("zh.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(zh_lines))

# =====================================================================
# PART 2: 构建全球精选源 -> qq.m3u (多线程死链过滤 + 自动汉化)
# =====================================================================
iptv_org_urls = {
    "全球新闻网": "https://iptv-org.github.io/iptv/categories/news.m3u",
    "全球纪录片": "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "全球体育台": "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "全球电影台": "https://iptv-org.github.io/iptv/categories/movies.m3u"
}

raw_global_items = []
for group_name, url in iptv_org_urls.items():
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    ch_name = line.split(',')[-1].strip()
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        stream_url = lines[i+1].strip()
                        # 汉化触发：如果在字典里，转换名字
                        if ch_name in GLOBAL_TRANSLATE:
                            ch_name = GLOBAL_TRANSLATE[ch_name]
                        if len([x for x in raw_global_items if x[0] == group_name]) < 120:
                            raw_global_items.append((group_name, ch_name, stream_url))
    except: pass

valid_global_items = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_global_link, raw_global_items)
    for result in results:
        if result: valid_global_items.append(result)

qq_lines = ["#EXTM3U"]
for group_name, ch_name, stream_url in valid_global_items:
    qq_lines.append(f'#EXTINF:-1 group-title="{group_name}",{ch_name}')
    qq_lines.append(stream_url)

with open("qq.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(qq_lines))
print("全部终极优化完成！")
