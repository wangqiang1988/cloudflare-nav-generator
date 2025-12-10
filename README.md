# 🌐 Cloudflare DNS 导航站生成器 (Cloudflare DNS Nav Generator)

这是一个自动化项目，用于通过 Cloudflare API 获取你账户下的所有 DNS
记录（网站类记录），并自动生成一个美观、易用的静态导航页面。告别手动维护导航链接，让你的所有域名一目了然！

## ✨ 主要功能

-   **API 驱动**：通过 Cloudflare API 实时拉取 DNS 记录。
-   **智能过滤**：自动排除 `TXT`、`MX`、`SRV` 等非网站记录，仅保留
    `A`、`CNAME`、`AAAA`。
-   **按 Zone 分组**：导航链接根据域名（Zone）自动分组展示。
-   **静态生成**：输出纯静态 HTML，可部署在 Cloudflare Pages、GitHub
    Pages 或任意静态托管服务。
-   **GitHub Actions 自动化**：支持定时任务自动同步 DNS 变化并部署。

## 🛠️ 项目结构

    /cloudflare-nav-generator
    ├── .github/workflows/
    │   └── deploy.yml          # GitHub Actions 自动化部署配置
    ├── src/
    │   ├── generator.py        # Python 核心脚本：API 调用、数据处理、HTML 生成
    │   └── template.html       # HTML 页面模板
    ├── index.html              # 最终生成的导航页
    ├── requirements.txt        # Python 依赖
    └── README.md

## 🚀 快速开始

### 步骤 1 --- 环境准备

1.  克隆仓库：

``` bash
git clone https://github.com/你的用户名/cloudflare-nav-generator.git
cd cloudflare-nav-generator
```

2.  安装依赖：

``` bash
pip install -r requirements.txt
```

### 步骤 2 --- 创建 Cloudflare API Token

1.  登录 Cloudflare → **My Profile** → **API Tokens** → **Create
    Token**。
2.  授权配置建议：
    -   **Zone: Read**
    -   **DNS: Read**
    -   **Zone Resources**：选择 **All Zones**
3.  复制并保存生成的 Token。

### 步骤 3 --- 本地运行（可选）

``` bash
export CF_API_TOKEN="YOUR_TOKEN"
export CF_EMAIL="YOUR_EMAIL"

python src/generator.py
```

成功执行后，根目录会生成 `index.html`。

## 🔄 自动化部署（推荐）

### GitHub Actions Secrets

`Settings → Secrets and variables → Actions`

添加：

-   `CF_API_TOKEN`
-   `CF_EMAIL`

工作流会根据 `deploy.yml` 自动生成导航站。

## ☁️ 部署到 Cloudflare Pages

构建设置：

-   **Build command：**

    ``` bash
    pip install -r requirements.txt && python src/generator.py
    ```

-   **Build output directory：** `.`

-   设置环境变量：`CF_API_TOKEN`、`CF_EMAIL`

## 💡 自定义

### DNS 过滤规则（src/generator.py）

``` python
ALLOWED_TYPES = {"A", "CNAME", "AAAA"}
EXCLUDE_PREFIXES = ["_acme-challenge", "mail", "ftp", "localhost"]
```

### 页面样式（template.html）

可自由修改 HTML 与 CSS。

## 📄 许可证

本项目采用 **MIT License**。
