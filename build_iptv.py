import os
import requests
import re
import concurrent.futures

# =====================================================================
# ⚙️ 第一部分：公共测速与清洗核心配置
# =====================================================================

# 频道标准化洗白规则（确保台标与节目单100%匹配）
def clean_channel_name(name):
    name = name.strip()
    name = re.sub(r'(HD|高清|超清|标清|频道|综合|娱乐|影视|文艺|综艺|字幕|[-—_ ‐一\s]+|[\[\(].*?[\]\)])', '', name, flags=re.IGNORECASE)
    cctv_match = re.search(r'CCTV(\d+\+?)', name, flags=re.IGNORECASE)
    if cctv_match:
        return f"CCTV{cctv_match.group(1).upper()}"
    return name

# 工业级双路由高并发链探测机制（针对公司防火墙严查进行初筛与流探测）
def verify_link(item):
    group_name, ch_name, url, is_ipv6 = item
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 策略 A：极速 HEAD 探测
    try:
        res = requests.head(url, timeout=2, allow_redirects=True, headers=headers)
        if res.status_code in [200, 206, 301, 302]:
            return group_name, ch_name, url, is_ipv6
    except: pass
    
    # 策略 B：GET 流式低开销拉取探测（针对防爬虫服务器兜底）
    try:
        res = requests.get(url, timeout=2, stream=True, headers=headers)
        if res.status_code in [200, 206]:
            return group_name, ch_name, url, is_ipv6
    except: pass
    
    return None

# 全球高热度大台汉化字典
GLOBAL_TRANSLATE = {
    "CNN International": "🇺🇸 CNN 国际新闻", "BBC News": "🇬🇧 BBC 世界新闻", 
    "BBC World News": "🇬🇧 BBC 世界新闻", "Discovery Channel": "🇺🇸 探索频道",
    "National Geographic": "🇺🇸 国家地理", "HBO": "🇺🇸 HBO 电影台",
    "CNBC": "🇺🇸 CNBC 财经", "Bloomberg TV": "🇺🇸 彭博财经",
    "NHK World Premium": "🇯🇵 NHK 世界精品", "KBS World": "🇰🇷 KBS 国际台"
}

# =====================================================================
# PART 2: 多源汇聚清洗 -> 国内综合源 zh.m3u (IPv4 / IPv6 双栈智能容灾)
# =====================================================================
print("========== 开始构建国内综合源 zh.m3u ==========")

# 1. 读取重庆联通家庭组播（基础固化层，云端不测速，只留内网回家用）
raw_multicast = ""
if os.path.exists("Multicast/chongqing/unicom.txt"):
    with open("Multicast/chongqing/unicom.txt", "r", encoding="utf-8") as f: raw_multicast = f.read()

home_multicast_dict = {}
if raw_multicast:
    for line in raw_multicast.split('\n'):
        line = line.strip()
        if ",rtp://" in line:
            name, rtp_url = line.split(',', 1)
            std_name = clean_channel_name(name)
            home_multicast_dict[std_name] = rtp_url.replace("rtp://", "http://192.168.1.1:8888/rtp/")

# 2. 跨源采集全网公共直播流（结合 Guovin/iptv-api 多模板逻辑，IPv4 与 IPv6 齐抓）
public_sources = [
    {"url": "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u", "type": "IPv6"},  # 经典 IPv6 源
    {"url": "https://raw.githubusercontent.com/YueChan/Live/main/APTV.m3u", "type": "Mixed"},             # 优质混合栈
    {"url": "https://iptv-org.github.io/iptv/countries/cn.m3u", "type": "IPv4"}                         # 全球库中国IPv4区
]

to_verify_domestic = []
for src in public_sources:
    try:
        print(f"正在从 {src['url']} 采集公共通道...")
        res = requests.get(src['url'], timeout=10)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    ch_name = line.split(',')[-1].strip()
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        stream_url = lines[i+1].strip()
                        
                        # 过滤只保留高频主力台，防止臃肿
                        if "CCTV" in ch_name or "卫视" in ch_name or "重庆" in ch_name:
                            is_v6 = True if "ipv6" in stream_url or src['type'] == "IPv6" else False
                            group = "央视频道" if "CCTV" in ch_name else "卫视频道"
                            to_verify_domestic.append((group, ch_name, stream_url, is_v6))
    except Exception as e:
        print(f"采集失败: {e}")

# 3. 启动高并发线程池，当场清洗国内公网死链
print(f"🚀 正在对公网采集的 {len(to_verify_domestic)} 条国内线路进行多线程洗牌测速...")
valid_domestic = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_link, to_verify_domestic)
    for r in results:
        if r: valid_domestic.append(r)

# 4. 聚合写入 zh.m3u（实现多线同名盲切，组播最优先，IPv4/IPv6全栈兜底）
zh_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# 建立全局标准库容器
all_channels = set(list(home_multicast_dict.keys()) + [clean_channel_name(x[1]) for x in valid_domestic])

for ch in sorted(all_channels):
    logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{ch}.png"
    group = "央视频道" if "CCTV" in ch else "卫视频道"
    if "重庆" in ch: group = "重庆地方台"
    
    # 线路 1：注入家庭组播专线（如果你在家，直接走这条秒开）
    if ch in home_multicast_dict:
        zh_lines.append(f'#EXTINF:-1 tvg-id="{ch}" tvg-name="{ch}" tvg-logo="{logo_url}" group-title="{group}",{ch}')
        zh_lines.append(home_multicast_dict[ch])
        
    # 线路 2+：注入经过云端测速存活的公网IPv4/IPv6流（如果你在公司，第一条失败后自动跳到这里）
    ch_lines_public = [x for x in valid_domestic if clean_channel_name(x[1]) == ch]
    for g, name, url, is_v6 in ch_lines_public:
        stack_label = "[IPv6]" if is_v6 else "[IPv4-公司友好]"
        zh_lines.append(f'#EXTINF:-1 tvg-id="{ch}" tvg-name="{ch}" tvg-logo="{logo_url}" group-title="{group}",{ch} {stack_label}')
        zh_lines.append(url)

with open("zh.m3u", "w", encoding="utf-8") as f: f.write("\n".join(zh_lines))
print(f"⚡ 国内双栈融合源 zh.m3u 洗白生成完毕！（保留公网优质活链 {len(valid_domestic)} 条）")


# =====================================================================
# PART 3: 全球精选源 -> qq.m3u (高并发过滤外网死链 + 自动汉化)
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
                            raw_global_items.append((group_name, ch_name, stream_url, False))
    except: pass

print(f"🚀 正在启动全球源 30 线程并发测速（总共待测 {len(raw_global_items)} 条）...")
valid_global = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_link, raw_global_items)
    for r in results:
        if r: valid_global.append(r)

qq_lines = ["#EXTM3U"]
for group_name, ch_name, stream_url, _ in valid_global:
    qq_lines.append(f'#EXTINF:-1 group-title="{group_name}",{ch_name}')
    qq_lines.append(stream_url)

with open("qq.m3u", "w", encoding="utf-8") as f: f.write("\n".join(qq_lines))
print("⚡ 全球汉化纯净版 qq.m3u 生成成功！全部终极优化完成！")
