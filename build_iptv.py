import os
import requests
import re
import concurrent.futures

# =====================================================================
# ⚙️ 核心工具函数（支持标准化台标匹配与大厂CDN识别）
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
    "CNBC": "🇺🇸 CNBC 财经", "Bloomberg TV": "🇺苔 彭博财经",
    "NHK World Premium": "🇯🇵 NHK 世界精品", "KBS World": "🇰🇷 KBS 国际台"
}

# =====================================================================
# PART 1: 构建国内综合源 -> cn.m3u (彻底重命名，显式区分环境)
# =====================================================================
print("========== 开始构建国内综合源 cn.m3u ==========")
cn_lines = ['#EXTM3U x-tvg-url="https://raw.githubusercontent.com/fanmingming/live/main/e.xml"']

# 1. 注入家庭专属组播线（纯净保留，打上专属后缀，绝不在云端测速）
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
            # 在显示名称上直接加上 [家庭组播]，防止在公司误点
            cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏠家庭内网组播线 [限家里看]",{name} [家庭组播] 🏠')
            cn_lines.append(local_url)

# 2. 汇聚全网最顶级的公共 IPv4/IPv6 大库（取消云端测速，保留完整国内大厂节点）
public_sources = [
    "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/ipv6.m3u",
    "https://raw.githubusercontent.com/YueChan/Live/main/APTV.m3u",
    "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.m3u"
]

print("正在跨库聚合国内公网主流源（跳过海外测速以防止误删国内大厂CDN）...")
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
                        
                        # 严格筛选出主力频道
                        if "CCTV" in ch_name or "卫视" in ch_name or "重庆" in ch_name:
                            std_name = clean_channel_name(ch_name)
                            logo_url = f"https://raw.githubusercontent.com/fanmingming/live/main/tv/logos/{std_name}.png"
                            
                            # 识别公司网络极其欢迎的 标准端口 IPv4 线路
                            domain_match = re.search(r'https?://([^/]+)', stream_url)
                            if domain_match:
                                domain = domain_match.group(1)
                                if (临时 := ":" not in domain or ":80" in domain or ":443" in domain) and "[" not in domain:
                                    # 归类为公司友好线
                                    cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🏢公司网络友好线 [IPv4直连]",{ch_name} [公司公网-v4] 🏢')
                                    cn_lines.append(stream_url)
                                else:
                                    # 归类为移动双栈/IPv6线
                                    cn_lines.append(f'#EXTINF:-1 tvg-id="{std_name}" tvg-name="{std_name}" tvg-logo="{logo_url}" group-title="🚀移动双栈全网线 [双栈/IPv6]",{ch_name} [全网备用-v6] 🚀')
                                    cn_lines.append(stream_url)
    except: pass

with open("cn.m3u", "w", encoding="utf-8") as f: f.write("\n".join(cn_lines))
print("⚡ 国内双栈大融合源 cn.m3u 构建成功！")


# =====================================================================
# PART 2: 全球精选源 -> qq.m3u (保持原名，高并发死链清洗 + 自动汉化)
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
                        if len([x for x in raw_global_items if x[0] == group_name]) < 120:
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
print("⚡ 全球汉化纯净版 qq.m3u 生成成功！")
