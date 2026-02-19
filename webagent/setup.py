from setuptools import setup, find_packages

setup(
    name="webagent",
    version="0.1.0",
    description="AI agent browser automation toolkit",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
        "beautifulsoup4>=4.11.0",
        "lxml>=4.9.0",
    ],
    python_requires=">=3.8",
)
