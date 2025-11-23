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
                print(f"Error loading credentials from token_data: {e}")

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
                        print(f"Error during authentication from credentials_data: {e}")
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
                    print("\nMake sure credentials.json is valid and downloaded from Google Cloud Console.")
                    raise
            
            if creds and not self.token_data:
                with open(self.token_file, 'wb') as token:
                    pickle.dump(creds, token)
        
        if creds:
            self.service = build('gmail', 'v1', credentials=creds)
        else:
            raise Exception("Failed to authenticate Gmail API")
    
    def fetch_bank_emails(self, max_results: Optional[int] = 10, since_date: Optional[datetime] = None) -> List[Tuple[str, str, str]]:
        """
        Fetch bank transaction emails from Gmail.
        
        Args:
            max_results: Maximum number of emails to fetch. If None, fetches all available.
            since_date: Optional. Fetch emails newer than this date.
        
        Returns:
            List of tuples (message_id, subject, body)
        """
        if not self.service:
            print("Error: Gmail service not initialized")
            return []
        
        try:
            search_terms = []
            # Add bank keywords
            quoted_keywords = [f'\"{kw}\"' for kw in self.BANK_KEYWORDS]
            bank_keywords_formatted = " OR ".join(quoted_keywords)
            search_terms.append(f"({bank_keywords_formatted})")
            
            # Add date filter if provided
            if since_date:
                search_terms.append(f"after:{since_date.strftime('%Y/%m/%d')}")
            
            search_query = " ".join(search_terms)
            
            print(f"Fetching emails with query: {search_query}")
            
            # Fetch email IDs
            results = self.service.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=max_results if max_results is not None else None
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                print("No bank emails found")
                return []
            
            print(f"Found {len(messages)} emails")
            
            # Fetch full email content
            emails = []
            for msg in messages:
                email_data = self._get_email_content(msg['id'])
                if email_data:
                    emails.append(email_data)
            
            return emails
        
        except Exception as e:
            print(f"Error fetching emails: {e}")
            return []
    
    def _get_email_content(self, message_id: str) -> Optional[Tuple[str, str, str]]:
        """
        Get full email content from Gmail message ID.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Tuple of (message_id, subject, body) or None
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
            
            return (message_id, subject, body)
        
        except Exception as e:
            print(f"Error getting email content: {e}")
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
    
    def fetch_emails_by_sender(self, sender: str, max_results: int = 10) -> List[Tuple[str, str]]:
        """
        Fetch emails from a specific sender (e.g., 'alerts@hdfc.com').
        
        Args:
            sender: Email address or partial name
            max_results: Maximum number of emails
        
        Returns:
            List of tuples (subject, body)
        """
        query = f"from:{sender}"
        return self.fetch_bank_emails(max_results=max_results, query=query)
    
    def fetch_emails_by_date(self, days: int = 7) -> List[Tuple[str, str]]:
        """
        Fetch bank emails from the last N days.
        
        Args:
            days: Number of days to look back
        
        Returns:
            List of tuples (subject, body)
        """
        since_date = datetime.now() - timedelta(days=days)
        return self.fetch_bank_emails(since_date=since_date)
