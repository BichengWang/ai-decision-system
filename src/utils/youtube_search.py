from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
from dotenv import load_dotenv

def search_youtube(query, max_results=10):
    """
    Search YouTube for videos matching the given query.
    
    Args:
        query (str): The search query
        max_results (int): Maximum number of results to return (default: 10)
    
    Returns:
        list: List of video results with title, video ID, and URL
    """
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment variable
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY not found in environment variables")
    
    try:
        # Build the YouTube service
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # Execute the search request
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=max_results,
            type='video'
        ).execute()
        
        # Process the results
        results = []
        for item in search_response.get('items', []):
            video_id = item['id']['videoId']
            title = item['snippet']['title']
            url = f'https://www.youtube.com/watch?v={video_id}'
            results.append({
                'title': title,
                'video_id': video_id,
                'url': url
            })
        
        return results
    
    except HttpError as e:
        print(f'An HTTP error {e.resp.status} occurred: {e.content}')
        return []

if __name__ == '__main__':
    # Example usage
    search_query = input("Enter your search query: ")
    results = search_youtube(search_query)
    
    print("\nSearch Results:")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}")
        print(f"   URL: {result['url']}\n") 