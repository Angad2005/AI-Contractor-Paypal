from bs4 import BeautifulSoup
from pathlib import Path

def verify_page(path: str, contract, repaired: bool = False) -> list[dict]:
    """Verification function - delegates to enhanced verification"""
    from app.services.verifier_enhanced import verify_page_enhanced
    return verify_page_enhanced(path, contract)
