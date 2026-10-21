"""Общие пути тестовых артефактов; документационные PNG не изменяются."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / ".tmp" / "test-screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)
