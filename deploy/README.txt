部署文件说明

xiayuan.service：网站与机器人后端服务
xiayuan.conf：Nginx 域名反向代理配置

API Key 仅应保存在服务器的 /etc/xiayuan.env 中，格式如下：
SILICONFLOW_API_KEY=你的密钥
SILICONFLOW_MODEL=Qwen/Qwen3-8B

请勿把真实 API Key 写入本部署包或网页文件。

资料存放区
----------
版本 3.0 已新增“资料存放区”，入口在左侧第 16 项。访客可以搜索和下载，只有管理员登录后才能上传和删除。

本地预览
1. 直接使用 Python 启动服务时，资料默认写入 data/materials，索引写入 data/materials.sqlite3。
2. 访问资料存放区，点击“管理员登录”。管理员账号通过环境变量 MATERIAL_ADMIN_USERNAME 和 MATERIAL_ADMIN_PASSWORD（或 MATERIAL_ADMIN_PASSWORD_HASH）配置。

管理员密码哈希
1. 在项目目录执行：python3 server.py --make-password-hash
2. 输入密码，将输出的 PBKDF2-SHA256 哈希写入 /etc/xiayuan.env 的 MATERIAL_ADMIN_PASSWORD_HASH。
3. 生产环境不要配置 MATERIAL_ADMIN_PASSWORD 明文变量。

腾讯云 COS
1. 创建 COS 存储桶，建议设置为私有读写；不要把存储桶设置为公有读写。
2. 创建仅能访问该存储桶资料目录的 CAM 子账号，填写 COS_BUCKET、COS_REGION、COS_SECRET_ID、COS_SECRET_KEY。
3. 将 MATERIAL_STORAGE=cos，并在服务器安装 requirements.txt 中的 cos-python-sdk-v5。
4. 在 COS 的跨域访问 CORS 中加入你的网站域名，允许 GET、PUT、HEAD、OPTIONS；不要使用 `*` 作为长期生产来源。
5. COS 模式下浏览器通过后端生成的短期预签名地址直接上传，服务器只保存资料索引，不转存大文件。
6. COS 模式下每个文件默认最大 50 MB，可通过 MATERIAL_MAX_BYTES 调整。

部署示例
1. 将 xiayuan.env.example 复制为服务器上的 /etc/xiayuan.env，并填写真实配置；权限设置为仅 root 可读。
2. 将项目目录部署到 /opt/xiayuan，并确保 /opt/xiayuan/data 可由 xiayuan.service 中的 www-data 用户写入。
3. 安装依赖后重启 xiayuan.service，再通过域名进入资料存放区测试登录、上传、搜索和下载。

安全提醒：资料数据目录不会通过静态文件服务直接公开，文件下载统一经过 /api/materials/download。生产环境必须启用 HTTPS。
