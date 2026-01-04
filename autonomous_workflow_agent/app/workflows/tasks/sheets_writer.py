"""
Google Sheets writer task - writes data with idempotency.
"""
from typing import List, Optional, Set
from googleapiclient.errors import HttpError
from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.workflows.models import SheetRow
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class SheetsWriter:
    """Writes data to Google Sheets with idempotency."""
    
    def __init__(self):
        """Initialize the Sheets writer."""
        self.auth_manager = get_auth_manager()
        self.settings = get_settings()
        self.service = None
        self.sheet_id = self.settings.google_sheet_id
    
    def _ensure_service(self) -> bool:
        """Ensure Sheets service is available."""
        if not self.service:
            self.service = self.auth_manager.get_sheets_service()
        return self.service is not None
    
    def _get_existing_email_ids(self, sheet_name: str = "Sheet1") -> Set[str]:
        """
        Get existing email IDs from the sheet to ensure idempotency.
        
        Args:
            sheet_name: Name of the sheet
            
        Returns:
            Set of existing email IDs
        """
        if not self._ensure_service():
            return set()
        
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{sheet_name}!A:A"
            ).execute()
            
            values = result.get('values', [])
            # Skip header row
            email_ids = {row[0] for row in values[1:] if row}
            logger.info(f"Found {len(email_ids)} existing email IDs in sheet")
            return email_ids
            
        except HttpError as e:
            logger.error(f"Error reading existing data: {e}")
            return set()
    
    def _ensure_headers(self, sheet_name: str = "Sheet1") -> bool:
        """
        Ensure the sheet has proper headers.
        
        Args:
            sheet_name: Name of the sheet
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_service():
            return False
        
        try:
            # Check if headers exist
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{sheet_name}!A1:I1"
            ).execute()
            
            values = result.get('values', [])
            
            # If no headers, add them
            if not values:
                headers = [[
                    'Email ID', 'Subject', 'Sender', 'Date', 'Summary',
                    'Category', 'Sentiment', 'Urgency Score', 'Processed At'
                ]]
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{sheet_name}!A1:I1",
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                logger.info("Added headers to sheet")
            
            return True
            
        except HttpError as e:
            logger.error(f"Error ensuring headers: {e}")
            return False
    
    def write_rows(self, rows: List[SheetRow], sheet_name: str = "Sheet1") -> int:
        """
        Write rows to Google Sheets with idempotency.
        
        Args:
            rows: List of SheetRow objects to write
            sheet_name: Name of the sheet
            
        Returns:
            Number of rows successfully written
        """
        if not self._ensure_service():
            logger.error("Sheets service not available")
            return 0
        
        if not rows:
            logger.info("No rows to write")
            return 0
        
        # Ensure headers exist
        if not self._ensure_headers(sheet_name):
            logger.error("Failed to ensure headers")
            return 0
        
        # Get existing email IDs for idempotency
        existing_ids = self._get_existing_email_ids(sheet_name)
        
        # Filter out duplicates
        new_rows = [row for row in rows if row.email_id not in existing_ids]
        
        if not new_rows:
            logger.info("All rows already exist in sheet (idempotent)")
            return 0
        
        logger.info(f"Writing {len(new_rows)} new rows (filtered {len(rows) - len(new_rows)} duplicates)")
        
        try:
            # Prepare values
            values = []
            for row in new_rows:
                # Convert urgency score to text label
                if row.urgency_score >= 0.7:
                    urgency_label = "Important"
                elif row.urgency_score >= 0.4:
                    urgency_label = "Needed Review"
                else:
                    urgency_label = "Take Your Time"
                
                values.append([
                    row.email_id,
                    row.subject,
                    row.sender,
                    row.date,
                    row.summary,
                    row.category,
                    row.sentiment,
                    urgency_label,  # Text label
                    row.processed_at
                ])
            
            # Append to sheet
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=f"{sheet_name}!A:I",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': values}
            ).execute()
            
            updated_rows = result.get('updates', {}).get('updatedRows', 0)
            logger.info(f"Successfully wrote {updated_rows} rows to sheet")
            return updated_rows
            
        except HttpError as e:
            logger.error(f"Sheets API error: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error writing to sheet: {e}")
            return 0


def get_sheets_writer() -> SheetsWriter:
    """Get a Sheets writer instance."""
    return SheetsWriter()
