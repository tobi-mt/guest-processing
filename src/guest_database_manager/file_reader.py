"""File reading utilities for CSV and Excel files."""

import pandas as pd
import logging
from pathlib import Path
from typing import Optional

try:
    from .constants import ENCODING_OPTIONS
except ImportError as exc:
    if "attempted relative import" not in str(exc):
        raise
    from constants import ENCODING_OPTIONS

logger = logging.getLogger(__name__)


class FileReader:
    """Handles reading CSV and Excel files with robust error handling."""
    
    @staticmethod
    def read_csv(file_path: str, encoding: str = 'utf-8') -> Optional[pd.DataFrame]:
        """
        Read CSV file with multiple encoding attempts.
        
        Args:
            file_path: Path to the CSV file
            encoding: Primary encoding to try first
            
        Returns:
            DataFrame if successful, None otherwise
        """
        encodings_to_try = [encoding] + [e for e in ENCODING_OPTIONS if e != encoding]
        
        for enc in encodings_to_try:
            try:
                logger.info(f"Trying to read CSV with encoding: {enc}")
                df = pd.read_csv(
                    file_path,
                    encoding=enc,
                    on_bad_lines='skip',
                    engine='c'
                )
                logger.info(f"Successfully read CSV with encoding: {enc}")
                return df
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                logger.warning(f"Failed to read with encoding {enc}: {e}")
                continue
        
        # Fallback to python engine
        try:
            logger.info("Trying fallback with python engine")
            df = pd.read_csv(
                file_path,
                encoding='utf-8',
                on_bad_lines='skip',
                engine='python'
            )
            return df
        except Exception as e:
            logger.error(f"Could not read CSV file with any encoding: {e}")
            return None
    
    @staticmethod
    def read_excel(file_path: str) -> Optional[pd.DataFrame]:
        """
        Read Excel file.
        
        Args:
            file_path: Path to the Excel file
            
        Returns:
            DataFrame if successful, None otherwise
        """
        try:
            df = pd.read_excel(file_path)
            logger.info(f"Successfully read Excel file with {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Could not read Excel file: {e}")
            return None
    
    @staticmethod
    def read_file(file_path: str, encoding: str = 'utf-8') -> Optional[pd.DataFrame]:
        """
        Read file (CSV or Excel) based on extension.
        
        Args:
            file_path: Path to the file
            encoding: Encoding for CSV files
            
        Returns:
            DataFrame if successful, None otherwise
        """
        path = Path(file_path)
        
        if not path.exists():
            logger.error(f"File does not exist: {file_path}")
            return None
        
        suffix = path.suffix.lower()
        
        if suffix == '.csv':
            return FileReader.read_csv(file_path, encoding)
        elif suffix in ['.xlsx', '.xls']:
            return FileReader.read_excel(file_path)
        else:
            logger.error(f"Unsupported file type: {suffix}")
            return None
