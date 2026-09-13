import os
import io
import logging

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
import pdfplumber
from anthropic import Anthropic

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, FileMessageContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("line-report-bot")

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

# 單一份報告最多送去摘要的字數上限（避免超長報告塞爆 context / 花費過高）
MAX_CHARS = 60000

app = FastAPI()
handler = WebhookHandler(LINE_CHANNEL_SECRET)
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
claude = Anthropic(api_key=ANTHROPIC_API_KEY)

SUMMARY_PROMPT = """你是專業的證券分析助理。以下是一份券商研究報告的內文，請用繁體中文做摘要，包含：

1. 標的（公司/產業）與報告日期、評等、目標價（如果有）
2. 這份報告的核心觀點（3-5 點重點）
3. 支撐論點的關鍵數據或催化劑
4. 主要風險因子
5. 一句話結論

請條列清楚、精簡，不要照抄整段原文。

報告內文：
---
{content}
---
"""


def extract_pdf_text(pdf_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def summarize_with_claude(report_text: str) -> str:
    truncated = report_text[:MAX_CHARS]
    note = ""
    if len(report_text) > MAX_CHARS:
        note = "\n\n（註：報告內容過長，僅分析前面部分）"

    resp = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[
            {"role": "user", "content": SUMMARY_PROMPT.format(content=truncated)}
        ],
    )
    summary_text = "".join(
        block.text for block in resp.content if block.type == "text"
    )
    return summary_text + note


def process_pdf_and_reply(message_id: str, user_id: str, file_name: str):
    """背景任務：下載 PDF、抽字、摘要、用 push message 送回結果"""
    try:
        with ApiClient(line_config) as api_client:
            blob_api = MessagingApiBlob(api_client)
            pdf_bytes = blob_api.get_message_content(message_id)

        report_text = extract_pdf_text(pdf_bytes)

        if not report_text:
            reply_text = (
                f"🔗 這份「{file_name}」是掃描圖檔型 PDF，鏈子咬不進去，"
                "摘要惡魔暫時無法解析（還沒有 OCR 能力）。"
            )
        else:
            reply_text = (
                f"🔗 摘要惡魔已將「{file_name}」嚼碎，以下是消化後的精華：\n\n"
                + summarize_with_claude(report_text)
            )

    except Exception:
        logger.exception("處理 PDF 時發生錯誤")
        reply_text = "🔗 鏈子卡住了，這份報告處理時出了點問題，請稍後再試一次。"

    # LINE 單則文字訊息上限 5000 字，過長要切段
    with ApiClient(line_config) as api_client:
        messaging_api = MessagingApi(api_client)
        chunks = [reply_text[i:i + 4900] for i in range(0, len(reply_text), 4900)] or [reply_text]
        messaging_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=chunk) for chunk in chunks[:5]],
            )
        )


@handler.add(MessageEvent, message=FileMessageContent)
def handle_file_message(event: MessageEvent):
    file_name = event.message.file_name or ""
    user_id = event.source.user_id
    message_id = event.message.id

    with ApiClient(line_config) as api_client:
        messaging_api = MessagingApi(api_client)

        if not file_name.lower().endswith(".pdf"):
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="🔗 摘要惡魔只吃 PDF，其他格式咬不動喔～")],
                )
            )
            return

        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"🔗 拉繩啟動！摘要惡魔已甦醒，正在撕碎「{file_name}」...約 10-30 秒後奉上摘要")],
            )
        )

    # 背景處理，避免 webhook 逾時
    background_tasks_registry.append((message_id, user_id, file_name))


# FastAPI 的 BackgroundTasks 要在 request handler 內取得，
# 用一個簡單的 module-level list 暫存，再由 webhook endpoint 統一 dispatch。
background_tasks_registry = []


@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    background_tasks_registry.clear()

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for message_id, user_id, file_name in background_tasks_registry:
        background_tasks.add_task(process_pdf_and_reply, message_id, user_id, file_name)

    return "OK"


@app.get("/")
async def health_check():
    return {"status": "ok"}
