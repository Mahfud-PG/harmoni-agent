import os
import json
from pathlib import Path
from dotenv import load_dotenv

class ConfigService:
    """
    Sari AI Operating System - Centralized Configuration Service
    Single Source of Truth for all system parameters.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
        
    def _initialize(self):
        from sari_core.paths import PROJECT_ROOT, CORE_DIR, ENV_FILE, DB_FILE, LOG_DIR
        # Load environment variables
        load_dotenv(ENV_FILE)
        
        self.PROJECT_ROOT = PROJECT_ROOT
        self.CORE_DIR = CORE_DIR
        # Basis data ada di folder DATA pengguna, bukan folder program,
        # supaya riwayat obrolan tidak hilang saat aplikasi diperbarui.
        self.DB_PATH = DB_FILE
        self.LOG_DIR = LOG_DIR
        
        # Ensure directories exist
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # AI Models
        self.DEFAULT_LLM_MODEL = "gemini-2.5-flash-exp"
        self.REASONING_MODEL = "gemini-2.5-pro-exp"  
        
        # Memory / Orchestrator Settings
        self.MAX_TOKENS_BEFORE_SUMMARY = 4000
        self.MAX_RECENT_EVENTS_REPLAY = 50 
        
        # Telemetry
        self.ENABLE_DEBUG_TRACE = True

config = ConfigService()
