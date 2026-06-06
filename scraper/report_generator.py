"""日报生成器 v2 —— 分类日报 + 大白话摘要"""
from datetime import datetime
from pathlib import Path
from .ai_summarizer import analyze_items, group_by_category, CATEGORIES


class ReportGeneratorV2:
    """分类日报生成器"""
    
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, all_results: dict[str, list[dict]], kb_stats: dict = None) -> dict:
        """
        生成分类日报
        返回 {"markdown": str, "date": str, "stats": dict, "categories": dict}
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        
        # 1. 分析所有条目
        all_analyzed = []
        for source, items in all_results.items():
            analyzed = analyze_items(items, source)
            all_analyzed.extend(analyzed)
        
        # 2. 按分类分组
        grouped = group_by_category(all_analyzed)
        
        # 3. 统计
        total = len(all_analyzed)
        stats = {
            "total": total,
            "categories": {cat: len(items) for cat, items in grouped.items()},
            "sources": {}
        }
        for item in all_analyzed:
            src = item.get("source", "未知")
            stats["sources"][src] = stats["sources"].get(src, 0) + 1
        
        # 4. 生成日报
        lines = []
        lines.append(f"# 🧠 认知作弊 · 每日情报")
        lines.append(f"")
        lines.append(f"> 📅 **{date_str} {weekday}** | 共抓取 **{total}** 条信息")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
        
        # 今日一句话总结
        top_items = [i for i in all_analyzed if i.get("priority") == "high" or len(i.get("tags", [])) >= 3]
        if top_items:
            top3 = sorted(top_items, key=lambda x: len(x.get("tags", [])), reverse=True)[:3]
            lines.append(f"## 💡 今天这3条最重要")
            lines.append(f"")
            for idx, item in enumerate(top3, 1):
                lines.append(f"{idx}. **{item['title'][:80]}**")
                lines.append(f"   > {item['ai_summary'][:150]}")
                lines.append(f"")
            lines.append(f"---")
            lines.append(f"")
        
        # 按分类展示
        cat_order = ["🏛️ 政策/宏观", "🤖 AI/技术", "💼 商业/创业", "💰 投资/财报", "🛒 消费/市场", "🌍 其他"]
        ordered_cats = [c for c in cat_order if c in grouped] + [c for c in grouped if c not in cat_order]
        
        for cat_name in ordered_cats:
            items = grouped[cat_name]
            cat_info = CATEGORIES.get(cat_name, {"desc": ""})
            
            lines.append(f"## {cat_name}（{len(items)}条）")
            lines.append(f"> {cat_info.get('desc', '')}")
            lines.append(f"")
            
            for idx, item in enumerate(items, 1):
                title = item.get("title", "")
                url = item.get("url", "")
                source = item.get("source", "")
                ai_summary = item.get("ai_summary", "")
                tags = item.get("tags", [])
                priority = item.get("priority", "")
                
                # 大白话标题 + 一句话总结
                priority_mark = "🔴" if priority == "high" else ""
                
                lines.append(f"**{idx}. {priority_mark}{title[:100]}**")
                lines.append(f"")
                lines.append(f"💬 {ai_summary[:200]}")
                lines.append(f"")
                if tags:
                    lines.append(f"🏷️ {' · '.join(tags[:5])}")
                lines.append(f"📎 [{source}]({url})")
                lines.append(f"")
        
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## 📊 今日数据")
        lines.append(f"")
        lines.append(f"| 分类 | 数量 |")
        lines.append(f"|------|------|")
        for cat_name in ordered_cats:
            if cat_name in grouped:
                lines.append(f"| {cat_name} | {len(grouped[cat_name])} |")
        lines.append(f"")
        
        if kb_stats:
            lines.append(f"| 📚 知识库总量 | {kb_stats.get('total', 0)} |")
            lines.append(f"| ⭐ 已收藏 | {kb_stats.get('favorites', 0)} |")
            lines.append(f"| 📝 有笔记 | {kb_stats.get('with_notes', 0)} |")
            lines.append(f"")
        
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"*本日报由「认知作弊信息抓取系统」自动生成 · {date_str}*")
        
        content = "\n".join(lines)
        
        # 5. 保存文件
        filename = self.output_dir / f"日报_{date_str}.md"
        filename.write_text(content, encoding='utf-8')
        
        latest = self.output_dir / "latest.md"
        latest.write_text(content, encoding='utf-8')
        
        # 保存分类数据JSON（供前端用）
        data_json = {
            "date": date_str,
            "stats": stats,
            "categories": {
                cat: [
                    {
                        "title": i["title"],
                        "url": i.get("url", ""),
                        "source": i.get("source", ""),
                        "ai_summary": i.get("ai_summary", ""),
                        "tags": i.get("tags", []),
                        "priority": i.get("priority", "normal")
                    }
                    for i in items
                ]
                for cat, items in grouped.items()
            }
        }
        data_file = self.output_dir / f"data_{date_str}.json"
        data_file.write_text(
            __import__('json').dumps(data_json, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        
        return {
            "markdown": content,
            "date": date_str,
            "stats": stats,
            "categories": grouped,
            "all_analyzed": all_analyzed
        }
    
    def generate_category_report(self, all_results: dict[str, list[dict]], category: str) -> str:
        """生成单个分类的专题日报"""
        all_analyzed = []
        for source, items in all_results.items():
            analyzed = analyze_items(items, source)
            all_analyzed.extend(analyzed)
        
        grouped = group_by_category(all_analyzed)
        cat_items = grouped.get(category, [])
        
        if not cat_items:
            return f"# {category}\n\n今日暂无此分类的信息。"
        
        now = datetime.now()
        lines = []
        lines.append(f"# {category} 专题 · {now.strftime('%Y-%m-%d')}")
        lines.append(f"")
        lines.append(f"> 共 {len(cat_items)} 条")
        lines.append(f"")
        
        for idx, item in enumerate(cat_items, 1):
            lines.append(f"## {idx}. {item['title'][:100]}")
            lines.append(f"")
            lines.append(f"💬 {item['ai_summary'][:200]}")
            lines.append(f"")
            if item.get("tags"):
                lines.append(f"🏷️ {' · '.join(item['tags'][:5])}")
            lines.append(f"📎 [{item.get('source', '')}]({item.get('url', '')})")
            lines.append(f"")
        
        return "\n".join(lines)
    
    def get_history(self, limit: int = 30) -> list[dict]:
        """获取历史日报列表"""
        files = sorted(self.output_dir.glob("日报_*.md"), reverse=True)
        history = []
        for f in files[:limit]:
            date_part = f.stem.replace("日报_", "")
            data_file = self.output_dir / f"data_{date_part}.json"
            stats = {}
            if data_file.exists():
                try:
                    stats = __import__('json').loads(data_file.read_text(encoding='utf-8')).get("stats", {})
                except:
                    pass
            history.append({
                "date": date_part,
                "filename": f.name,
                "size": f.stat().st_size,
                "stats": stats
            })
        return history
    
    def read_report(self, date_str: str) -> str | None:
        """读取指定日期的日报"""
        filename = self.output_dir / f"日报_{date_str}.md"
        if filename.exists():
            return filename.read_text(encoding='utf-8')
        return None
    
    def read_data(self, date_str: str) -> dict | None:
        """读取指定日期的分类数据JSON"""
        data_file = self.output_dir / f"data_{date_str}.json"
        if data_file.exists():
            return __import__('json').loads(data_file.read_text(encoding='utf-8'))
        return None
