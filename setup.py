from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).parent
README = ROOT / "README.md"


setup(
    name="ozon-api",
    version="0.6.4",
    description="Load Ozon Performance API UTM and external traffic statistics into pandas.",
    long_description=README.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    py_modules=["ozon_utm_statistics"],
    python_requires=">=3.10",
    install_requires=[
        "openpyxl>=3.1",
        "pandas>=2.2",
        "psycopg2-binary>=2.9",
        "SQLAlchemy>=2.0",
    ],
)
