"""数据库初始化脚本 —— 首次部署时运行一次"""
from models import init_db

if __name__ == '__main__':
    init_db()
    print("数据库初始化完成！")
