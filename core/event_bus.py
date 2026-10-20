import threading
import traceback
from typing import Callable, Dict, List, Any

class EventBus:
    """
    Event Bus Asinkron untuk Pub/Sub antar-plugin.
    Memungkinkan plugin memancar dan mendengar event tanpa saling ketergantungan.
    """
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def on(self, event_name: str, handler: Callable):
        """Mendaftarkan fungsi handler pendengar untuk event tertentu."""
        with self._lock:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            if handler not in self._listeners[event_name]:
                self._listeners[event_name].append(handler)
        print(f"[EventBus] Registered listener for '{event_name}': {handler.__name__}")

    def off(self, event_name: str, handler: Callable):
        """Mencabut handler dari event tertentu."""
        with self._lock:
            if event_name in self._listeners and handler in self._listeners[event_name]:
                self._listeners[event_name].remove(handler)

    def emit(self, event_name: str, data: Any = None):
        """Memancarkan event ke seluruh pendengar di latar belakang (thread terpisah)."""
        with self._lock:
            handlers = list(self._listeners.get(event_name, []))

        if not handlers:
            return

        def _notify():
            for handler in handlers:
                try:
                    handler(data)
                except Exception as e:
                    print(f"[EventBus] ❌ Error in handler {handler.__name__} for event '{event_name}': {e}")
                    traceback.print_exc()

        thread = threading.Thread(target=_notify, daemon=True)
        thread.start()

    def get_status(self) -> Dict[str, int]:
        """Mengembalikan daftar status event aktif beserta jumlah pendengarnya."""
        with self._lock:
            return {k: len(v) for k, v in self._listeners.items()}

# Singleton Instance Global
event_bus = EventBus()

def on(event_name: str, handler: Callable):
    event_bus.on(event_name, handler)

def emit(event_name: str, data: Any = None):
    event_bus.emit(event_name, data)

def get_event_bus_status():
    return event_bus.get_status()
