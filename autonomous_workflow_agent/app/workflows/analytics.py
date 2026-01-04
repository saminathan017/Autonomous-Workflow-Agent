"""
Analytics module for tracking workflow metrics.
"""
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class AnalyticsStore:
    """Stores and retrieves analytics data."""
    
    def __init__(self):
        """Initialize analytics store."""
        self.settings = get_settings()
        self.db_path = self.settings.get_absolute_database_path()
        self._init_analytics_tables()
    
    def _init_analytics_tables(self):
        """Initialize analytics tables if they don't exist."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Analytics metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                metadata TEXT
            )
        """)
        
        # Email classifications cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_classifications (
                email_id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                sentiment TEXT,
                urgency_score REAL,
                confidence REAL,
                classified_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Analytics tables initialized")
    
    def record_metric(self, metric_name: str, value: float, metadata: Optional[str] = None):
        """
        Record a metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            metadata: Optional metadata JSON string
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO analytics (timestamp, metric_name, metric_value, metadata)
            VALUES (?, ?, ?, ?)
        """, (datetime.now().isoformat(), metric_name, value, metadata))
        
        conn.commit()
        conn.close()
    
    def get_summary(self, days: int = 7) -> Dict:
        """
        Get analytics summary for the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with summary metrics
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Get workflow run stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
                SUM(emails_processed) as total_emails
            FROM workflow_runs
            WHERE started_at >= ?
        """, (cutoff_date,))
        
        run_stats = cursor.fetchone()
        
        # Get category distribution
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM email_classifications
            WHERE classified_at >= ?
            GROUP BY category
        """, (cutoff_date,))
        
        categories = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get sentiment distribution
        cursor.execute("""
            SELECT sentiment, COUNT(*) as count
            FROM email_classifications
            WHERE classified_at >= ?
            GROUP BY sentiment
        """, (cutoff_date,))
        
        sentiments = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get average urgency score
        cursor.execute("""
            SELECT AVG(urgency_score) as avg_urgency
            FROM email_classifications
            WHERE classified_at >= ?
        """, (cutoff_date,))
        
        avg_urgency = cursor.fetchone()[0] or 0.0
        
        conn.close()
        
        return {
            "total_runs": run_stats[0] or 0,
            "successful_runs": run_stats[1] or 0,
            "total_emails": run_stats[2] or 0,
            "success_rate": (run_stats[1] / run_stats[0] * 100) if run_stats[0] > 0 else 0,
            "categories": categories,
            "sentiments": sentiments,
            "avg_urgency_score": round(avg_urgency, 2)
        }
    
    def get_time_series(self, metric_name: str, days: int = 7) -> List[Dict]:
        """
        Get time series data for a metric.
        
        Args:
            metric_name: Name of the metric
            days: Number of days to look back
            
        Returns:
            List of {timestamp, value} dictionaries
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT timestamp, metric_value
            FROM analytics
            WHERE metric_name = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (metric_name, cutoff_date))
        
        data = [{"timestamp": row[0], "value": row[1]} for row in cursor.fetchall()]
        conn.close()
        
        return data
    
    def cache_classification(self, email_id: str, category: str, sentiment: str, 
                           urgency_score: float, confidence: float):
        """
        Cache email classification for analytics.
        
        Args:
            email_id: Email ID
            category: Classification category
            sentiment: Sentiment
            urgency_score: Urgency score
            confidence: Classification confidence
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO email_classifications 
            (email_id, category, sentiment, urgency_score, confidence, classified_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (email_id, category, sentiment, urgency_score, confidence, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()


def get_analytics_store() -> AnalyticsStore:
    """Get analytics store instance."""
    return AnalyticsStore()
