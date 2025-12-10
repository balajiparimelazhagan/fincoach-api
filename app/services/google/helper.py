import base64
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from app.logging_config import get_logger

logger = get_logger(__name__)


def fetch_messages_paginated(service, query: str, max_results: Optional[int]) -> List[dict]:
    """
    Fetch message IDs from Gmail with pagination.
    
    Args:
        service: Gmail API service instance
        query: Gmail search query string
        max_results: Maximum number of messages to fetch
    
    Returns:
        List of message dictionaries containing message IDs
    """
    messages = []
    page_token = None
    results_per_page = max_results if max_results is not None else 500
    
    while True:
        # Fetch page of results from Gmail API
        response = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=results_per_page,
            pageToken=page_token
        ).execute()
        
        # Collect messages from this page
        page_messages = response.get('messages', [])
        if page_messages:
            messages.extend(page_messages)
        
        # Stop if no more pages or reached limit
        page_token = response.get('nextPageToken')
        if not page_token or (max_results is not None and len(messages) >= max_results):
            break
    
    return messages


def get_email_content(service, message_id: str) -> Optional[Tuple[str, str, str, datetime]]:
    """
    Get full email content from Gmail message ID.
    
    Args:
        service: Gmail API service instance
        message_id: Gmail message ID
    
    Returns:
        Tuple of (message_id, subject, body, date) or None
    """
    try:
        # Fetch full message from Gmail
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        headers = message['payload']['headers']
        
        # Extract subject from headers
        subject = next(
            (h['value'] for h in headers if h['name'] == 'Subject'), 
            'No Subject'
        )
        
        # Extract body from payload
        body = extract_body(message['payload'])
        
        # Extract date: try internalDate (ms since epoch) first
        email_date = None
        if 'internalDate' in message:
            try:
                milliseconds = int(message['internalDate'])
                email_date = datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc)
            except Exception:
                pass
        
        # Fallback to Date header if internalDate failed
        if not email_date:
            date_header = next((h['value'] for h in headers if h['name'] == 'Date'), None)
            if date_header:
                try:
                    from email.utils import parsedate_to_datetime
                    parsed_date = parsedate_to_datetime(date_header)
                    if parsed_date.tzinfo is None:
                        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                    email_date = parsed_date
                except Exception:
                    pass
        
        # Final fallback to current time
        if not email_date:
            email_date = datetime.now(timezone.utc)

        return (message_id, subject, body, email_date)
    
    except Exception as e:
        logger.error(f"Error getting email content: {e}")
        return None


def extract_body(payload: dict) -> str:
    """
    Extract email body from payload (prefer text/plain, fallback to text/html).
    
    Args:
        payload: Gmail message payload dictionary
    
    Returns:
        Extracted email body text
    """
    # Handle multipart messages
    if 'parts' in payload:
        text_plain = ""
        text_html = ""
        
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data', '')
            
            if not body_data:
                continue
            
            # Decode base64url-encoded data
            try:
                decoded = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
            except Exception:
                continue
            
            # Collect text/plain and text/html parts
            if mime_type == 'text/plain':
                text_plain += decoded
            elif mime_type == 'text/html':
                text_html += decoded
        
        # Prefer text/plain over text/html
        return (text_plain or text_html).strip()
    
    # Handle single-part messages
    if 'body' in payload:
        body_data = payload['body'].get('data', '')
        if body_data:
            try:
                return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore').strip()
            except Exception:
                pass
    
    return ""
