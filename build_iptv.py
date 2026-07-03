import os
import requests
import re
import concurrent.futures

# =====================================================================
# ⚙️ 核心优化函数
# =====================================================================

def clean_channel_name(name):
    name = name.strip()
    name = re.sub(r'(HD|高清|超清|标清|频道|综合|娱乐|影视|文艺|综艺|体育|新闻|少儿|动漫|字幕|[-—_ ‐一\s]+|[\[\(].*?[\]\)])', '', name, flags=re.IGNORECASE)
    cctv_match = re.search(r'CCTV(\d+\+?)', name, flags=re.IGNORECASE)
    if cctv_match: return f"CCTV{cctv_match.group(1).upper()}"
    return name

# 专为全球源打造的海外死链过滤器（全球源可以放心在云端测速）
def verify_global_link(item):
    group_name, ch_name, url = item
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.head(url, timeout=2, allow_redirects=True, headers=headers)
        if res.status_code in [200, 206, 301, 302]: return group_name, ch_name, url
    except: pass
    try:
        res = requests.get(url, timeout=2, stream=True, headers=headers)
        if res.status_code in [200, 206]: return group_name, ch_name, url
    except: pass
    return None

GLOBAL_TRANSLATE = {
    "CNN International": "🇺🇸 CNN 国际新闻", "BBC News": "🇬🇧 BBC 世界新闻", 
    "BBC World News": "🇬🇧 BBC 世界新闻", "Discovery Channel": "🇺🇸 探索频道",
    "National Geographic": "🇺🇸 国家地理", "HBO": "🇺🇸 HBO 电影台",
    "CNBC": "🇺🇸 CNBC 财经", "Bloomberg TV": "🇺🇸 彭博财经",
    "NHK World Premium": "🇯🇵 NHK 世界精品", "KBS World": "🇰🇷 KBS 国际台"
}

# =====================================================================
# PART 1: 构建国内综合源 -> cn.m3u (更名完成，四重机制分级隔离)
# =====================================================================
print("========== 开始构建国内综合源 cn.m3u ==========")
cn_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# 1.1 注入家庭专属组播线（来自 xisohi/CHINA-IPTV 库，打上专属后缀，限家里看）
raw_multicast = ""
if os.path.exists("Multicast/chongqing/unicom.txt"):
    with open("Multicast/chongqing/unicom.txt", "r", encoding="utf-8") as f: raw_multicast = f.read()

if raw_multicast:
    for line in raw_multicast.split('\n'):
        line = line.strip()
        if ",rtp://" in line:
            name, rtp_url = line.split(',', 1)
            std_name = clean_channel_name(name)
            logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
            local_url = rtp_url.replace("rtp://", "http://192.168.1.1:8888/rtp/")
            cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏠家庭内网组播线 [限家里用]",{name} [家庭组播] 🏠')
            cn_lines.append(local_url)

# 1.2 借鉴 Guovin 采集核心：引入全网最强国内 IPv4/IPv6 大融合池
public_sources = [
    "https://raw.githubusercontent.com/joevess/IPTV/main/m3u/iptv.m3u",          # 顶级IPv4标准端口大库
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",          # 混合栈动态聚合库
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u"   # IPv6补充备线库
]

print("正在全自动跨库提取公网单播链路...")
domestic_pool = []
for url in public_sources:
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    ch_name = line.split(',')[-1].strip()
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        stream_url = lines[i+1].strip()
                        if "CCTV" in ch_name or "卫视" in ch_name or "重庆" in ch_name:
                            domestic_pool.append((ch_name, stream_url))
    except: pass

# 1.3 策略化分级清洗（无需云端测速，通过物理特征直接破开公司防火墙）
print(f"开始对国内公网 {len(domestic_pool)} 条链路进行多级防火墙穿透策略清洗...")

company_friendly_lines = [] # 组别一：公司绝对能看线（IPv4 + 80/443标准端口）
ipv4_high_port_lines = []   # 组别二：普通公网单播线（IPv4 + 搞怪高位端口）
ipv6_lines = []             # 组别三：移动全网双栈线（纯 IPv6）

for ch_name, stream_url in domestic_pool:
    std_name = clean_channel_name(ch_name)
    logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
    
    # 特征 A：如果是 IPv6（链接中带有中括号 [ ]）
    if "[" in stream_url:
        ipv6_lines.append((std_name, ch_name, logo_url, stream_url))
        continue
        
    # 特征 B：提取域名和端口，进行防火墙白名单判断
    domain_match = re.search(r'https?://([^/]+)', stream_url)
    if domain_match:
        domain = domain_match.group(1)
        # 如果不带冒号（默认80/443端口），或者明确指定了 :80 或 :443
        if ":" not in domain or ":80" in domain or ":443" in domain:
            company_friendly_lines.append((std_name, ch_name, logo_url, stream_url))
        else:
            # 带有非标准高位端口（如 :9999）
            ipv4_high_port_lines.append((std_name, ch_name, logo_url, stream_url))

# 1.4 写入 cn.m3u (严格区分线路，按稳定性由高到低排列线路 1、2、3)
# 组别一：公司特快过墙线
for std, name, logo, url in company_friendly_lines:
    cn_lines.append(f'#EXTINF:-1 tvg-id="{std}" tvg-name="{std}" tvg-logo="{logo}" group-title="🏢公司网络特快线 [过墙王-网页端口直连]",{name} [公司公网-v4] 🏢')
    cn_lines.append(url)

# 组别二：普通公网单播线
for std, name, logo, url in ipv4_high_port_lines:
    cn_lines.append(f'#EXTINF:-1 tvg-id="{std}" tvg-name="{std}" tvg-logo="{logo}" group-title="🌍普通公网单播线 [IPv4-高位端口]",{name} [公网单播-v4] 🌍')
    cn_lines.append(url)

# 组别三：移动全网双栈线
for std, name, logo, url in ipv6_lines:
    cn_lines.append(f'#EXTINF:-1 tvg-id="{std}" tvg-name="{std}" tvg-logo="{logo}" group-title="🚀移动双栈全网线 [需支持IPv6]",{name} [移动备用-v6] 🚀')
    cn_lines.append(url)

with open("cn.m3u", "w", encoding="utf-8") as f: f.write("\n".join(cn_lines))
print("⚡ 国内大融合源 cn.m3u 重构完成！")


# =====================================================================
# PART 2: 全球精选源 -> qq.m3u (全球源保持不变，高并发测速过滤)
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
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    ch_name = line.split(',')[-1].strip()
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        stream_url = lines[i+1].strip()
                        if ch_name in GLOBAL_TRANSLATE: ch_name = GLOBAL_TRANSLATE[ch_name]
                        if len([x for x in raw_global_items if x[0] == group_name]) < 150:
                            raw_global_items.append((group_name, ch_name, stream_url))
    except: pass

print(f"🚀 正在启动全球源 30 线程并发测速（总共待测 {len(raw_global_items)} 条）...")
valid_global = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_global_link, raw_global_items)
    for r in results:
        if r: valid_global.append(r)

qq_lines = ["#EXTM3U"]
for group_name, ch_name, stream_url in valid_global:
    qq_lines.append(f'#EXTINF:-1 group-title="{group_name}",{ch_name} 🌐')
    qq_lines.append(stream_url)

with open("qq.m3u", "w", encoding="utf-8") as f: f.write("\n".join(qq_lines))
print("⚡ 全球汉化纯净版 qq.m3u 生成成功！全部终极优化完成！")
