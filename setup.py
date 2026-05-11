from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).parent
README = ROOT / "README.md"


setup(
    name="ozon-api",
    version="0.1.1",
    description="Download Ozon Performance API UTM and external traffic statistics.",
    long_description=README.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    py_modules=["ozon_utm_statistics"],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "ozon-utm-statistics=ozon_utm_statistics:main",
        ],
    },
)
