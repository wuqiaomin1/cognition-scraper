"""AI答疑小助手 —— 基于本地知识库的智能问答
支持两种模式：
1. 本地模式：基于知识库检索 + 规则匹配（无需API Key）
2. API模式：接入外部大模型（需配置API Key）
"""
import os
import re
from .knowledge_base import KnowledgeBase


class AIAssistant:
    """AI答疑小助手"""
    
    def __init__(self, kb: KnowledgeBase = None, api_key: str = None, api_base: str = None):
        self.kb = kb
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.api_base = api_base or os.environ.get("OPENAI_API_BASE", "https://api.deepseek.com/v1")
        self.use_api = bool(self.api_key)

    def set_kb(self, kb):
        """运行时切换知识库"""
        self.kb = kb
    
    def chat(self, question: str, history: list[dict] = None) -> str:
        """智能问答"""
        if self.use_api:
            return self._api_chat(question, history or [])
        return self._local_chat(question)
    
    def _local_chat(self, question: str) -> str:
        """本地智能问答：基于知识库 + 规则"""
        q_lower = question.lower()
        
        # 1. 先检查是否是概念解释型问题
        has_concept = any(w in q_lower for w in ['什么是', '什么意思', '解释一下', 'ai是什么', 'gpt', '大模型', '融资是什么意思', 'ipo是什么', '财报怎么看'])
        has_explain = any(w in q_lower for w in ['解释', '说明', '讲一下', '分析', '解读', '怎么看'])
        
        if has_concept:
            result = self._concept_mode(question)
            if result and '知识库中还有' not in result[:50]:
                # 纯概念解释，不用再查知识库
                return result
        
        # 2. 如果是解释型问题，结合知识库
        if has_explain or has_concept:
            return self._explain_mode(question)
        
        # 3. 搜索型问题
        if any(w in q_lower for w in ['有哪些', '有什么', '最近', '最新', '关于', '找一下', '搜一下']):
            return self._search_mode(question)
        
        # 4. 通用回答
        return self._general_mode(question)
    
    def _explain_mode(self, question: str) -> str:
        """解释模式：从知识库找相关内容并解释"""
        # 提取关键词
        keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', question)
        relevant = []
        
        for kw in keywords[:5]:
            results = self.kb.search(kw)
            relevant.extend(results)
        
        # 去重
        seen = set()
        unique = []
        for r in relevant:
            if r['id'] not in seen:
                seen.add(r['id'])
                unique.append(r)
        
        if not unique:
            return self._general_mode(question)
        
        # 构建回答
        top = unique[:3]
        lines = ["根据知识库中的相关信息，我来帮你解读：\n"]
        
        for item in top:
            title = item.get('title', '')
            summary = item.get('ai_summary', '')
            source = item.get('source', '')
            
            lines.append(f"**{title[:80]}**")
            if summary:
                lines.append(f"> {summary[:200]}")
            lines.append(f"📎 来源：{source}")
            lines.append("")
        
        lines.append("💡 如果需要更深入的分析，可以告诉我你具体想了解哪个方面。")
        return "\n".join(lines)
    
    def _search_mode(self, question: str) -> str:
        """搜索模式"""
        keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', question)
        all_results = []
        
        for kw in keywords[:3]:
            results = self.kb.search(kw)
            all_results.extend(results)
        
        seen = set()
        unique = []
        for r in all_results:
            if r['id'] not in seen:
                seen.add(r['id'])
                unique.append(r)
        
        if not unique:
            return "我在知识库中没有找到直接相关的内容。建议你：\n• 换一个关键词搜索\n• 执行一次新的抓取获取最新信息\n• 在知识库页面用搜索框查找"
        
        lines = [f"找到 {len(unique)} 条相关内容：\n"]
        for item in unique[:5]:
            title = item.get('title', '')[:80]
            cat = item.get('category', '')
            source = item.get('source', '')
            url = item.get('url', '')
            lines.append(f"• [{cat}] **{title}**" + (f" [原文]({url})" if url else ""))
        
        if len(unique) > 5:
            lines.append(f"\n...还有 {len(unique) - 5} 条，可以在知识库中查看。")
        
        return "\n".join(lines)
    
    def _concept_mode(self, question: str) -> str:
        """概念解释模式"""
        concepts = {
            'ai': 'AI（人工智能）是让机器模拟人类智能的技术。当前最热的方向包括大语言模型（如ChatGPT、DeepSeek）、AI Agent、具身智能等。',
            '大模型': '大模型（Large Language Model）是通过海量数据训练的大型神经网络，能够理解和生成自然语言。代表产品有GPT-4、Claude、DeepSeek、豆包等。',
            '融资': '融资是企业获取外部资金的过程。常见的融资轮次包括：天使轮→A轮→B轮→C轮→IPO上市。融资能力反映了资本市场对企业的信心。',
            'ipo': 'IPO（首次公开募股）是指企业首次向公众发行股票。上市后企业可以在证券交易所公开交易，是创业公司的重要里程碑。',
            '政策': '政策是政府为实现特定目标制定的规则和措施。关注政策动向可以帮助你提前预判行业趋势，政策红利期通常有3年窗口。',
            '财报': '财报（财务报告）是上市公司定期发布的经营状况报告。重点关注：营收、利润、现金流、管理层分析。巨潮资讯网是查看A股财报的官方渠道。',
            '芯片': '芯片（集成电路）是现代电子设备的核心。当前AI芯片需求暴涨，英伟达是全球龙头。中国在芯片领域正加速自主替代。',
            '自动驾驶': '自动驾驶是AI在交通领域的应用，分为L1-L5五个等级。当前主流车企处于L2-L3阶段，完全无人驾驶（L5）仍在研发中。',
            '机器人': '机器人技术正从工业机器人向人形机器人、具身智能方向发展。AI大模型的进步正在加速机器人智能化。',
        }
        
        for key, explanation in concepts.items():
            if key in question.lower():
                results = self.kb.search(key)
                recent = f"\n\n📚 知识库中还有 {len(results)} 条相关内容，可以进一步查阅。" if results else ""
                return explanation + recent
        
        return self._general_mode(question)
    
    def _general_mode(self, question: str) -> str:
        """通用回答模式"""
        # 尝试从知识库找相关内容
        keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', question)
        all_results = []
        for kw in keywords[:3]:
            all_results.extend(self.kb.search(kw))
        
        if all_results:
            seen = set()
            unique = []
            for r in all_results:
                if r['id'] not in seen:
                    seen.add(r['id'])
                    unique.append(r)
            
            lines = ["这个问题很好！我在知识库中找到了以下相关内容：\n"]
            for item in unique[:3]:
                title = item.get('title', '')[:80]
                summary = item.get('ai_summary', '')[:150]
                url = item.get('url', '')
                lines.append(f"**{title}**")
                if summary:
                    lines.append(f"> {summary}")
                if url:
                    lines.append(f"📎 [查看原文]({url})")
                lines.append("")
            return "\n".join(lines)
        
        return "我目前的知识库中还没有足够的信息来回答这个问题。建议你：\n• 先执行一次信息抓取，丰富知识库\n• 在知识库页面用搜索框查找关键词\n• 直接把你想了解的原文内容粘贴给我，我来帮你解读"
    
    def _api_chat(self, question: str, history: list[dict]) -> str:
        """通过API调用大模型（DeepSeek/OpenAI兼容）"""
        import requests
        
        # 先从知识库检索相关上下文
        keywords = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]{2,}', question)
        kb_context = ""
        for kw in keywords[:3]:
            results = self.kb.search(kw)
            for r in results[:3]:
                kb_context += f"\n[{r.get('source', '')}] {r.get('title', '')}: {r.get('ai_summary', '')}"
        
        system_prompt = f"""你是一个专业的信息解读助手，帮助用户理解新闻、政策、商业信息。
你基于以下知识库内容来回答问题，用通俗易懂的中文解释。

当前知识库相关内容：
{kb_context[:2000] if kb_context else "暂无相关知识库内容"}

请用简洁、直白的中文回答。如果有不确定的地方，诚实说明。"""
        
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": question})
        
        try:
            resp = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "max_tokens": 1000,
                    "temperature": 0.7
                },
                timeout=30
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"API调用失败: {e}")
            return self._local_chat(question)
