# 部署到服务器

**完整操作指南见 [`服务器接入指南.md`](服务器接入指南.md)。**这份只是命令速查。

```
域名   art.ddhulu.cn        （A 记录还没加，这是第一件要做的事）
服务器 124.220.179.33       腾讯云 · 上海
备案   ✅ 已过              http://ddhulu.cn 返回 200
入口   Caddy                自动签 HTTPS，不需要 certbot
SSH    端口未知             22 是拒绝连接，被改过了，得问对方
```

路线：应用只监听 `127.0.0.1:8010`，对外由**服务器上已有的 Caddy** 反代。
不抢端口、不动安全组，要撤掉删一段配置 reload 一下就行。

⚠️ **上线前必读**：应用目前没有鉴权层，`GET /api/sessions` 会返回全部孩子的
作品列表。`Caddyfile.artquest` 已把三个研究员接口挡在口令后面，但那是止血不是
根治。细节见指南第零部分末尾和第三部分。

## 一次性准备

1. 生成密钥对（已完成），公钥发给服务器主人装进 `authorized_keys`：

   ```bash
   cat ~/.ssh/aliyun_ed25519.pub
   ```

   那个 `~/.ssh/aliyun.ppk` 不用了 —— 私钥不该在人之间传递，见指南第二部分说明 1。

2. 写进 `~/.ssh/config`：

   ```
   Host aliyun
     HostName <公网IP>
     Port <SSH端口>
     User ray
     IdentityFile ~/.ssh/aliyun_ed25519
     ServerAliveInterval 30
   ```

3. 试连：`ssh aliyun`

## 部署 / 更新

```bash
./deploy/push.sh                  # 用 ssh config 里的 Host aliyun
./deploy/push.sh root@1.2.3.4     # 或直接给地址
```

第一次会自动装依赖、建 `artquest` 服务账号、装 systemd 服务。
之后每次改完代码重跑同一条命令即可。

## 访问

**公开访问**（正式路线）：`https://art.ddhulu.cn/` —— 需要对方加 A 记录并接上 Caddy，见指南第二部分的两封信。

**自己调试**（nginx 还没接上时）：

```bash
ssh -N -L 8010:127.0.0.1:8010 aliyun     # 占着终端，Ctrl-C 结束
```

浏览器开 http://127.0.0.1:8010/

## 运维

```bash
ssh aliyun journalctl -u artquest -f      # 看日志
ssh aliyun systemctl restart artquest     # 重启
ssh aliyun systemctl status artquest      # 状态
```

## 数据

孩子的画存在服务器的 `/opt/artquest/data/`，`push.sh` **不会**碰它。
拉回本机备份：

```bash
rsync -az aliyun:/opt/artquest/data/ ./backup-$(date +%F)/
```

## API key（可选）

不配也能跑（离线启发式评分 + 模板反馈）。要用 Claude 评分就在服务器上建 `.env`：

```bash
ssh aliyun 'cat > /opt/artquest/.env' <<'ENV'
ANTHROPIC_API_KEY=sk-ant-...
ARTQUEST_MODEL=claude-opus-5
ARTQUEST_ADMIN_TOKEN=<python3 -c "import secrets;print(secrets.token_urlsafe(24))" 生成一串>
ENV
ssh aliyun 'chmod 600 /opt/artquest/.env && chown artquest:artquest /opt/artquest/.env && systemctl restart artquest'
```

`ARTQUEST_ADMIN_TOKEN` **不是可选的**：全量列表、打分、策展这些研究员接口只认它，
不设就全是 401。研究员这么用：`curl -H "Authorization: Bearer $TOKEN" https://art.ddhulu.cn/api/v1/sessions`。

⚠️ systemd 的 `EnvironmentFile` **不认行尾注释**——`KEY=auto  # 说明` 会把整串当成值。
服务器上的 `.env` 每行只能是干净的 `KEY=VALUE`，别直接拷 `.env.example`。

## 以后要给别人用

需要域名 + HTTPS（Service Worker 只在 HTTPS 下注册，离线和"装到主屏"靠它）。
你的机器在香港/海外，**不需要 ICP 备案**，域名指过来直接 certbot 签证书就行。
但在那之前，`docs/ETHICS.md` 里那份同意书得先定下来。
