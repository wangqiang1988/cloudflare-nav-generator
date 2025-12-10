import os
import sys
import requests
from collections import defaultdict
from dotenv import dotenv_values # 用于直接读取 .env 文件内容

# --- 配置加载 (不使用 os.getenv) ---

# 1. 获取当前脚本的目录
script_dir = os.path.dirname(os.path.abspath(__file__))

# 2. 构造 .env 文件的路径：向上退一级到项目根目录
dotenv_path_raw = os.path.join(script_dir, '..', '.env')

# 3. 标准化路径：清理掉路径中的 '..'，保证 Windows/Linux 环境下的路径正确性
dotenv_path = os.path.normpath(dotenv_path_raw)

# 4. 读取 .env 文件内容到 config 字典
config = dotenv_values(dotenv_path) 

# --- 配置项获取 ---
API_TOKEN = config.get("CF_API_TOKEN")
API_EMAIL = config.get("CF_EMAIL")

# Cloudflare API 基地址
API_BASE_URL = "https://api.cloudflare.com/client/v4"

# 检查配置是否缺失
if not API_TOKEN or not API_EMAIL:
    print("错误: 缺少 CF_API_TOKEN 或 CF_EMAIL 配置项。请检查 .env 文件。")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "X-Auth-Email": API_EMAIL
}

# 过滤规则：只包含这些类型的记录，通常它们对应网站或服务
ALLOWED_TYPES = {"A", "CNAME", "AAAA"} 
# 排除这些子域名前缀
EXCLUDE_PREFIXES = ["_acme-challenge", "mail", "ftp", "localhost"]
# 目标 HTML 输出文件
OUTPUT_FILE = "index.html" 
# 模板文件 (位于 src 目录)
TEMPLATE_FILE = os.path.join(script_dir, "template.html") 

# --- API 访问函数 ---

def get_cloudflare_data(url, params=None):
    """通用的 Cloudflare API GET 请求函数"""
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        if not data.get('success'):
            print(f"API 调用失败: {data.get('errors')}")
            return None
        # 处理分页，确保获取所有结果
        all_results = data.get('result', [])
        page_info = data.get('result_info', {})
        total_pages = page_info.get('total_pages', 1)
        
        for page in range(2, total_pages + 1):
            params = params or {}
            params['page'] = page
            response = requests.get(url, headers=HEADERS, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            all_results.extend(data.get('result', []))
            
        return all_results
    except requests.exceptions.RequestException as e:
        print(f"请求 API 时发生错误: {e}")
        return None
    except Exception as e:
        print(f"处理 API 响应时发生未知错误: {e}")
        return None

def get_all_zones():
    """获取所有 Zone (域名)"""
    url = f"{API_BASE_URL}/zones"
    return get_cloudflare_data(url)

def get_dns_records(zone_id):
    """获取指定 Zone 的所有 DNS 记录 (不处理分页，由 get_cloudflare_data 内部处理)"""
    url = f"{API_BASE_URL}/zones/{zone_id}/dns_records"
    # 注意：这里我们不再需要手动分页，让 get_cloudflare_data 处理
    return get_cloudflare_data(url, params={"per_page": 100}) 

# --- 新增：从执行脚本主机检测 URL 状态 ---

def check_url_status(url):
    """
    从执行脚本的主机向目标 URL 发起 HEAD 请求，返回状态码。
    """
    try:
        # 使用 HEAD 请求，设置 User-Agent，允许重定向
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 CloudflareNavGenerator'
        }
        
        response = requests.head(url, timeout=5, allow_redirects=True, headers=headers)
        return response.status_code
    except requests.exceptions.RequestException:
        # 999 代表网络连接或超时失败
        return 999


# --- 数据处理函数 ---

def is_valid_link_record(record):
    """判断 DNS 记录是否应该被包含在导航站中"""
    name = record['name']
    record_type = record['type']
    
    if record_type not in ALLOWED_TYPES:
        return False
        
    subdomain = name.replace(f".{record['zone_name']}", "")
    for prefix in EXCLUDE_PREFIXES:
        if name.startswith(prefix + '.'):
            return False
        
    return True

def generate_links_html(dns_data):
    """将处理后的 DNS 数据转换成 HTML 链接结构"""
    html_output = []
    
    grouped_data = defaultdict(list)
    for link in dns_data:
        grouped_data[link['zone_name']].append(link)

    # 生成 HTML
    for zone_name, links in grouped_data.items():
        html_output.append(f'<div class="zone-group">')
        html_output.append(f'<h2>🌐 {zone_name}</h2>')
        html_output.append(f'<ul class="link-list">')
        
        for link in links:
            full_url = f"https://{link['full_name']}"
            status_code = link['status_code']
            
            # 根据状态码决定样式和文本
            if status_code >= 200 and status_code < 400:
                status_class = 'status-ok'
                status_text = f'在线: {status_code}'
            elif status_code == 999:
                status_class = 'status-net-error'
                status_text = '连接失败'
            else:
                status_class = 'status-error'
                status_text = f'错误: {status_code}'

            item_html = f"""
            <li class="link-item">
                <a href="{full_url}" target="_blank" title="{full_url}">{link['full_name']}</a>
                <p>指向: {link['content']} ({link['type']})</p>
                <div class="status-area">
                    <span class="status-display {status_class}">
                        {status_text}
                    </span>
                    <span class="status-test-url" title="检测URL">({link['test_url']})</span>
                </div>
            </li>
            """
            html_output.append(item_html)
            
        html_output.append('</ul>')
        html_output.append('</div>')
        
    return "\n".join(html_output)

# --- 主执行逻辑 ---

def main():
    print("--- 1. 获取所有 Zone ---")
    zones = get_all_zones()
    if not zones:
        print("未能获取任何 Zone，退出。")
        return

    print(f"成功获取 {len(zones)} 个 Zone。")
    
    all_valid_links = []
    
    print("--- 2. 遍历 Zone 获取 DNS 记录并执行实时检测 ---")
    for zone in zones:
        zone_id = zone['id']
        zone_name = zone['name']
        
        print(f"  > 正在处理 Zone: {zone_name}")
        records = get_dns_records(zone_id)
        if not records:
            continue
            
        for record in records:
            record['zone_name'] = zone_name # 附带 zone_name
            
            if is_valid_link_record(record):
                full_name = record['name']
                test_url = f"https://{full_name}" 
                
                # 【实时检测】
                status_code = check_url_status(test_url)
                print(f"    - {full_name}: {status_code}") 
                
                link_data = {
                    'zone_name': zone_name,
                    'full_name': full_name, 
                    'type': record['type'],
                    'content': record['content'],
                    'status_code': status_code,  # 结果
                    'test_url': test_url         # 测试URL
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

    final_html = template_content.replace("{{ links }}", links_html)

    print("--- 5. 写入最终 HTML 文件 ---")
    output_path = os.path.join(os.path.dirname(script_dir), OUTPUT_FILE)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)
        
    print(f"✅ 导航站生成成功！文件已保存为 {output_path}")

if __name__ == "__main__":
    main()