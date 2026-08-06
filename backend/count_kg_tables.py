import sys
import os

# Ensure app path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pyrefly: ignore [missing-import]
from app.core.database import SessionLocal
from sqlalchemy import text

def count_tables():
    db = SessionLocal()
    tables = [
        'knowledge_entities',
        'knowledge_aliases',
        'knowledge_properties',
        'knowledge_relationships',
        'knowledge_graph_imports',
        'knowledge_graph_import_nodes',
        'knowledge_graph_import_edges'
    ]
    
    print("==========================================")
    print("Thống kê dữ liệu Knowledge Graph Tables:")
    print("==========================================")
    
    total = 0
    for table in tables:
        try:
            res = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"| {table:<30} | {res:>10,} hàng |")
            total += res
        except Exception as e:
            print(f"| {table:<30} | Lỗi: {e} |")
            
    print("------------------------------------------")
    print(f"Tổng cộng: {total:,} bản ghi")
    print("==========================================")
    db.close()

if __name__ == "__main__":
    count_tables()
