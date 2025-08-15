from typing import Dict, Any,List, Optional
import asyncio
from datetime import datetime, timedelta
from app.core.logging import get_logger
from app.core.exceptions import SessionNotFoundError

logger = get_logger(__name__)

class SessionManager:
    def __init__(self, session_timeout_minutes: int = 60):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout_minutes = session_timeout_minutes
        self._cleanup_task = None

    async def register_session(self, session_id: str, session_info: Dict[str, Any]):
        self.sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "info": session_info
        }
        logger.info(f"Session {session_id} registered.")

    async def unregister_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Session {session_id} unregistered.")
        else:
            raise SessionNotFoundError(session_id)

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if session:
            await self.update_session_activity(session_id, "get_info")
            return session
        return None

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        return list(self.sessions.values())

    async def update_session_activity(self, session_id: str, activity_type: str, details: Dict[str, Any] = None):
        if session_id in self.sessions:
            self.sessions[session_id]["last_activity"] = datetime.utcnow().isoformat()
            logger.debug(f"Session {session_id} activity: {activity_type}")
        else:
            logger.warning(f"Attempted to update activity for non-existent session {session_id}.")

    async def _cleanup_inactive_sessions(self):
        while True:
            await asyncio.sleep(self.session_timeout_minutes * 60) # Check every timeout period
            logger.info("Running inactive session cleanup.")
            current_time = datetime.utcnow()
            sessions_to_close = []
            for session_id, session_data in self.sessions.items():
                last_activity_time = datetime.fromisoformat(session_data["last_activity"])
                if current_time - last_activity_time > timedelta(minutes=self.session_timeout_minutes):
                    sessions_to_close.append(session_id)
            
            # In a real application, you would also trigger browser_service.close_session here
            # For now, we just unregister them from the manager
            for session_id in sessions_to_close:
                logger.info(f"Closing inactive session: {session_id}")
                await self.unregister_session(session_id)

    def start_cleanup_task(self):
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions())
            logger.info("Inactive session cleanup task started.")

    def stop_cleanup_task(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            logger.info("Inactive session cleanup task stopped.")

    async def close_all_sessions(self):
        for session_id in list(self.sessions.keys()):
            await self.unregister_session(session_id)
        self.stop_cleanup_task()
        logger.info("All sessions closed and cleanup task stopped.")


