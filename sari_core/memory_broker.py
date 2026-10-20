import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from sari_core.db_manager import db

logger = logging.getLogger(__name__)

@dataclass
class ConversationState:
    person_id: str
    revision_number: int
    recent_messages: List[Dict[str, Any]]
    context_pointers: Dict[str, Any]
    total_tokens_estimate: int

class MemoryBroker:
    """
    Sari AI Operating System - Memory Broker API
    Handles Event Sourcing, Snapshots, and Per-Person Queues.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryBroker, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
        
    def _initialize(self):
        # Per-person locks to prevent race conditions during state replay and event appending
        self._person_locks: Dict[str, asyncio.Lock] = {}
        
    def _get_lock(self, person_id: str) -> asyncio.Lock:
        if person_id not in self._person_locks:
            self._person_locks[person_id] = asyncio.Lock()
        return self._person_locks[person_id]

    async def get_or_create_person(self, channel_id: str, channel_type: str) -> str:
        """Resolves a channel ID (e.g. WA number) to a Person ID."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT person_id FROM channels WHERE channel_id = ? AND channel_type = ?', (channel_id, channel_type))
            row = cursor.fetchone()
            if row:
                return row['person_id']
                
            # Create new person if not exists
            import uuid
            person_id = f"p_{uuid.uuid4().hex[:12]}"
            cursor.execute('INSERT INTO persons (person_id) VALUES (?)', (person_id,))
            cursor.execute('INSERT INTO channels (channel_id, person_id, channel_type) VALUES (?, ?, ?)', (channel_id, person_id, channel_type))
            logger.info(f"Created new Person {person_id} for channel {channel_id} ({channel_type})")
            return person_id

    async def append_event(self, person_id: str, event_type: str, payload: Dict[str, Any]) -> int:
        """Appends an event to the Event Log safely using Optimistic Concurrency Control / Locks."""
        import uuid
        event_id = f"evt_{uuid.uuid4().hex}"
        
        async with self._get_lock(person_id):
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT MAX(revision_number) as max_rev FROM events WHERE person_id = ?', (person_id,))
                row = cursor.fetchone()
                current_rev = row['max_rev'] if row and row['max_rev'] is not None else 0
                new_rev = current_rev + 1
                
                cursor.execute('''
                    INSERT INTO events (event_id, person_id, revision_number, event_type, payload)
                    VALUES (?, ?, ?, ?, ?)
                ''', (event_id, person_id, new_rev, event_type, json.dumps(payload)))
                
                logger.info(f"Appended event {event_type} for person {person_id} at revision {new_rev}")
                return new_rev

    async def build_state(self, person_id: str) -> ConversationState:
        """Rebuilds the current conversation state from Snapshots and Event Logs."""
        async with self._get_lock(person_id):
            with db.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. Load latest snapshot
                cursor.execute('SELECT last_revision_number, state_payload FROM snapshots WHERE person_id = ? ORDER BY last_revision_number DESC LIMIT 1', (person_id,))
                snapshot_row = cursor.fetchone()
                
                if snapshot_row:
                    last_rev = snapshot_row['last_revision_number']
                    state_data = json.loads(snapshot_row['state_payload'])
                    state = ConversationState(**state_data)
                else:
                    last_rev = 0
                    state = ConversationState(person_id=person_id, revision_number=0, recent_messages=[], context_pointers={}, total_tokens_estimate=0)
                
                # 2. Load events after snapshot
                cursor.execute('SELECT revision_number, event_type, payload FROM events WHERE person_id = ? AND revision_number > ? ORDER BY revision_number ASC', (person_id, last_rev))
                events = cursor.fetchall()
                
                for ev in events:
                    payload = json.loads(ev['payload'])
                    if ev['event_type'] == 'MESSAGE_RECEIVED':
                        state.recent_messages.append({"role": "user", "content": payload.get('content')})
                        words = len(str(payload.get('content', '')).split())
                        state.total_tokens_estimate += int(words * 1.3)
                    elif ev['event_type'] == 'LLM_RESPONSE_SENT':
                        state.recent_messages.append({"role": "assistant", "content": payload.get('content')})
                        words = len(str(payload.get('content', '')).split())
                        state.total_tokens_estimate += int(words * 1.3)
                    elif ev['event_type'] == 'TOOL_CALLED':
                        state.recent_messages.append({
                            "role": "assistant",
                            "tool_calls": [{
                                "id": payload.get("id"),
                                "type": "function",
                                "function": {
                                    "name": payload.get("name"),
                                    "arguments": json.dumps(payload.get("args", {}))
                                }
                            }]
                        })
                    elif ev['event_type'] == 'TOOL_RESULT':
                        state.recent_messages.append({
                            "role": "tool",
                            "tool_call_id": payload.get("tool_call_id"),
                            "name": payload.get("name"),
                            "content": payload.get("content")
                        })
                    elif ev['event_type'] == 'CONTEXT_POINTER_SET':
                        key = payload.get('key')
                        if key: state.context_pointers[key] = payload.get('value')
                        
                    state.revision_number = ev['revision_number']
                        
                if len(state.recent_messages) > 100:
                    state.recent_messages = state.recent_messages[-100:]
                    
                return state


    async def clear_memory(self, person_id: str) -> bool:
        """Clears the short-term chat history (events and snapshots) for a person."""
        async with self._get_lock(person_id):
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM events WHERE person_id = ?', (person_id,))
                    cursor.execute('DELETE FROM snapshots WHERE person_id = ?', (person_id,))
                    conn.commit()
                    logger.info(f"Cleared memory for person {person_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to clear memory for {person_id}: {e}")
                return False

memory_broker = MemoryBroker()
