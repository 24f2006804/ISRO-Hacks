from setuptools import setup, find_packages

setup(
    name="space_station_inventory",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn>=0.20.0",
        "sqlalchemy>=2.0.0",
        "pydantic>=2.0.0",
        "python-multipart>=0.0.5",
        "aiosqlite>=0.17.0",
        "pandas>=2.0.0",
        "pytest>=7.0.0",
        "httpx>=0.24.0",
    ],
    python_requires=">=3.8",
)