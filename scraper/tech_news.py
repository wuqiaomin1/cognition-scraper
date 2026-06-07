"""36氪、虎嗅、极客公园 - 科技商业资讯抓取（优化版）"""
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from .base import BaseScraper, clean_text


class Kr36Scraper(BaseScraper):
    """36氪抓取器 - 使用RSS Feed"""
    
    def __init__(self):
        super().__init__("36氪", "https://36kr.com")
    
    def fetch(self) -> list[dict]:
        results = []
        try:
            resp = self.session.get("https://36kr.com/feed", timeout=15)
            resp.raise_for_status()
            # 强制 UTF-8 编码，避免中文乱码
            resp.encoding = 'utf-8'
            
            root = ET.fromstring(resp.text)
            channel = root.find('channel')
            if channel is None:
                return results
            
            for item in channel.findall('item')[:20]:
                title = clean_text(item.findtext('title', ''))
                link = item.findtext('link', '')
                desc = clean_text(item.findtext('description', ''))[:200]
                
                if title and len(title) > 5:
                    results.append({
                        "title": title,
                        "summary": desc,
                        "url": link,
                        "source": "36氪",
                        "time": item.findtext('pubDate', '')
                    })
        except Exception as e:
            print(f"[36氪] RSS抓取失败: {e}")
        
        return results[:15]


class HuxiuScraper(BaseScraper):
    """虎嗅抓取器 - 使用RSS Feed（备用多个源）"""
    
    def __init__(self):
        super().__init__("虎嗅", "https://www.huxiu.com")
    
    def fetch(self) -> list[dict]:
        results = []
        
        # 尝试多个RSS源
        rss_urls = [
            "https://www.huxiu.com/rss/0.xml",
            "https://feedx.net/rss/huxiu.xml",
        ]
        
        for rss_url in rss_urls:
            try:
                resp = self.session.get(rss_url, timeout=15)
                resp.raise_for_status()
                resp.encoding = 'utf-8'
                
                root = ET.fromstring(resp.text)
                channel = root.find('channel')
                if channel is None:
                    continue
                
                for item in channel.findall('item')[:20]:
                    title = clean_text(item.findtext('title', ''))
                    link = item.findtext('link', '')
                    desc = clean_text(item.findtext('description', ''))[:200]
                    
                    if title and len(title) > 5:
                        results.append({
                            "title": title,
                            "summary": desc,
                            "url": link,
                            "source": "虎嗅",
                            "time": item.findtext('pubDate', '')
                        })
                
                if results:
                    break
            except Exception as e:
                print(f"[虎嗅] {rss_url} 失败: {e}")
                continue
        
        # 如果所有RSS都失败，返回指引
        if not results:
            results.append({
                "title": "虎嗅 - 建议手动访问 huxiu.com 查看最新资讯",
                "summary": "虎嗅网由于反爬机制，自动抓取受限。建议每天早上花5分钟手动浏览首页标题和摘要。",
                "url": "https://www.huxiu.com",
                "source": "虎嗅",
                "time": ""
            })
        
        return results[:15]


class GeekparkScraper(BaseScraper):
    """极客公园抓取器"""
    
    def __init__(self):
        super().__init__("极客公园", "https://www.geekpark.net")
    
    def fetch(self) -> list[dict]:
        results = []
        
        # 尝试直接请求（某些环境下可以访问）
        try:
            html = self._fetch_html(self.url)
            if html and len(html) > 5000:
                soup = BeautifulSoup(html, 'html.parser')
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag.get('href', '')
                    text = clean_text(a_tag.get_text())
                    # 极客公园文章链接通常包含 /news/ 或 /article/
                    if ('/news/' in href or '/article/' in href) and len(text) > 8:
                        if not href.startswith('http'):
                            href = f"https://www.geekpark.net{href}" if href.startswith('/') else f"https://www.geekpark.net/{href}"
                        
                        # 去重
                        if not any(r['title'] == text for r in results):
                            results.append({
                                "title": text,
                                "summary": "",
                                "url": href,
                                "source": "极客公园",
                                "time": ""
                            })
        except Exception as e:
            print(f"[极客公园] HTML抓取失败: {e}")
        
        # 如果抓取失败，返回指引
        if not results:
            results.append({
                "title": "极客公园 - 建议手动访问 geekpark.net 查看最新资讯",
                "summary": "极客公园由于反爬机制，自动抓取受限。建议每天早上花5分钟手动浏览首页标题和摘要。",
                "url": "https://www.geekpark.net",
                "source": "极客公园",
                "time": ""
            })
        
        return results[:15]
