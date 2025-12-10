import os
import requests
from collections import defaultdict
import datetime

# --- 配置 ---
# 从环境变量读取配置
API_TOKEN = os.getenv("CF_API_TOKEN")
API_EMAIL = os.getenv("CF_EMAIL")

# Cloudflare API 基地址
API_BASE_URL = "https://api.cloudflare.com/client/v4"
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "X-Auth-Email": API_EMAIL # 部分旧 API 或验证可能需要
}

# 过滤规则：只包含这些类型的记录，通常它们对应网站或服务
ALLOWED_TYPES = {"A", "CNAME", "AAAA"} 
# 排除这些子域名前缀，例如 Cloudflare 默认的验证记录
EXCLUDE_PREFIXES = ["_acme-challenge", "mail", "ftp", "localhost"]
# 目标 HTML 输出文件
OUTPUT_FILE = "index.html" 
# 模板文件
TEMPLATE_FILE = "src/template.html" 

# --- API 访问函数 ---

def get_cloudflare_data(url, params=None):
    """通用的 Cloudflare API GET 请求函数"""
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status() # 检查 HTTP 错误
        data = response.json()
        if not data.get('success'):
            print(f"API 调用失败: {data.get('errors')}")
            return None
        return data.get('result')
    except requests.exceptions.RequestException as e:
        print(f"请求 API 时发生错误: {e}")
        return None

def get_all_zones():
    """获取所有 Zone (域名)"""
    url = f"{API_BASE_URL}/zones"
    return get_cloudflare_data(url)

def get_dns_records(zone_id):
    """获取指定 Zone 的所有 DNS 记录"""
    url = f"{API_BASE_URL}/zones/{zone_id}/dns_records"
    # 分页获取所有记录
    all_records = []
    page = 1
    while True:
        params = {"per_page": 100, "page": page}
        records = get_cloudflare_data(url, params=params)
        if not records:
            break
        all_records.extend(records)
        if len(records) < 100:
            break
        page += 1
    return all_records

# --- 数据处理函数 ---

def is_valid_link_record(record):
    """判断 DNS 记录是否应该被包含在导航站中"""
    name = record['name']
    record_type = record['type']
    
    # 1. 检查记录类型
    if record_type not in ALLOWED_TYPES:
        return False
        
    # 2. 检查子域名前缀
    # name 格式通常是 subdomain.domain.com
    subdomain = name.replace(f".{record['zone_name']}", "")
    if subdomain in EXCLUDE_PREFIXES:
        return False
        
    # 3. 排除一些特殊情况（例如只指向 IPv6/IPv4 地址的根域名）
    # 这里可以根据需要添加更多复杂的过滤规则
    
    return True

def generate_links_html(dns_data):
    """将处理后的 DNS 数据转换成 HTML 链接结构"""
    html_output = []
    
    # 按 Zone Name (域名) 分组
    grouped_data = defaultdict(list)
    for link in dns_data:
        grouped_data[link['zone_name']].append(link)

    # 生成 HTML
    for zone_name, links in grouped_data.items():
        # Zone Group 标题
        html_output.append(f'<div class="zone-group">')
        html_output.append(f'<h2>🌐 {zone_name}</h2>')
        
        # 链接列表
        html_output.append(f'<ul class="link-list">')
        for link in links:
            # 完整的 URL，使用 HTTPS 协议
            full_url = f"https://{link['full_name']}"
            
            # 链接项的 HTML 结构
            item_html = f"""
            <li class="link-item">
                <a href="{full_url}" target="_blank" title="{full_url}">{link['full_name']}</a>
                <p>指向: {link['content']} ({link['type']})</p>
            </li>
            """
            html_output.append(item_html)
            
        html_output.append('</ul>')
        html_output.append('</div>')
        
    return "\n".join(html_output)

# --- 主执行逻辑 ---

def main():
    if not API_TOKEN or not API_EMAIL:
        print("错误: 缺少 CF_API_TOKEN 或 CF_EMAIL 环境变量。请检查配置。")
        return

    print("--- 1. 获取所有 Zone ---")
    zones = get_all_zones()
    if not zones:
        print("未能获取任何 Zone，退出。")
        return

    print(f"成功获取 {len(zones)} 个 Zone。")
    
    # 存储所有有效链接
    all_valid_links = []
    
    print("--- 2. 遍历 Zone 获取 DNS 记录 ---")
    for zone in zones:
        zone_id = zone['id']
        zone_name = zone['name'] # <--- 确保 zone_name 变量在这里被定义
        
        print(f"  > 正在处理 Zone: {zone_name}")
        records = get_dns_records(zone_id)
        if not records:
            continue
            
        for record in records:
            # 【关键修复】手动将 zone_name 添加到 record 字典中，以供后续函数使用
            record['zone_name'] = zone_name 
            
            # 检查记录是否符合导航站标准
            if is_valid_link_record(record): # <--- 现在这里不会报错了
                # 构造最终数据结构
                link_data = {
                    'zone_name': zone_name, # 注意：这里的 zone_name 是从外部变量获取的
                    'full_name': record['name'], 
                    'type': record['type'],
                    'content': record['content']
                }
                all_valid_links.append(link_data)

    print(f"总共找到 {len(all_valid_links)} 个有效网站链接。")

    print("--- 3. 生成 HTML 链接结构 ---")
    links_html = generate_links_html(all_valid_links)

    print("--- 4. 读取模板并替换内容 ---")
    try:
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"错误: 模板文件未找到: {TEMPLATE_FILE}")
        return

    # 替换模板中的占位符
    final_html = template_content.replace("{{ links }}", links_html)

    print("--- 5. 写入最终 HTML 文件 ---")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)
        
    print(f"✅ 导航站生成成功！文件已保存为 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()