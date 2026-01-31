# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Configuration management for Guest Database Manager."""

import json
import os
from pathlib import Path
from typing import Dict, Optional

import streamlit as st
from cryptography.fernet import Fernet


class ConfigManager:
    """Manages application configuration and secure storage of email settings."""

    def __init__(self):
        """Initialize the configuration manager."""
        self.config_dir = Path.home() / ".guest_database_manager"
        self.config_file = self.config_dir / "config.json"
        self.key_file = self.config_dir / ".key"

        # Ensure config directory exists
        self.config_dir.mkdir(exist_ok=True)

        # Initialize encryption key
        self._init_encryption_key()

    def _init_encryption_key(self) -> None:
        """Initialize or load encryption key for password security."""
        if not self.key_file.exists():
            # Generate new key
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Set restrictive permissions (readable only by owner)
            os.chmod(self.key_file, 0o600)

        # Load key
        with open(self.key_file, 'rb') as f:
            self.key = f.read()
        self.cipher = Fernet(self.key)

    def _encrypt_password(self, password: str) -> str:
        """Encrypt password for secure storage."""
        return self.cipher.encrypt(password.encode()).decode()

    def _decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt password from storage."""
        return self.cipher.decrypt(encrypted_password.encode()).decode()

    def save_email_config(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str,
        provider: str = "Gmail",
    ) -> bool:
        """Save email configuration securely.

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password (will be encrypted)
            from_email: From email address
            from_name: From name
            provider: Email provider name

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            config = {
                "email": {
                    "provider": provider,
                    "smtp_server": smtp_server,
                    "smtp_port": smtp_port,
                    "username": username,
                    "password": self._encrypt_password(password),
                    "from_email": from_email,
                    "from_name": from_name,
                }
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)

            # Set restrictive permissions
            os.chmod(self.config_file, 0o600)
            return True

        except (OSError, ValueError) as e:
            st.error(f"Failed to save email configuration: {str(e)}")
            return False

    def load_email_config(self) -> Optional[Dict[str, any]]:
        """Load email configuration.

        Returns:
            Dictionary with email configuration or None if not found
        """
        try:
            if not self.config_file.exists():
                return None

            with open(self.config_file, encoding='utf-8') as f:
                config = json.load(f)

            email_config = config.get("email")
            if email_config and "password" in email_config:
                # Decrypt password
                email_config["password"] = self._decrypt_password(email_config["password"])

            return email_config

        except (OSError, ValueError, json.JSONDecodeError) as e:
            st.warning(f"Failed to load email configuration: {str(e)}")
            return None

    def clear_email_config(self) -> bool:
        """Clear saved email configuration.

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            if self.config_file.exists():
                self.config_file.unlink()
            return True
        except OSError as e:
            st.error(f"Failed to clear email configuration: {str(e)}")
            return False

    def has_email_config(self) -> bool:
        """Check if email configuration exists.

        Returns:
            True if configuration exists, False otherwise
        """
        return self.config_file.exists()
