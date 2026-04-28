# copy-board 一键文案复制工具

## 功能说明

- **前端展示页** `/`：手机微信打开，显示标题+文案，一键复制
- **管理后台** `/admin`：密码登录后可新增、编辑、删除文案

## 快速启动

```bash
python server.py
```

启动后访问：
- 前端：`http://localhost:8899/`
- 后台：`http://localhost:8899/admin`

## 修改管理员密码

打开 `server.py`，找到第 16 行：

```python
ADMIN_PASSWORD = "admin123"
```

改成你想要的密码即可。

## 部署到 NAS

1. 将整个 `copy-board` 文件夹上传到 NAS
2. SSH 登录 NAS，进入目录执行：
   ```bash
   python3 server.py &
   ```
3. 或使用 Docker 部署（见下方）

## Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
EXPOSE 8899
CMD ["python", "server.py"]
```

```bash
docker build -t copy-board .
docker run -d -p 8899:8899 -v $(pwd)/data:/app/data --name copy-board copy-board
```

## 文件说明

```
copy-board/
├── server.py          # 后端服务（Python，无需安装依赖）
├── data/
│   └── items.json     # 数据文件（自动生成）
└── README.md
```
