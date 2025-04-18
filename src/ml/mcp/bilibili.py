import os
from typing import Any
from bilibili_api import search, sync
from mcp.server.fastmcp import FastMCP

mcp = FastMCP('bilibili mcp server')


@mcp.tool('general_search')
def general_search(keyword):
    """
    Search Bilibili API with the given keyword.
    
    Args:
        keyword: Search term to look for on Bilibili
        
    Returns:
        Dictionary containing the search results from Bilibili
    """
    return sync(search.search(keyword))


if __name__ == "__main__":
    mcp.run(transport='stdio')