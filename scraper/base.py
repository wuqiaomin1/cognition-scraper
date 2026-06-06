"""信息源抓取基类"""
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional
from abc import ABC, abstractmethod

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

class BaseScraper(ABC):
    """抓取器基类"""
    
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
    
    def _fetch_html(self, url: str, timeout: int = 15) -> Optional[str]:
        """获取HTML内容"""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or 'utf-8'
            return resp.text
        except Exception as e:
            print(f"[{self.name}] 请求失败: {e}")
            return None
    
    @abstractmethod
    def fetch(self) -> list[dict]:
        """抓取信息，返回 [{title, summary, url, source, time}, ...]"""
        pass


def clean_text(text: str) -> str:
    """清理文本"""
    text = re.sub(r'\s+', ' ', text).strip()
    return text
