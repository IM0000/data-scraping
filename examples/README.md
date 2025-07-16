# Examples

This directory contains examples for the data scraping project.

## Contents

- `basic_structure.py` - Basic file structure and coding patterns
- `models/` - Data model usage examples
- `queue_usage.py` - Message queue system examples
- `test_pattern.py` - Testing patterns and examples
- `scripts/` - Script management system examples (Phase 3)

## Phase 3: Script Management System

The `scripts/` directory contains examples for the script management system:

- `usage_example.py` - Comprehensive usage examples including:
  - Basic script downloading and caching
  - Version management and cache control
  - Convenience functions usage
  - Cache statistics and management

### Quick Start

```python
from src.scripts import get_script, ScriptDownloader

# Simple usage with convenience function
script_path, metadata = await get_script("my_scraper", "1.0.0")

# Advanced usage with downloader
async with ScriptDownloader() as downloader:
    script_path, metadata = await downloader.get_script("my_scraper")
    print(f"Downloaded: {metadata.name} v{metadata.version}")
```
