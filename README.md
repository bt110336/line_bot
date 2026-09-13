# LINE 券商報告摘要機器人

在 LINE 傳 PDF 券商報告給機器人，自動用 Claude 產生摘要並回傳。

## 運作方式

1. 你傳 PDF 檔到 LINE 機器人
2. 機器人立刻回「分析中」
3. 背景抽取 PDF 文字 → 呼叫 Claude API 摘要 → 用 push message 傳回摘要

限制：目前只吃「文字型」PDF（用 pdfplumber 抽字），如果是掃描圖檔型的 PDF（整頁是圖片），抽不到文字，會提示你沒有 OCR 支援。

---

## 步驟一：建立 LINE Messaging API 頻道

1. 到 [LINE Developers Console](https://developers.line.biz/console/) 登入
2. 建立 Provider → 建立 Channel，選 **Messaging API**
3. 在 Channel 的「Messaging API」分頁：
   - 取得 **Channel access token**（長期）→ 之後填入 `LINE_CHANNEL_ACCESS_TOKEN`
   - 到「Basic settings」分頁取得 **Channel secret** → 填入 `LINE_CHANNEL_SECRET`
   - 把「Auto-reply messages」「Greeting messages」關掉（避免干擾）
   - Webhook 記得開啟「Use webhook」

## 步驟二：取得 Anthropic API Key

到 [console.anthropic.com](https://console.anthropic.com/) 建立 API Key，填入 `ANTHROPIC_API_KEY`。

## 步驟三：本機測試（可跳過，直接部署也行）

```bash
pip install -r requirements.txt

export LINE_CHANNEL_SECRET=xxx
export LINE_CHANNEL_ACCESS_TOKEN=xxx
export ANTHROPIC_API_KEY=xxx

uvicorn main:app --reload --port 8000
```

本機測試需要用 `ngrok http 8000` 之類的工具打洞，把公開網址填到 LINE 的 Webhook URL（記得後面要加 `/callback`）。

## 步驟四：部署（推薦 Render 或 Zeabur）

### 用 Render.com

1. 把這個資料夾 push 到一個 GitHub repo
2. Render → New → Web Service → 連接該 repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. 在 Environment 頁籤加入三個環境變數：`LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`ANTHROPIC_API_KEY`
6. 部署完成後會拿到一個網址，例如 `https://your-app.onrender.com`

### 用 Zeabur（台灣團隊做的，介面中文、串信用卡方便）

1. 一樣先 push 到 GitHub
2. Zeabur → 新專案 → 從 GitHub 匯入這個 repo，會自動偵測是 Python 專案
3. 在服務設定裡加上同樣三個環境變數
4. 部署完成後一樣會拿到一個公開網址

## 步驟五：設定 LINE Webhook URL

回到 LINE Developers Console → Messaging API 分頁 → Webhook URL 填入：

```
https://你的網址/callback
```

按「Verify」測試連線成功即可。之後用手機 LINE 掃描該 Channel 的 QR code 加好友，傳 PDF 過去測試。

---

## 之後可以擴充的方向

- 支援圖片型 PDF：加入 OCR（例如串 Google Vision 或 Claude 的圖片輸入能力，把每頁轉成圖片直接丟給 Claude）
- 支援多檔案批次摘要、或用 LINE Flex Message 做更好看的排版
- 把摘要記錄存到資料庫，之後可以查歷史報告
- 長報告用「分段摘要 + 彙整」的 map-reduce 方式處理，避免只看前面部分
