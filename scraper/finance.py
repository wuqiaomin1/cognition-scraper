"""巨潮资讯网 - 上市公司公告/管理层分析抓取"""
import re
from bs4 import BeautifulSoup
from .base import BaseScraper, clean_text

class CninfoScraper(BaseScraper):
    """巨潮资讯网抓取器"""
    
    def __init__(self):
        super().__init__("巨潮资讯网", "http://www.cninfo.com.cn")
    
    def fetch(self) -> list[dict]:
        """抓取最新包含"管理层分析与讨论"的公告"""
        results = []
        try:
            # 搜索管理层分析
            search_url = "http://www.cninfo.com.cn/new/fulltextSearch/full"
            params = {
                "searchkey": "管理层分析与讨论",
                "sdate": "",
                "edate": "",
                "isfulltext": "false",
                "sortName": "pubdate",
                "sortType": "desc",
                "pageNum": 1,
                "pageSize": 15
            }
            html = self._fetch_html(
                f"{search_url}?searchkey={'管理层分析与讨论'}&sdate=&edate=&isfulltext=false&sortName=pubdate&sortType=desc&pageNum=1"
            )
            
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                for item in soup.select('.list-group-item, .result-item, tr, .search-item')[:15]:
                    title_el = item.select_one('a')
                    if title_el:
                        title = clean_text(title_el.get_text())
                        if title and len(title) > 5:
                            results.append({
                                "title": title,
                                "summary": f"巨潮资讯网公告 - {title[:80]}",
                                "url": f"http://www.cninfo.com.cn{title_el.get('href', '')}" if title_el.get('href', '').startswith('/') else title_el.get('href', ''),
                                "source": "巨潮资讯网",
                                "time": ""
                            })
        except Exception as e:
            print(f"[巨潮资讯网] 抓取失败: {e}")
        
        # 如果API抓取失败，返回链接指引
        if not results:
            results.append({
                "title": "巨潮资讯网 - 搜索'管理层分析与讨论'",
                "summary": "建议手动访问 cninfo.com.cn 搜索'管理层分析与讨论'查看最新上市公司管理层分析报告",
                "url": "http://www.cninfo.com.cn/new/fulltextSearch?key=%E7%AE%A1%E7%90%86%E5%B1%82%E5%88%86%E6%9E%90%E4%B8%8E%E8%AE%A8%E8%AE%BA",
                "source": "巨潮资讯网",
                "time": ""
            })
        
        return results[:15]
