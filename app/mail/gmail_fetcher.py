"""
Gmail Email Fetcher for bank transaction emails.
Fetches emails from Gmail using Google API and filters for bank notifications.
"""

import os
import pickle
import base64
from typing import List, Tuple, Optional
from datetime import datetime, timedelta, timezone
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import email
from pathlib import Path
from app.logging_config import get_logger

logger = get_logger(__name__)


class GmailFetcher:
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
    
    def fetch_bank_emails(self, max_results: Optional[int] = 10, since_date: Optional[datetime] = None, query: Optional[str] = None, ascending: bool = False, chunk_days: int = 7) -> List[Tuple[str, str, str, datetime]]:
        """
        Fetch bank transaction emails from Gmail.
        
        Args:
            max_results: Maximum number of emails to fetch. If None, fetches all available.
            since_date: Optional datetime; messages newer than this date will be fetched. Internally we use
                        epoch seconds for `after`/`before` filters for accuracy.
            query: Optional full Gmail `q` string. If provided, it overrides default bank keywords.
            ascending: If True, fetch results oldest-first by querying successive date windows.
            chunk_days: When ascending is True, the number of days per query chunk.

        Returns:
            List of tuples (message_id, subject, body, date)
        """
        if not self.service:
            logger.error("Error: Gmail service not initialized")
            return []
        
        try:
            search_terms = []
            # Add bank keywords
            quoted_keywords = [f'\"{kw}\"' for kw in self.BANK_KEYWORDS]
            bank_keywords_formatted = " OR ".join(quoted_keywords)
            search_terms.append(f"({bank_keywords_formatted})")
            
            # Build base query (bank keywords) or use provided explicit query
            quoted_keywords = [f'"{kw}"' for kw in self.BANK_KEYWORDS]
            bank_keywords_formatted = " OR ".join(quoted_keywords)
            base_query = query or f"({bank_keywords_formatted})"

            # If ascending=True, perform date-chunked queries (server-side) starting at since_date
            
            # When ascending is requested, iterate over date ranges forwards from since_date to now
            emails = []
            if ascending:
                if not since_date:
                    # default to 6 months if since_date not set
                    since_date = datetime.now(timezone.utc) - timedelta(days=180)
                end_date = datetime.now(timezone.utc)
                start = since_date
                seen_ids = set()
                # Enforce reasonable chunk_days
                if chunk_days <= 0:
                    chunk_days = 1
                # Stop when we have enough results or when we've reached the end_date
                while start <= end_date and (max_results is None or len(emails) < max_results):
                    chunk_end = min(start + timedelta(days=chunk_days), end_date)
                    # Use epoch timestamps for `after`/`before` to avoid any locale/date parsing issues
                    after_ts = int(start.replace(tzinfo=timezone.utc).timestamp())
                    before_ts = int((chunk_end + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp())
                    chunk_q = f"{base_query} after:{after_ts} before:{before_ts}"
                    per_chunk_max = None
                    if max_results is not None:
                        per_chunk_max = max_results - len(emails)
                    # Paginate through all pages in this chunk
                    msgs = []
                    page_token = None
                    # Determine per-page limit for list calls (use per_chunk_max if given, else default 500)
                    per_page = per_chunk_max if per_chunk_max is not None else 500
                    while True:
                        results = self.service.users().messages().list(userId='me', q=chunk_q, maxResults=per_page if per_page is not None else None, pageToken=page_token).execute()
                        page_msgs = results.get('messages', [])
                        if page_msgs:
                            msgs.extend(page_msgs)
                        page_token = results.get('nextPageToken')
                        # If we've reached per_chunk_max number of results across pages, stop paginating
                        if page_token is None or (per_chunk_max is not None and len(msgs) >= per_chunk_max):
                            break
                    if not msgs:
                        # Move to the next chunk
                        start = chunk_end + timedelta(seconds=1)
                        continue
                    # Gmail returns newest-first, so reverse for oldest-first in this chunk
                    for msg in reversed(msgs):
                        mid = msg.get('id')
                        if not mid or mid in seen_ids:
                            continue
                        email_data = self._get_email_content(mid)
                        if email_data:
                            emails.append(email_data)
                            seen_ids.add(mid)
                        if max_results is not None and len(emails) >= max_results:
                            break
                    start = chunk_end + timedelta(seconds=1)
                return emails
            else:
                # Non-ascending path: use a single query - if since_date given, include it
                q = base_query
                if since_date:
                    q = f"{q} after:{int(since_date.replace(tzinfo=timezone.utc).timestamp())}"
                # Paginate through pages when needed
                msgs = []
                page_token = None
                per_page = max_results if max_results is not None else 500
                while True:
                    results = self.service.users().messages().list(userId='me', q=q, maxResults=per_page if per_page is not None else None, pageToken=page_token).execute()
                    page_msgs = results.get('messages', [])
                    if page_msgs:
                        msgs.extend(page_msgs)
                    page_token = results.get('nextPageToken')
                    if page_token is None or (max_results is not None and len(msgs) >= max_results):
                        break
                if not msgs:
                    return []
                for msg in msgs:
                    email_data = self._get_email_content(msg['id'])
                    if email_data:
                        emails.append(email_data)
                return emails
        
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            return []
    
    def _get_email_content(self, message_id: str) -> Optional[Tuple[str, str, str, datetime]]:
        """
        Get full email content from Gmail message ID.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Tuple of (message_id, subject, body, date) or None
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            
            # Extract body
            body = self._extract_body(message['payload'])
            
            # Try to get message date from internalDate (ms since epoch), fall back to 'Date' header
            email_date = None
            if 'internalDate' in message:
                try:
                    ms = int(message['internalDate'])
                    email_date = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
                except Exception:
                    email_date = None

            if not email_date:
                date_header = next((h['value'] for h in headers if h['name'] == 'Date'), None)
                if date_header:
                    try:
                        # Parse into datetime using email.utils
                        from email.utils import parsedate_to_datetime
                        parsed = parsedate_to_datetime(date_header)
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        email_date = parsed
                    except Exception:
                        email_date = None

            # Fallback to now UTC if parsing fails
            if not email_date:
                email_date = datetime.now(timezone.utc)

            return (message_id, subject, body, email_date)
        
        except Exception as e:
            logger.error(f"Error getting email content: {e}")
            return None
    
    def _extract_body(self, payload) -> str:
        """Extract email body from payload"""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                
                if mime_type == 'text/plain':
                    if 'data' in part['body']:
                        data = part['body'].get('data', '')
                        body += base64.urlsafe_b64decode(data).decode('utf-8')
                elif mime_type == 'text/html' and not body:
                    if 'data' in part['body']:
                        data = part['body'].get('data', '')
                        body += base64.urlsafe_b64decode(data).decode('utf-8')
        elif 'body' in payload:
            data = payload['body'].get('data', '')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        return body.strip()
    
    def fetch_emails_by_sender(self, sender: str, max_results: int = 10, ascending: bool = False) -> List[Tuple[str, str, str, datetime]]:
        """
        Fetch emails from a specific sender (e.g., 'alerts@hdfc.com').
        
        Args:
            sender: Email address or partial name
            max_results: Maximum number of emails
            ascending: If True, fetch oldest-first
        
        Returns:
            List of tuples (message_id, subject, body, date)
        """
        query = f"from:{sender}"
        return self.fetch_bank_emails(max_results=max_results, query=query, ascending=ascending)
    
    def fetch_emails_by_date(self, days: int = 7, ascending: bool = False) -> List[Tuple[str, str, str, datetime]]:
        """
        Fetch bank emails from the last N days.
        
        Args:
            days: Number of days to look back
            ascending: If True, fetch oldest-first
        
        Returns:
            List of tuples (message_id, subject, body, date)
        """
        since_date = datetime.now() - timedelta(days=days)
        return self.fetch_bank_emails(since_date=since_date, ascending=ascending)
