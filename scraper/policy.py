"""国务院政策文件库 - 政策信息抓取（优化版）"""
import re
from bs4 import BeautifulSoup
from .base import BaseScraper, clean_text


class PolicyScraper(BaseScraper):
    """国务院政策文件库抓取器"""
    
    def __init__(self):
        super().__init__("国务院政策文件库", "https://www.gov.cn")
    
    def fetch(self) -> list[dict]:
        """抓取最新政策文件"""
        results = []
        
        # 主要URL
        urls = [
            "https://www.gov.cn/zhengce/zuixin/home.htm",
            "https://www.gov.cn/zhengce/",
        ]
        
        for url in urls:
            html = self._fetch_html(url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 找所有政策链接
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                text = clean_text(a_tag.get_text())
                
                # 筛选政策内容链接
                if '/zhengce/content/' in href and len(text) > 8:
                    if not href.startswith('http'):
                        href = f"https://www.gov.cn{href}" if href.startswith('/') else f"https://www.gov.cn/{href}"
                    
                    # 去重
                    if any(r['title'] == text for r in results):
                        continue
                    
                    # 判断优先级：包含促进/支持/意见等关键词
                    keywords = ['促进', '支持', '意见', '发展', '创新', '改革', '推动', '鼓励', '措施', '方案', '通知']
                    priority = "high" if any(kw in text for kw in keywords) else "normal"
                    
                    results.append({
                        "title": text,
                        "summary": "",
                        "url": href,
                        "source": "国务院政策文件库",
                        "time": "",
                        "priority": priority
                    })
        
        # 如果没有抓到，返回指引
        if not results:
            results.append({
                "title": "国务院政策文件库 - 搜索'促进 支持 意见'",
                "summary": "建议每月1号手动访问 gov.cn/zhengce/ 搜索'促进' '支持' '意见'等关键词",
                "url": "https://www.gov.cn/zhengce/",
                "source": "国务院政策文件库",
                "time": "",
                "priority": "high"
            })
        
        # 高优先级排前面
        results.sort(key=lambda x: (0 if x.get("priority") == "high" else 1))
        
        return results[:15]
