# 厦园新手村 · 一站式新生导航

面向厦门大学新生的单页导航站：选课、保研、奖助学金、体育、快递、拼票省钱规划等十几个实用栏目，配全站正文搜索、hash 路由、通行码解锁，另有微信小程序版和安卓壳 App。

线上地址：https://xiayuanguide.cloud

## 功能亮点

- **十余个实用栏目**：新生报到、校历、选课、学分绩点、保研系列、竞赛匹配、双学位、转专业、体育场馆/选课、快递点地图、入学考试查询、资料存放区等
- **拼票规划器**：从 12306 实时票价里找出「曲线回家」的最便宜组合（一跳/两跳中转 + 价格日历 + 住宿成本对比），配套全国火车站点地图选点（腾讯地图）
- **全站正文搜索**：构建期预生成索引（`tools/build_search_index.py`），搜正文而不仅标题，结果可跳到具体小节并高亮提示
- **hash 路由**：任何栏目、任何小节都能直接分享链接，浏览器前进后退可用
- **通行码解锁**：指定栏目凭通行码访问，白名单在 `assets/nav-data.js` 单点维护
- **资料存放区**：带管理员后端的云资料库（SQLite 存储，可选对接腾讯云 COS）
- **微信小程序版**：新生问答测验
- **安卓壳 App**：WebView 离线打包版

## 快速开始

```bash
git clone https://github.com/<你的用户名>/xiayuan-village.git
cd xiayuan-village
pip install -r requirements.txt
python3 server.py            # 默认监听 8080，可用 PORT 环境变量改端口
```

后端提供资料存放区、拼票规划 API、通行码校验等能力，配合前端页面一起构成完整站点。

### 配置腾讯地图 Key（拼票地图选点用）

```bash
cp assets/piao-config.example.js assets/piao-config.js
# 编辑 assets/piao-config.js，填入你在 lbs.qq.com 申请的「Web JS API GL」类型 key
```

key 免费申请：https://lbs.qq.com ，申请后建议在控制台配置域名白名单。该文件已被 .gitignore 排除，不会被提交。

## main 分支文件介绍

```
xiayuan-village/
├── .gitignore              # 版本库排除规则（密钥、用户数据、本地文件）
├── LICENSE                 # MIT 开源许可证
├── README.md               # 本文件
├── android-app/            # 安卓壳 App：WebView 加载站点，含离线本地服务，免装浏览器直接用
├── assets/                 # 静态资源：导航清单、拼票站点数据、搜索索引、主题样式、插画素材、推免细则 PDF 等
├── deploy/                 # 部署配置：nginx 反代、systemd 服务、环境变量模板、12306 中转规划子服务
├── mini-program/           # 微信小程序版：新生问答测验（首页 / 结果 / 村庄三页）
├── requirements.txt        # Python 依赖清单（server.py 运行所需）
├── server.py               # 后端服务：资料存放区、拼票规划 API（对接 12306）、通行码校验
├── tools/                  # 构建脚本：页面标题补锚点 id、重建全站搜索索引
└── 使用说明.txt             # 站点日常使用与维护速览
```

## 部署参考

`deploy/` 内附 nginx 配置（静态资源长缓存 + 反代）和 systemd 服务文件，服务器上：

```bash
pip install -r requirements.txt
python3 server.py   # 生产环境建议配 MATERIAL_ADMIN_PASSWORD_HASH 等环境变量，见 server.py 头部注释
```

### 主要环境变量

| 变量 | 说明 |
|---|---|
| `PORT` | 监听端口，默认 8080 |
| `MATERIAL_ADMIN_PASSWORD` / `MATERIAL_ADMIN_PASSWORD_HASH` | 资料区管理员密码（推荐用 PBKDF2 哈希） |
| `COS_SECRET_ID` / `COS_SECRET_KEY` | 腾讯云 COS 凭证（资料大文件直传，可选） |

## 内容更新流程

`tools/` 下的两个构建脚本服务于站点内容维护：

```bash
python3 tools/add_heading_ids.py      # 给新增小节标题补锚点 id
python3 tools/build_search_index.py   # 重建搜索索引
```

## 改成你自己学校的新生站

内容按栏目一页一个 HTML 组织（自行编写页面后放入 `pages/`），导航栏目清单集中在 `assets/nav-data.js` 一处维护（名称、图标、是否需要通行码）。拼票站点数据在 `assets/piao-stations.js`，换城市只需替换对应数据。`tools/` 下的构建脚本会自动给页面补锚点、生成搜索索引。

## 许可证

[MIT](LICENSE)
