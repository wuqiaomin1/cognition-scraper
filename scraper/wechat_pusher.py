"""企业微信机器人推送模块 + 微信聊天风格消息格式化"""
import requests
from datetime import datetime


class WeChatPusher:
    """企业微信机器人推送器"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send_text(self, content: str, mentioned_list: list[str] = None) -> bool:
        """发送纯文本消息"""
        payload = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list or []
            }
        }
        return self._send(payload)
    
    def send_markdown(self, content: str) -> bool:
        """发送Markdown格式消息"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        return self._send(payload)
    
    def send_news(self, articles: list[dict]) -> bool:
        """发送图文消息（最多8条）"""
        payload = {
            "msgtype": "news",
            "news": {
                "articles": articles[:8]
            }
        }
        return self._send(payload)
    
    def _send(self, payload: dict) -> bool:
        """发送请求"""
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            result = resp.json()
            if result.get("errcode") == 0:
                return True
            print(f"[微信推送] 失败: {result}")
            return False
        except Exception as e:
            print(f"[微信推送] 异常: {e}")
            return False
    
    def push_daily_report(self, report_data: dict, categories_order: list[str] = None) -> dict:
        """
        推送分类日报到企业微信
        返回 {"ok": bool, "sent": int, "failed": int}
        """
        if categories_order is None:
            categories_order = ["🏛️ 政策/宏观", "🤖 AI/技术", "💼 商业/创业", "💰 投资/财报", "🛒 消费/市场", "🌍 其他"]
        
        cats = report_data.get("categories", {})
        stats = report_data.get("stats", {})
        date_str = report_data.get("date", datetime.now().strftime("%Y-%m-%d"))
        total = stats.get("total", 0)
        
        sent = 0
        failed = 0
        
        # 1. 发送头条消息
        header = self._format_header(date_str, total, stats)
        if self.send_markdown(header):
            sent += 1
        else:
            failed += 1
        
        # 2. 按分类发送（每个分类一条消息）
        for cat_name in categories_order:
            items = cats.get(cat_name, [])
            if not items:
                continue
            
            msg = self._format_category(cat_name, items)
            if self.send_markdown(msg):
                sent += 1
            else:
                failed += 1
            
            # 企业微信有频率限制，间隔一下
            import time
            time.sleep(0.5)
        
        # 3. 发送行动建议
        footer = self._format_footer()
        if self.send_markdown(footer):
            sent += 1
        else:
            failed += 1
        
        return {"ok": failed == 0, "sent": sent, "failed": failed}
    
    def _format_header(self, date_str: str, total: int, stats: dict) -> str:
        """格式化头条消息"""
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.strptime(date_str, "%Y-%m-%d").weekday()]
        cat_stats = stats.get("categories", {})
        
        lines = [
            f"## 🧠 认知作弊 · 每日情报",
            f"> {date_str} {weekday} | 共 <font color=\"info\">{total}条</font>",
            f"",
        ]
        
        # 分类概要
        for cat, count in cat_stats.items():
            if count > 0:
                lines.append(f"> {cat}: <font color=\"comment\">{count}条</font>")
        
        lines.append("")
        lines.append("---")
        lines.append("")
        
        return "\n".join(lines)
    
    def _format_category(self, cat_name: str, items: list) -> str:
        """格式化一个分类的消息"""
        lines = [
            f"## {cat_name}",
            f"",
        ]
        
        # 取前5条
        for idx, item in enumerate(items[:5], 1):
            title = item.get("title", "")[:60]
            summary = item.get("ai_summary", "")[:100]
            url = item.get("url", "")
            priority = "🔴" if item.get("priority") == "high" else ""
            
            lines.append(f"**{idx}. {priority}{title}**")
            if summary:
                lines.append(f"> {summary}")
            if url:
                lines.append(f"[📎 查看原文]({url})")
            lines.append("")
        
        # 如果超过5条，提示
        if len(items) > 5:
            lines.append(f"> 还有 {len(items) - 5} 条，打开Web页面查看完整内容")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_footer(self) -> str:
        """格式化底部消息"""
        now = datetime.now().strftime("%H:%M")
        return f"## 💡 今日行动建议\n\n- 标记 **3-5 篇** 值得深度阅读\n- 用 AI 工具**整理成思维导图**\n- 结合自身领域，输出 **1 条今日思考**\n\n> 🕐 {now} · 由认知作弊情报系统自动推送"
    
    def push_instant(self, title: str, summary: str, url: str, source: str) -> bool:
        """推送单条即时消息"""
        msg = f"## 📡 即时推送\n\n**{title[:80]}**\n\n> {summary[:150]}\n\n📎 [{source}]({url})"
        return self.send_markdown(msg)


def format_wechat_chat_message(report_data: dict, categories_order: list[str] = None) -> list[dict]:
    """
    生成微信聊天风格的消息列表（用于Web页面展示）
    返回 [{"role": "assistant", "content": "...", "type": "text"|"card"}, ...]
    """
    if categories_order is None:
        categories_order = ["🏛️ 政策/宏观", "🤖 AI/技术", "💼 商业/创业", "💰 投资/财报", "🛒 消费/市场", "🌍 其他"]
    
    cats = report_data.get("categories", {})
    stats = report_data.get("stats", {})
    date_str = report_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    total = stats.get("total", 0)
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    
    messages = []
    
    # 1. 问候消息
    messages.append({
        "role": "assistant",
        "type": "text",
        "content": f"早上好！今天是 {date_str} {weekday} ☀️\n\n今天的认知情报已整理完毕，共抓取 **{total}** 条信息。来看看今天有什么值得关注的 👇"
    })
    
    # 2. 今日3条最重要的
    all_items = []
    for cat in categories_order:
        all_items.extend(cats.get(cat, []))
    
    top_items = sorted(
        [i for i in all_items if i.get("priority") == "high" or (i.get("tags") and len(i.get("tags", [])) >= 3)],
        key=lambda x: len(x.get("tags", [])),
        reverse=True
    )[:3]
    
    if top_items:
        content = "💡 **今天最值得关注的3条：**\n"
        for idx, item in enumerate(top_items, 1):
            content += f"\n{idx}. **{item['title'][:60]}**\n   > {item.get('ai_summary', '')[:100]}\n"
        messages.append({"role": "assistant", "type": "text", "content": content})
    
    # 3. 按分类发送卡片
    for cat_name in categories_order:
        items = cats.get(cat_name, [])
        if not items:
            continue
        
        messages.append({
            "role": "assistant",
            "type": "category_header",
            "content": f"{cat_name}（{len(items)}条）"
        })
        
        for item in items[:5]:
            messages.append({
                "role": "assistant",
                "type": "card",
                "title": item.get("title", ""),
                "summary": item.get("ai_summary", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "category": cat_name,
                "tags": item.get("tags", []),
                "priority": item.get("priority", "")
            })
        
        if len(items) > 5:
            messages.append({
                "role": "assistant",
                "type": "text",
                "content": f"📎 还有 {len(items) - 5} 条{cat_name}相关内容，打开Web页面查看完整日报"
            })
    
    # 4. 行动建议
    messages.append({
        "role": "assistant",
        "type": "text",
        "content": "📋 **今日行动建议：**\n\n✅ 标记 3-5 篇值得深度阅读\n✅ 用 AI 工具整理成思维导图\n✅ 结合自身领域，输出 1 条今日思考\n\n— 认知作弊情报系统 🤖"
    })
    
    return messages
