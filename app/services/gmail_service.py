import os
import pickle
import base64
from typing import List, Tuple, Optional
from datetime import datetime, timedelta, timezone
import json
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import email
from pathlib import Path
from app.logging_config import get_logger

logger = get_logger(__name__)


class GmailService:
    """Fetches emails from Gmail using Google API"""
    
    # Gmail API scopes
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile', 'openid']
    
    # Bank keywords to filter emails
    BANK_KEYWORDS = [
        'HDFC Bank',
        'State Bank of India',
        'SBI',
        'ICICI Bank',
        'Axis Bank',
        'Kotak',
        'Punjab National Bank',
        'PNB',
        'IDBI Bank',
        'Union Bank',
        'Bank of Baroda',
        'UPI Transaction',
        'transaction notification',
        'debit alert',
        'credit alert',
        'payment alert'
    ]
    
    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.pickle",
        credentials_data: Optional[str] = None, # JSON string of client secrets
        token_data: Optional[str] = None # Pickled string of credentials object
    ):
        """
        Initialize Gmail API client.
        
        Args:
            credentials_file: Path to OAuth2 credentials JSON file (fallback)
            token_file: Path to token pickle file (cached credentials, fallback)
            credentials_data: JSON string of client secrets (preferred)
            token_data: Pickled string of credentials object (preferred)
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.credentials_data = credentials_data
        self.token_data = token_data
        self.service = None
        self._authenticate()
    
    def _authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth2"""
        creds = None
        
        if self.token_data:
            try:
                creds = pickle.loads(self.token_data)
            except Exception as e:
                logger.error(f"Error loading credentials from token_data: {e}")

        if not creds and os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if self.credentials_data:
                    try:
                        client_config = json.loads(self.credentials_data)
                        flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)
                        creds = flow.run_local_server(port=0)
                    except Exception as e:
                        logger.error(f"Error during authentication from credentials_data: {e}")
                        raise
                elif not os.path.exists(self.credentials_file):                   
                    raise FileNotFoundError(
                        f"Credentials file '{self.credentials_file}' not found."
                    )
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, self.SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error("Make sure credentials.json is valid and downloaded from Google Cloud Console.")
                    raise
            
            if creds and not self.token_data:
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)
        
        if creds:
            self.service = build('gmail', 'v1', credentials=creds)
        else:
            raise Exception("Failed to authenticate Gmail API")
    
    def fetch_bank_emails(
        self, 
        max_results: Optional[int] = 10, 
        since_date: Optional[datetime] = None, 
        query: Optional[str] = None, 
        ascending: bool = False, 
        chunk_days: int = 7
    ) -> List[Tuple[str, str, str, datetime]]:
        """
        Fetch bank transaction emails from Gmail.
        
        Args:
            max_results: Maximum number of emails to fetch. If None, fetches all available.
            since_date: Optional datetime; messages newer than this date will be fetched. 
                        Internally uses epoch seconds for `after`/`before` filters.
            query: Optional full Gmail `q` string. If provided, overrides default bank keywords.
            ascending: If True, fetch results oldest-first by querying successive date windows.
            chunk_days: When ascending is True, the number of days per query chunk.

        Returns:
            List of tuples (message_id, subject, body, date)
        """
        if not self.service:
            logger.error("Error: Gmail service not initialized")
            return []
        
        try:
            # Build base query: use custom query or construct from bank keywords
            if query:
                base_query = query
            else:
                quoted_keywords = [f'"{keyword}"' for keyword in self.BANK_KEYWORDS]
                base_query = f"({' OR '.join(quoted_keywords)})"

            # Choose between ascending (date-chunked) or standard fetch
            if ascending:
                return self._fetch_ascending(base_query, max_results, since_date, chunk_days)
            else:
                return self._fetch_standard(base_query, max_results, since_date)
        
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []
    
    def _fetch_ascending(
        self, 
        base_query: str, 
        max_results: Optional[int], 
        since_date: Optional[datetime], 
        chunk_days: int
    ) -> List[Tuple[str, str, str, datetime]]:
        """Fetch emails in ascending order (oldest first) using date chunks."""
        
        # Set date range: default to 6 months ago if not provided
        start_date = since_date or (datetime.now(timezone.utc) - timedelta(days=180))
        end_date = datetime.now(timezone.utc)
        chunk_days = max(1, chunk_days)  # Enforce minimum chunk size
        
        emails = []
        seen_ids = set()
        current_start = start_date
        
        # Process date range in chunks to handle large result sets
        while current_start <= end_date and (max_results is None or len(emails) < max_results):
            chunk_end = min(current_start + timedelta(days=chunk_days), end_date)
            
            # Build query with date range using epoch timestamps
            after_timestamp = int(current_start.replace(tzinfo=timezone.utc).timestamp())
            before_timestamp = int((chunk_end + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp())
            chunk_query = f"{base_query} after:{after_timestamp} before:{before_timestamp}"
            
            # Calculate remaining results needed for this chunk
            remaining = None
            if max_results is not None:
                remaining = max_results - len(emails)
            
            # Fetch message IDs for this chunk
            messages = self._fetch_messages_paginated(chunk_query, remaining)
            
            if messages:
                # Process messages in reverse order (oldest first within chunk)
                for message in reversed(messages):
                    message_id = message.get('id')
                    
                    if not message_id or message_id in seen_ids:
                        continue
                    
                    email_data = self._get_email_content(message_id)
                    if email_data:
                        emails.append(email_data)
                        seen_ids.add(message_id)
                    
                    if max_results is not None and len(emails) >= max_results:
                        break
            
            # Move to next chunk
            current_start = chunk_end + timedelta(seconds=1)
        
        return emails
    
    def _fetch_standard(
        self, 
        base_query: str, 
        max_results: Optional[int], 
        since_date: Optional[datetime]
    ) -> List[Tuple[str, str, str, datetime]]:
        """Fetch emails using standard query (newest first)."""
        
        # Add date filter to query if provided
        query = base_query
        if since_date:
            after_timestamp = int(since_date.replace(tzinfo=timezone.utc).timestamp())
            query = f"{base_query} after:{after_timestamp}"
        
        # Fetch message IDs from Gmail
        messages = self._fetch_messages_paginated(query, max_results)
        if not messages:
            return []
        
        # Fetch full email content for each message
        emails = []
        for message in messages:
            message_id = message.get('id')
            if not message_id:
                continue
            
            email_data = self._get_email_content(message_id)
            if email_data:
                emails.append(email_data)
        
        return emails
    
    def _fetch_messages_paginated(
        self, 
        query: str, 
        max_results: Optional[int]
    ) -> List[dict]:
        """Fetch message IDs from Gmail with pagination."""
        
        messages = []
        page_token = None
        results_per_page = max_results if max_results is not None else 500
        
        while True:
            # Fetch page of results from Gmail API
            response = self.service.users().messages().list(
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
    
    def _get_email_content(self, message_id: str) -> Optional[Tuple[str, str, str, datetime]]:
        """
        Get full email content from Gmail message ID.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Tuple of (message_id, subject, body, date) or None
        """
        try:
            # Fetch full message from Gmail
            message = self.service.users().messages().get(
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
            body = self._extract_body(message['payload'])
            
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
    
    def _extract_body(self, payload: dict) -> str:
        """Extract email body from payload (prefer text/plain, fallback to text/html)."""
        
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
    