import os
import requests

# ==================== PART 1: 国内重庆联通组播清洗 ====================
local_backup_path = "Multicast/chongqing/unicom.txt"
upstream_url = "https://raw.githubusercontent.com/xisohi/CHINA-IPTV/main/Multicast/chongqing/unicom.txt"
raw_data = ""

try:
    print("正在尝试从原作者仓库获取最新联通组播地址...")
    response = requests.get(upstream_url, timeout=10)
    if response.status_code == 200 and "rtp://" in response.text:
        raw_data = response.text
        print("🎉 成功获取国内上游最新数据！")
except Exception as e:
    print(f"⚠️ 警报：国内上游仓库异常 ({e})！启动容灾方案...")

if not raw_data and os.path.exists(local_backup_path):
    with open(local_backup_path, "r", encoding="utf-8") as f:
        raw_data = f.read()

# 开始构建国内版 live.m3u
if raw_data:
    m3u_lines = ["#EXTM3U"]
    current_group = "未分类"
    for line in raw_data.split('\n'):
        line = line.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if ",#genre#" in line:
            current_group = line.split(',')[0]
        elif ",rtp://" in line:
            name, rtp_url = line.split(',', 1)
            # 自动注入爱快内网 udpxy 地址（若爱快LAN口不是192.168.1.1请自行修改）
            local_url = rtp_url.replace("rtp://", "http://192.168.1.1:8888/rtp/")
            m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{name}')
            m3u_lines.append(local_url)
    
    with open("live.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
    print("⚡ 国内版 live.m3u 生成成功！")


# ==================== PART 2: 全球 iptv-org 精选源抓取 ====================
# 在这里定义你想看的外网优质分类（避开8万个频道的死亡大总表）
iptv_org_urls = {
    "全球新闻网": "https://iptv-org.github.io/iptv/categories/news.m3u",
    "全球纪录片": "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "全球体育台": "https://iptv-org.github.io/iptv/categories/sports.m3u"
}

global_m3u_lines = ["#EXTM3U"]

print("正在从 iptv-org 抓取全球精选频道...")
for group_name, url in iptv_org_urls.items():
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            lines = res.text.split('\n')
            # 循环解析 iptv-org 的原生 m3u 格式并重新规整分组
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    # 提取原频道名称（英文名）
                    ch_name = line.split(',')[-1]
                    # 下一行通常是播放链接
                    if i + 1 < len(lines) and lines[i+1].strip().startswith("http"):
                        stream_url = lines[i+1].strip()
                        global_m3u_lines.append(f'#EXTINF:-1 group-title="{group_name}",{ch_name}')
                        global_m3u_lines.append(stream_url)
            print(f"✅ {group_name} 分类抓取成功！")
    except Exception as e:
        print(f"❌ 抓取 {group_name} 失败: {e}")

# 输出全球版 global.m3u
with open("global.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(global_m3u_lines))
print("⚡ 全球精选版 global.m3u 生成成功！")
