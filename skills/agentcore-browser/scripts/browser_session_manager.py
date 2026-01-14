"""
AgentCore Browser Session Manager

Manages AWS AgentCore Browser sessions without ParameterStore dependency.
Session information is returned directly and should be stored by the caller.
"""

import logging
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from bedrock_agentcore.tools.browser_client import BrowserClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BrowserSessionManager:
    """
    Manages AWS AgentCore Browser sessions.

    This class handles browser session initialization and cleanup without
    relying on AWS Parameter Store. Session information is returned directly
    and should be managed by the caller.
    """

    def __init__(self, aws_region: str = "us-east-1"):
        """
        Initialize the session manager.

        Args:
            aws_region: AWS region for AgentCore Browser service
        """
        self.aws_region = aws_region

    def init_browser_session(self, session_timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        Initialize AWS AgentCore Browser session.

        Args:
            session_timeout_seconds: Optional session timeout in seconds

        Returns:
            Dictionary containing session information including:
            - success: Operation success status
            - session_id: Unique session identifier
            - ws_url: WebSocket connection URL
            - ws_headers: WebSocket connection headers
            - live_view_url: URL to view browser activity (expires in 300s)
        """
        try:
            browser_client = BrowserClient(self.aws_region)

            if session_timeout_seconds:
                browser_client.start(
                    identifier="aws.browser.v1",
                    session_timeout_seconds=session_timeout_seconds
                )
            else:
                browser_client.start(identifier="aws.browser.v1")

            ws_url, headers = browser_client.generate_ws_headers()
            live_view_url = browser_client.generate_live_view_url(expires=300)

            logger.info(f"Browser session initialized: {browser_client.session_id}")

            return {
                "success": True,
                "status": "Browser session initialized successfully",
                "session_id": browser_client.session_id,
                "ws_url": ws_url,
                "ws_headers": headers,
                "live_view_url": live_view_url,
                "aws_region": self.aws_region
            }

        except (NoCredentialsError, ClientError, Exception) as e:
            logger.error(f"Error initializing browser session: {e}")
            return {
                "success": False,
                "status": f"Error: {str(e)}",
                "error": str(e)
            }

    def close_browser_session(self, session_id: str) -> Dict[str, Any]:
        """
        Close the browser session and cleanup resources.

        Args:
            session_id: The session ID to close

        Returns:
            Dictionary containing operation status
        """
        if not session_id:
            return {
                "success": False,
                "status": "session_id is required",
                "error": "Missing session_id parameter"
            }

        try:
            browser_client = BrowserClient(self.aws_region)
            browser_client.client.stop_browser_session(
                browserIdentifier="aws.browser.v1",
                sessionId=session_id
            )

            logger.info(f"Browser session stopped: {session_id}")

            return {
                "success": True,
                "status": "Browser session stopped successfully",
                "session_id": session_id
            }

        except (ClientError, Exception) as e:
            logger.error(f"Error closing browser session: {e}")
            return {
                "success": False,
                "status": f"Error: {str(e)}",
                "error": str(e)
            }
