try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

from typing import List, Dict

def web_search(query: str, max_results: int = 8) -> List[Dict[str, str]]:
    """
    Performs a web search and returns snippets.
    Increased to 8 results for better context.
    """
    if DDGS is None:
        print("[SEARCH WARNING] duckduckgo-search not installed. Skipping web search.")
        return []

    results = []
    try:
        with DDGS() as ddgs:
            ddgs_gen = ddgs.text(query, region='wt-wt', safesearch='moderate', timelimit='y')
            for i, r in enumerate(ddgs_gen):
                if len(results) >= max_results:
                    break
                
                # Quality filtering - skip results with very short or empty snippets
                snippet = r.get("body", "").strip()
                if len(snippet) < 20:  # Skip low-quality results
                    continue
                    
                results.append({
                    "title": r.get("title", "").strip(),
                    "link": r.get("href", ""),
                    "snippet": snippet
                })
    except Exception as e:
        print(f"[SEARCH ERROR] {e}")
    
    return results

def format_search_results(results: List[Dict[str, str]]) -> str:
    """Format search results for LLM context."""
    if not results:
        return ""
    
    header = "### WEB SEARCH RESULTS (Current Information):\n"
    formatted = []
    for idx, r in enumerate(results, 1):
        formatted.append(f"{idx}. **{r['title']}**\n   {r['snippet']}\n   Source: {r['link']}")
    
    return header + "\n".join(formatted) + "\n\n"

