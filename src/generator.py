import os
import sys
import requests
from collections import defaultdict
from dotenv import dotenv_values 
import concurrent.futures # 引入线程池模块

# --- 配置加载 (保持不变) ---
script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path_raw = os.path.join(script_dir, '..', '.env')
dotenv_path = os.path.normpath(dotenv_path_raw)
config = dotenv_values(dotenv_path) 

API_TOKEN = config.get("CF_API_TOKEN")
API_EMAIL = config.get("CF_EMAIL")

SHOW_RECORD_CONTENT = config.get("SHOW_RECORD_CONTENT", "True").lower() == "true"
SHOW_RECORD_STATUS = config.get("SHOW_RECORD_STATUS", "True").lower() == "true"

skip_detection_raw = config.get("SKIP_DETECTION_PREFIXES", "")
hide_record_raw = config.get("HIDE_RECORD_PREFIXES", "")

API_BASE_URL = "https://api.cloudflare.com/client/v4"

if not API_TOKEN or not API_EMAIL:
    print("错误: 缺少 CF_API_TOKEN 或 CF_EMAIL 配置项。请检查 .env 文件。")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "X-Auth-Email": API_EMAIL
}

ALLOWED_TYPES = {"A", "CNAME", "AAAA"} 
EXCLUDE_PREFIXES = {"_acme-challenge", "mail", "ftp", "localhost"} 

SKIP_DETECTION_PREFIXES = {p.strip() for p in skip_detection_raw.split(',') if p.strip()}
HIDE_RECORD_PREFIXES = {p.strip() for p in hide_record_raw.split(',') if p.strip()}

OUTPUT_FILE = "index.html" 
TEMPLATE_FILE = os.path.join(script_dir, "template.html") 

# --- API 访问函数 (保持不变，但会在线程中调用) ---

def get_cloudflare_data(url, params=None):
    """通用的 Cloudflare API GET 请求函数 (处理分页)"""
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        if not data.get('success'):
            # 返回 None 表示失败，并打印错误
            return None, data.get('errors')
        
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
            
        return all_results, None
    except requests.exceptions.RequestException as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)

def get_all_zones():
    """获取所有 Zone (域名)"""
    url = f"{API_BASE_URL}/zones"
    # 这里不需要多线程，只需要调用一次
    zones, error = get_cloudflare_data(url)
    if error:
        print(f"获取所有 Zones 失败: {error}")
    return zones

def get_dns_records(zone_id):
    """获取指定 Zone 的所有 DNS 记录"""
    url = f"{API_BASE_URL}/zones/{zone_id}/dns_records"
    records, error = get_cloudflare_data(url, params={"per_page": 100}) 
    if error:
        print(f"获取 Zone {zone_id} 的 DNS 记录失败: {error}")
    return records

# --- 状态检测函数 (保持不变，但会在线程中调用) ---

