"""本地知识库 —— JSON存储 + 全文搜索 + 收藏 + Notion导出"""
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


class KnowledgeBase:
    """本地JSON知识库"""
    
    def __init__(self, db_path: str = "./output/knowledge_base.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
    
    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"items": {}, "collections": {}, "meta": {"created": datetime.now().isoformat()}}
    
    def _save(self):
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def _make_id(self, title: str, url: str) -> str:
        return hashlib.md5(f"{title}{url}".encode()).hexdigest()[:12]
    
    def add(self, item: dict) -> str:
        """添加一条知识，返回ID"""
        item_id = self._make_id(item.get("title", ""), item.get("url", ""))
        
        if item_id not in self.data["items"]:
            self.data["items"][item_id] = {
                "id": item_id,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "category": item.get("category", ""),
                "ai_summary": item.get("ai_summary", ""),
                "tags": item.get("tags", []),
                "priority": item.get("priority", "normal"),
                "added_at": datetime.now().isoformat(),
                "favorite": False,
                "notes": "",
                "read_count": 0,
                "last_viewed": None,
                "related_to": []
            }
            self._save()
        
        return item_id
    
    def batch_add(self, items: list[dict]) -> int:
        """批量添加，返回新增数量"""
        count = 0
        for item in items:
            item_id = self._make_id(item.get("title", ""), item.get("url", ""))
            if item_id not in self.data["items"]:
                count += 1
            self.add(item)
        return count
    
    def favorite(self, item_id: str) -> bool:
        """收藏/取消收藏"""
        if item_id in self.data["items"]:
            self.data["items"][item_id]["favorite"] = not self.data["items"][item_id]["favorite"]
            self._save()
            return True
        return False
    
    def add_note(self, item_id: str, note: str) -> bool:
        """添加笔记"""
        if item_id in self.data["items"]:
            self.data["items"][item_id]["notes"] = note
            self._save()
            return True
        return False
    
    def mark_read(self, item_id: str):
        """标记已读"""
        if item_id in self.data["items"]:
            self.data["items"][item_id]["read_count"] += 1
            self.data["items"][item_id]["last_viewed"] = datetime.now().isoformat()
            self._save()
    
    def get(self, item_id: str) -> Optional[dict]:
        return self.data["items"].get(item_id)
    
    def search(self, query: str, category: str = None, favorite_only: bool = False) -> list[dict]:
        """全文搜索"""
        results = []
        query_lower = query.lower()
        
        for item in self.data["items"].values():
            if favorite_only and not item.get("favorite"):
                continue
            if category and item.get("category") != category:
                continue
            
            if not query:
                results.append(item)
                continue
            
            # 搜索标题、摘要、标签
            searchable = f"{item.get('title', '')} {item.get('ai_summary', '')} {' '.join(item.get('tags', []))}".lower()
            if query_lower in searchable:
                # 相关性评分
                score = 0
                if query_lower in item.get('title', '').lower():
                    score += 10
                if query_lower in item.get('ai_summary', '').lower():
                    score += 5
                for tag in item.get('tags', []):
                    if query_lower in tag.lower():
                        score += 3
                
                results.append({**item, "_score": score})
        
        results.sort(key=lambda x: x.get("_score", 0), reverse=True)
        return results
    
    def get_by_category(self, category: str) -> list[dict]:
        return self.search("", category=category)
    
    def get_favorites(self) -> list[dict]:
        return self.search("", favorite_only=True)
    
    def get_recent(self, limit: int = 50) -> list[dict]:
        items = sorted(
            self.data["items"].values(),
            key=lambda x: x.get("added_at", ""),
            reverse=True
        )
        return items[:limit]
    
    def get_stats(self) -> dict:
        """知识库统计"""
        items = list(self.data["items"].values())
        categories = {}
        sources = {}
        
        for item in items:
            cat = item.get("category", "未分类")
            categories[cat] = categories.get(cat, 0) + 1
            
            src = item.get("source", "未知")
            sources[src] = sources.get(src, 0) + 1
        
        return {
            "total": len(items),
            "favorites": sum(1 for i in items if i.get("favorite")),
            "with_notes": sum(1 for i in items if i.get("notes")),
            "categories": categories,
            "sources": sources,
            "last_updated": max((i.get("added_at", "") for i in items), default="")
        }
    
    def export_notion_format(self, item_ids: list[str] = None) -> str:
        """导出为Notion兼容的Markdown格式"""
        if item_ids:
            items = [self.data["items"][iid] for iid in item_ids if iid in self.data["items"]]
        else:
            items = list(self.data["items"].values())
        
        # 按分类分组
        grouped = {}
        for item in items:
            cat = item.get("category", "🌍 其他")
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(item)
        
        lines = []
        lines.append("# 🧠 认知作弊知识库导出")
        lines.append(f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"> 共 {len(items)} 条知识")
        lines.append("")
        
        for cat_name, cat_items in grouped.items():
            lines.append(f"## {cat_name}")
            lines.append("")
            
            for item in cat_items:
                title = item.get("title", "")
                url = item.get("url", "")
                summary = item.get("ai_summary", "")
                source = item.get("source", "")
                tags = item.get("tags", [])
                notes = item.get("notes", "")
                fav = "⭐ " if item.get("favorite") else ""
                
                lines.append(f"### {fav}{title}")
                lines.append(f"- **来源**: {source}")
                lines.append(f"- **摘要**: {summary}")
                if tags:
                    lines.append(f"- **标签**: {' '.join(['#' + t for t in tags])}")
                if notes:
                    lines.append(f"- **笔记**: {notes}")
                if url:
                    lines.append(f"- **链接**: {url}")
                lines.append("")
        
        return "\n".join(lines)
    
    def export_notion_json(self) -> list[dict]:
        """导出为Notion API兼容的JSON结构"""
        blocks = []
        for item in self.data["items"].values():
            blocks.append({
                "title": item.get("title", ""),
                "category": item.get("category", ""),
                "source": item.get("source", ""),
                "summary": item.get("ai_summary", ""),
                "tags": item.get("tags", []),
                "url": item.get("url", ""),
                "favorite": item.get("favorite", False),
                "notes": item.get("notes", ""),
                "added_at": item.get("added_at", "")
            })
        return blocks
    
    def export_file(self, format: str = "markdown", item_ids: list[str] = None) -> str:
        """导出到文件，返回文件路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == "markdown":
            content = self.export_notion_format(item_ids)
            filename = self.db_path.parent / f"knowledge_export_{timestamp}.md"
            filename.write_text(content, encoding='utf-8')
            return str(filename)
        elif format == "json":
            data = self.export_notion_json()
            filename = self.db_path.parent / f"knowledge_export_{timestamp}.json"
            filename.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            return str(filename)
        
        return ""
