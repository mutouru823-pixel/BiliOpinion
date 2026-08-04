# 如何获取 B 站 Cookie

B 站评论接口需要登录态（`SESSDATA` 等字段）才能稳定抓取，未登录时大量评论会被拦截或返回空。本项目把 Cookie 放在 `.env` 文件里，**不要**写进 `config.yaml`，也不要提交到 Git。

## 步骤

1. 用浏览器（Chrome / Edge / Firefox 均可）登录 <https://www.bilibili.com>。
2. 打开开发者工具（Windows：`F12`；macOS：`Cmd + Option + I`）。
3. 切换到 **Network（网络）** 面板，刷新页面，随便点一个向 `api.bilibili.com` 发的请求。
4. 在请求头（Request Headers）里找到 **Cookie** 这一行，整段复制。
5. 在项目根目录新建 `.env` 文件，写入：

   ```ini
   BILI_COOKIE=你的整段Cookie
   ```

   例如：

   ```ini
   BILI_COOKIE=DedeUserID=123456; SESSDATA=abcd1234%2Cabcdef; bili_jct=xxxx; buvid3=yyyy
   ```

   也可以不写 `.env`，而是直接把 Cookie 填进 `config.yaml` 的 `crawl.cookie` 字段；但**更推荐 `.env` 方式**，避免密钥入库。

## 验证 Cookie 是否有效

最简单的方法：在 Python 里访问一次需登录的接口，例如：

```python
import requests
ck = open(".env").read().split("BILI_COOKIE=")[1].strip()
r = requests.get("https://api.bilibili.com/x/web-interface/nav",
                 headers={"Cookie": ck, "User-Agent": "Mozilla/5.0"})
print(r.json()["data"]["isLogin"])   # True 表示登录有效
```

## 注意事项

- Cookie 含有你的账号凭证，**等同于账号密码**，请勿分享、勿提交到公开仓库。
- `SESSDATA` 过期后抓取会失败或数据不全，重新按上述步骤获取即可。
- 抓取频率已在 `config.yaml` 里做了限速（`request_delay` 等），请勿为提速而把延时调到 0，避免触发风控封禁账号。
- 仅用于学术/个人研究，遵守 B 站机器人协议与数据使用规范。