def check_url_status(url):
    """从执行脚本的主机向目标 URL 发起 HEAD 请求，返回状态码。"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 CloudflareNavGenerator'
        }
        response = requests.head(url, timeout=5, allow_redirects=True, headers=headers)
        return response.status_code
    except requests.exceptions.RequestException:
        return 999


# --- 数据过滤函数 (保持不变) ---

def is_valid_link_record(record):
    """判断 DNS 记录是否应该被包含在导航站中"""
    name = record['name']
    record_type = record['type']
    
    if record_type not in ALLOWED_TYPES:
        return False
        
    for prefix in EXCLUDE_PREFIXES:
        if name.startswith(prefix + '.'):
            return False
            
    for prefix in HIDE_RECORD_PREFIXES:
        if name.startswith(prefix + '.'):
            return False 
            
    return True

# --- HTML 生成函数 (保持不变) ---

def generate_links_html(dns_data):
    """将处理后的 DNS 数据转换成 HTML 链接结构"""
    html_output = []
    
    grouped_data = defaultdict(list)
    for link in dns_data:
        grouped_data[link['zone_name']].append(link)

    for zone_name, links in grouped_data.items():
        html_output.append(f'<div class="zone-group">')
        html_output.append(f'<h2>🌐 {zone_name}</h2>')
        html_output.append(f'<ul class="link-list">')
        
        for link in links:
            full_url = f"https://{link['full_name']}"
            
            content_html = ""
            if SHOW_RECORD_CONTENT:
                content_html = f"<p>指向: {link['content']} ({link['type']})</p>"
                
            status_html = ""
            if SHOW_RECORD_STATUS:
                status_code = link['status_code']
                
                if status_code >= 200 and status_code < 400:
                    status_class = 'status-ok'
                    status_text = f'在线: {status_code}'
                elif status_code == 888: 
                    status_class = 'status-skipped'
                    status_text = '跳过检测'
                elif status_code == 999:
                    status_class = 'status-net-error'
                    status_text = '连接失败'
                else:
                    status_class = 'status-error'
                    status_text = f'错误: {status_code}'
                
                status_html = f"""
                <div class="status-area">
                    <span class="status-display {status_class}">
                        {status_text}
                    </span>
                    <span class="status-test-url" title="检测URL">({link['test_url']})</span>
                </div>
                """

            item_html = f"""
            <li class="link-item">
                <a href="{full_url}" target="_blank" title="{full_url}">{link['full_name']}</a>
                {content_html} 
                {status_html}
            </li>
            """
            html_output.append(item_html)
            
        html_output.append('</ul>')
        html_output.append('</div>')
        
    return "\n".join(html_output)

# --- 辅助函数：处理单个 DNS 记录的状态检测 ---

def process_record_status(record_data):
    """
    接收一个包含 DNS 记录和 Zone 信息的字典，执行状态检测并返回结果。
    """
    zone_name = record_data['zone_name']
    record = record_data['record']
    
    # 1. 检查是否应该隐藏该记录
    if not is_valid_link_record(record):
        return None # 隐藏的记录返回 None
        
    full_name = record['name']
    test_url = f"https://{full_name}" 
    status_code = 0 
    
    # 2. 检查是否应该跳过检测
    perform_status_check = SHOW_RECORD_STATUS 
    should_skip_detection_by_config = False
    for prefix in SKIP_DETECTION_PREFIXES:
        if full_name.startswith(prefix + '.'):
            should_skip_detection_by_config = True
            break
    
    if not perform_status_check or should_skip_detection_by_config:
        # 【跳过检测】：使用 888 表示跳过
        status_code = 888 
        if perform_status_check:
            # 仅在 SHOW_RECORD_STATUS=True 时打印配置跳过的日志
            print(f"    - [{zone_name}] {full_name}: 检测跳过 (配置排除)") 
    else:
        # 【执行检测】
        status_code = check_url_status(test_url)
        print(f"    - [{zone_name}] {full_name}: {status_code}") 
    
    # 构造最终的数据结构
    link_data = {
        'zone_name': zone_name,
        'full_name': full_name, 
        'type': record['type'],
        'content': record['content'],
        'status_code': status_code, 
        'test_url': test_url        
    }
    return link_data


# --- 主执行逻辑 (使用 ThreadPoolExecutor 进行多线程加速) ---

def main():
    NUM_WORKERS = 5 # 线程数量设置为 5
    
    print("--- 1. 获取所有 Zone ---")
    zones = get_all_zones()
    if not zones:
        print("未能获取任何 Zone，退出。")
        return

    print(f"成功获取 {len(zones)} 个 Zone。")
    
    all_records_to_process = []
    
    # 阶段一：收集所有 DNS 记录 (仍保持串行获取，因为不同 Zone 的 API 调用是独立的)
    # 如果 Zone 数量很少，这一步串行速度通常足够快。
    print("--- 2. 串行遍历 Zone 并收集所有 DNS 记录 ---")
    for zone in zones:
        zone_id = zone['id']
        zone_name = zone['name']
        print(f"  > 正在获取 Zone: {zone_name} 的记录...")
        records = get_dns_records(zone_id)
        if records:
            for record in records:
                all_records_to_process.append({
                    'zone_name': zone_name,
                    'record': record
                })
                
    print(f"总共收集到 {len(all_records_to_process)} 条 DNS 记录准备进行状态检测。")
    
    # 阶段二：并行执行 URL 状态检测
    all_valid_links = []
    
    if all_records_to_process:
        print(f"--- 3. 启动 {NUM_WORKERS} 个线程并行执行 URL 状态检测 ---")
        
        # 使用 ThreadPoolExecutor 创建线程池
        with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
            # 将每个记录的处理任务提交给线程池
            # submit() 返回一个 Future 对象，result() 会获取其返回值
            future_to_record = {
                executor.submit(process_record_status, record_data): record_data 
                for record_data in all_records_to_process
            }
            
            # 遍历已完成的 Future 对象，获取结果
            for future in concurrent.futures.as_completed(future_to_record):
                link_data = future.result()
                
                # 如果结果不是 None (即记录没有被隐藏)，则添加到列表中
                if link_data:
                    all_valid_links.append(link_data)

    print(f"总共找到 {len(all_valid_links)} 个有效网站链接并完成了状态检测。")

    print("--- 4. 生成 HTML 链接结构 ---")
    links_html = generate_links_html(all_valid_links) 

    print("--- 5. 读取模板并替换内容 ---")
    try:
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"错误: 模板文件未找到: {TEMPLATE_FILE}")
        return

    final_html = template_content.replace("{{ links }}", links_html)

    print("--- 6. 写入最终 HTML 文件 ---")
    output_path = os.path.join(os.path.dirname(script_dir), OUTPUT_FILE)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_html)
        
    print(f"✅ 导航站生成成功！文件已保存为 {output_path}")

if __name__ == "__main__":
    main()