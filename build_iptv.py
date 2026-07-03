import os
import requests

# 1. 定义本地备份路径和上游开源地址
local_backup_path = "Multicast/chongqing/unicom.txt"
upstream_url = "https://raw.githubusercontent.com/xisohi/CHINA-IPTV/main/Multicast/chongqing/unicom.txt"

raw_data = ""

# 2. 容灾逻辑：优先抓取最新，失败则读取你专属的 Fork 本地备份
try:
    print("正在尝试从原作者仓库获取最新联通组播地址...")
    response = requests.get(upstream_url, timeout=10)
    if response.status_code == 200 and "rtp://" in response.text:
        raw_data = response.text
        print("🎉 成功获取上游最新数据！")
except Exception as e:
    print(f"⚠️ 警报：上游仓库异常 ({e})！启动容灾方案，读取本地历史备份...")

if not raw_data:
    if os.path.exists(local_backup_path):
        with open(local_backup_path, "r", encoding="utf-8") as f:
            raw_data = f.read()
        print("✅ 成功加载本地自身备份，业务未受影响！")
    else:
        print("❌ 严重错误：未找到任何可用备份！")
        exit(1)

# 3. 开始转换格式并注入你爱快的 udpxy 代理网关
m3u_lines = ["#EXTM3U"]
current_group = "未分类"

lines = raw_data.split('\n')
for line in lines:
    line = line.strip()
    if not line:
        continue
    if ",#genre#" in line:
        current_group = line.split(',')[0]
    elif ",rtp://" in line:
        name, rtp_url = line.split(',', 1)
        
        # 【核心】自动将 rtp:// 换成你家爱快内网 udpxy 服务的地址与端口
        # 注意：如果你的爱快 LAN 口 IP 不是 192.168.1.1，请在下方修改
        local_url = rtp_url.replace("rtp://", "http://192.168.1.1:8888/rtp/")
        
        m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{name}')
        m3u_lines.append(local_url)

# 4. 在根目录下输出供全家电视订阅的 live.m3u 文件
with open("live.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(m3u_lines))

print("⚡ 专属播放列表 live.m3u 构建洗白完成！")
