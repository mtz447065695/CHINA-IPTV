import os
import requests
import re
import concurrent.futures

# =====================================================================
# ⚙️ 核心配置与工具函数
# =====================================================================

def clean_channel_name(name):
    name = name.strip()
    name = re.sub(r'(HD|高清|超清|标清|频道|综合|娱乐|影视|文艺|综艺|体育|新闻|少儿|动漫|字幕|[-—_ ‐一\s]+|[\[\(].*?[\]\)])', '', name, flags=re.IGNORECASE)
    cctv_match = re.search(r'CCTV(\d+\+?)', name, flags=re.IGNORECASE)
    if cctv_match: return f"CCTV{cctv_match.group(1).upper()}"
    return name

# 仿 Guovin/iptv-api：并发双路由死链探测机制
def verify_link(item):
    group_name, ch_name, url = item
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 检测是否为公司防火墙友好的标准端口 (80/443) IPv4 流
    is_company_friendly = False
    domain_match = re.search(r'https?://([^/]+)', url)
    if domain_match:
        domain = domain_match.group(1)
        # 如果域名里不含冒号（默认80/443端口），或者明确指定了 :80 / :443，且不是IPv6的中括号地址
        if (":" not in domain or ":80" in domain or ":443" in domain) and "[" not in domain:
            is_company_friendly = True

    try:
        res = requests.head(url, timeout=2, allow_redirects=True, headers=headers)
        if res.status_code in [200, 206, 301, 302]: return group_name, ch_name, url, is_company_friendly
    except: pass
    try:
        res = requests.get(url, timeout=2, stream=True, headers=headers)
        if res.status_code in [200, 206]: return group_name, ch_name, url, is_company_friendly
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
# PART 1: 多源大融合 -> 国内综合源 cn.m3u (隔离分组避免死锁)
# =====================================================================
print("========== 开始构建国内综合源 cn.m3u ==========")

# 1.1 加载重庆联通本地组播（不测速，只加特定后缀和分组）
raw_multicast = ""
if os.path.exists("Multicast/chongqing/unicom.txt"):
    with open("Multicast/chongqing/unicom.txt", "r", encoding="utf-8") as f: raw_multicast = f.read()

home_multicast_list = []
if raw_multicast:
    for line in raw_multicast.split('\n'):
        line = line.strip()
        if ",rtp://" in line:
            name, rtp_url = line.split(',', 1)
            std_name = clean_channel_name(name)
            local_url = rtp_url.replace("rtp://", "http://192.168.1.1:8888/rtp/")
            home_multicast_list.append((std_name, local_url))

# 1.2 借鉴 Guovin 采集多库：引入全网最强的4个公共 IPv4/IPv6 聚合大库
public_sources = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",  # 优质IPv6库
    "https://raw.githubusercontent.com/YueChan/Live/main/APTV.m3u",             # 经典混合栈
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u",           # 骨干网IPv4/IPv6源
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv.m3u"              # 大厂CDN友好源区
]

to_verify_domestic = []
for url in public_sources:
    try:
        print(f"正在全自动采集公共池: {url}")
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    ch_name = line.split(',')[-1].strip()
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        stream_url = lines[i+1].strip()
                        
                        # 只抓主力台，保持列表干净高速
                        if "CCTV" in ch_name or "卫视" in ch_name or "重庆" in ch_name:
                            group = "央视频道" if "CCTV" in ch_name else "卫视频道"
                            if "重庆" in ch_name: group = "重庆地方台"
                            to_verify_domestic.append((group, ch_name, stream_url))
    except Exception as e:
        print(f"采集链路跳过: {e}")

# 1.3 启动 30 线程云端并发洗牌测速
print(f"🚀 正在对采集到的 {len(to_verify_domestic)} 条公网备线进行生死时速清洗...")
valid_domestic = []
with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
    results = executor.map(verify_link, to_verify_domestic)
    for r in results:
        if r: valid_domestic.append(r)

# 1.4 开始规范组装 cn.m3u (采用严格的分组和命名隔离)
cn_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# A 分组：生成家庭专属组播专线（打上 🏠 标签，你在公司千万别点它！）
if home_multicast_list:
    for std_name, local_url in home_multicast_list:
        logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
        cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏠家庭内网组播线 [限家里看]",{std_name} [家庭专线]')
        cn_lines.append(local_url)

# B 分组：生成公司网络绿色通道（大厂CDN、80/443标准端口、IPv4直连，打上 🏢 标签）
company_lines = [x for x in valid_domestic if x[3] is True]
for group, ch_name, url, _ in company_lines:
    std_name = clean_channel_name(ch_name)
    logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
    cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏢公司外网净化线 [IPv4直连]",{ch_name} [公司极速]')
    cn_lines.append(url)

# C 分组：生成全网全栈双栈流（包含IPv6等其他活链，打上 🚀 标签）
other_public_lines = [x for x in valid_domestic if x[3] is False]
for group, ch_name, url, _ in other_public_lines:
    std_name = clean_channel_name(ch_name)
    logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
    net_label = "[IPv6全栈]" if "[" in url else "[公网备用]"
    cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🚀移动双栈全网线 [双栈/IPv6]",{ch_name} {net_label}')
    cn_lines.append(url)

with open("cn.m3u", "w", encoding="utf-8") as f: f.write("\n".join(cn_lines))
print(f"🎉 国内版 cn.m3u 精密构建成功！公司专属线路保留 {len(company_lines)} 条。")


# =====================================================================
# PART 2: 全球精选源 -> qq.m3u (多线程死链过滤 + 自动汉化)
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
    results = executor.map(verify_link, raw_global_items)
    for r in results:
        if r: valid_global.append(r)

qq_lines = ["#EXTM3U"]
for group_name, ch_name, stream_url, _ in valid_global:
    qq_lines.append(f'#EXTINF:-1 group-title="{group_name}",{ch_name} 🌐')
    qq_lines.append(stream_url)

with open("qq.m3u", "w", encoding="utf-8") as f: f.write("\n".join(qq_lines))
print("⚡ 全球汉化纯净版 qq.m3u 生成成功！全部终极优化完成！")
