"""AI摘要与分类引擎 —— 离线关键词+规则引擎"""
import re
import json
from pathlib import Path

# ========== 分类体系 ==========
CATEGORIES = {
    "🤖 AI/技术": {
        "keywords": [
            "AI", "人工智能", "大模型", "GPT", "ChatGPT", "Claude", "DeepSeek", "豆包",
            "自动驾驶", "芯片", "半导体", "算法", "机器人", "神经网络", "机器学习",
            "深度学习", "NLP", "计算机视觉", "量子计算", "云计算", "SaaS",
            "开源", "API", "技术突破", "智能", "数据", "编程", "代码"
        ],
        "desc": "AI与前沿技术动态"
    },
    "💼 商业/创业": {
        "keywords": [
            "融资", "IPO", "上市", "创业", "创始人", "CEO", "裁员", "增长",
            "商业模式", "营收", "盈利", "亏损", "估值", "收购", "并购",
            "独角兽", "startup", "融资轮", "天使轮", "A轮", "B轮",
            "组织架构", "人事变动", "高管", "合伙人", "转型", "战略"
        ],
        "desc": "商业动态与创业风向"
    },
    "🏛️ 政策/宏观": {
        "keywords": [
            "国务院", "政策", "促进", "支持", "意见", "通知", "监管", "法规",
            "发改委", "工信部", "商务部", "央行", "银保监", "证监会",
            "宏观", "经济", "GDP", "PMI", "财政", "货币", "利率",
            "改革", "开放", "规划", "十四五", "战略", "国家安全"
        ],
        "desc": "政策风向与宏观经济"
    },
    "🛒 消费/市场": {
        "keywords": [
            "消费", "电商", "品牌", "营销", "广告", "零售", "线下",
            "用户增长", "DAU", "MAU", "流量", "直播", "短视频",
            "小红书", "抖音", "快手", "拼多多", "美团", "京东",
            "下沉市场", "出海", "跨境电商", "新消费", "Z世代"
        ],
        "desc": "消费趋势与市场洞察"
    },
    "💰 投资/财报": {
        "keywords": [
            "财报", "季度", "年报", "利润", "股价", "市值", "股东",
            "分红", "管理层分析", "巨潮", "上市公司", "港股", "A股",
            "美股", "基金", "ETF", "投资", "资产", "收益率",
            "ROE", "PE", "PB", "现金流", "负债", "资产负债表"
        ],
        "desc": "财报解读与投资参考"
    },
    "🌍 其他": {
        "keywords": [],
        "desc": "其他值得关注的信息"
    }
}


def classify(title: str, summary: str = "", source: str = "") -> str:
    """自动分类：根据标题+摘要匹配关键词"""
    text = f"{title} {summary}".lower()
    scores = {}
    
    for cat_name, cat_info in CATEGORIES.items():
        if cat_name == "🌍 其他":
            continue
        score = sum(1 for kw in cat_info["keywords"] if kw.lower() in text)
        if score > 0:
            scores[cat_name] = score
    
    if not scores:
        return "🌍 其他"
    
    return max(scores, key=scores.get)


def summarize(title: str, summary: str = "", source: str = "") -> str:
    """用大白话生成一句话摘要"""
    # 清理HTML标签
    clean_summary = re.sub(r'<[^>]+>', ' ', summary)
    clean_summary = re.sub(r'\s+', ' ', clean_summary).strip()
    
    # 策略1：如果summary足够长且有实质内容，提取核心
    if len(clean_summary) > 30:
        # 取前120字作为摘要
        short = clean_summary[:120].strip()
        if len(short) < len(clean_summary):
            short += "…"
        return short
    
    # 策略2：基于标题生成摘要
    title_clean = title.strip()
    
    # 提取关键信息
    patterns = [
        (r'(\d+)亿', r'涉及\1亿规模'),
        (r'突破', r'取得突破'),
        (r'发布', r'正式发布'),
        (r'上市', r'即将/已经上市'),
        (r'融资', r'获得融资'),
        (r'增长(\d+)%', r'增长\1%'),
        (r'下降(\d+)%', r'下降\1%'),
    ]
    
    for pattern, template in patterns:
        if re.search(pattern, title_clean):
            return f"这条消息说的是：{title_clean[:100]}"
    
    return f"值得关注：{title_clean[:120]}"


def get_keywords(title: str, summary: str = "") -> list[str]:
    """提取标签关键词"""
    text = f"{title} {summary}"
    tags = set()
    
    # 从所有分类关键词中匹配
    for cat_info in CATEGORIES.values():
        for kw in cat_info["keywords"]:
            if len(kw) >= 2 and kw.lower() in text.lower():
                tags.add(kw)
    
    return list(tags)[:5]


def analyze_items(items: list[dict], source: str = "") -> list[dict]:
    """批量分析：分类+摘要+标签"""
    analyzed = []
    for item in items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        
        category = classify(title, summary, source)
        ai_summary = summarize(title, summary, source)
        tags = get_keywords(title, summary)
        
        analyzed.append({
            **item,
            "category": category,
            "ai_summary": ai_summary,
            "tags": tags,
            "priority": item.get("priority", "normal")
        })
    
    return analyzed


def group_by_category(analyzed_items: list[dict]) -> dict[str, list[dict]]:
    """按分类分组"""
    groups = {}
    for cat_name in CATEGORIES:
        groups[cat_name] = []
    
    for item in analyzed_items:
        cat = item.get("category", "🌍 其他")
        if cat not in groups:
            cat = "🌍 其他"
        groups[cat].append(item)
    
    # 去掉空分类
    return {k: v for k, v in groups.items() if v}
