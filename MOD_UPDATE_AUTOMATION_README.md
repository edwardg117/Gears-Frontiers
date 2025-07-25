# Mod Update Automation Script

A comprehensive Python script for automating mod updates in Minecraft modpacks using MCUpdater XML configurations. This tool analyzes your modpack, checks for updates across Modrinth and CurseForge, and generates structured output files for easy update management.

## Features

- **Multi-Platform Support**: Checks updates from Modrinth and CurseForge APIs
- **Intelligent Version Comparison**: Semantic versioning with fallback strategies
- **Dependency Analysis**: Detects potential conflicts and dependency changes
- **Update Categorization**: Classifies updates by severity (major/minor/patch)
- **Multiple Output Formats**: XML, Markdown changelog, and detailed logs
- **Configurable Policies**: Exclude mods, pin versions, control update types
- **Rate Limiting**: Respects API limits with built-in rate limiting
- **Progress Reporting**: Real-time progress bars and verbose logging
- **Safety Features**: File hash verification and rollback information

## Requirements

- Python 3.8 or higher
- Required packages: `requests`, `packaging`, `tqdm`

## Installation

1. Install required packages:
```bash
pip install requests packaging tqdm
```

2. Copy the configuration template:
```bash
cp mod_update_config.ini.example mod_update_config.ini
```

3. Edit the configuration file with your API keys and preferences

## Configuration

### API Keys

- **Modrinth**: Optional - public API access available without key
- **CurseForge**: Required - get your key from [CurseForge Console](https://console.curseforge.com/)

### Key Configuration Options

```ini
[MODPACK]
target_minecraft_version = 1.21.1
target_loader = neoforge
excluded_mods = mod1,mod2,mod3
pinned_versions = create:6.0.4,jei:19.21.0.247

[UPDATE_POLICY]
allow_major_updates = true
allow_minor_updates = true
allow_patch_updates = true
```

## Usage

### Basic Usage

```bash
# Check for updates in the current directory
python mod_update_automation.py .

# Check specific directory
python mod_update_automation.py /path/to/modpack/xml/files

# Dry run (preview only)
python mod_update_automation.py . --dry-run

# Verbose output
python mod_update_automation.py . --verbose

# Custom configuration file
python mod_update_automation.py . --config my_config.ini

# Custom output directory
python mod_update_automation.py . --output /path/to/output
```

### Command Line Options

- `directory`: Directory containing MCUpdater XML files (required)
- `--config, -c`: Configuration file path (default: mod_update_config.ini)
- `--dry-run, -n`: Preview updates without generating files
- `--verbose, -v`: Enable verbose output
- `--output, -o`: Output directory for generated files

## Output Files

The script generates three types of output files:

### 1. XML Update Configuration (`updates-YYYY-MM-DD.xml`)
- Compatible with MCUpdater schema
- Contains only mods with available updates
- Includes new version numbers, download URLs, and file hashes
- Can be imported into your modpack configuration

### 2. Changelog Documentation (`CHANGELOG-YYYY-MM-DD.md`)
- Executive summary with update counts and categories
- Per-mod sections with version changes and release notes
- Organized by update severity (major/minor/patch)
- Includes compatibility warnings and important notes

### 3. Execution Log (`update-log-YYYY-MM-DD.txt`)
- Detailed technical log with timestamps
- API response details and error information
- Processing statistics and performance metrics
- Platform breakdown and mod analysis

## Update Severity Classification

- **Major Updates**: Breaking changes, major version bumps
- **Minor Updates**: New features, minor version bumps
- **Patch Updates**: Bug fixes, patch version bumps

## Safety Features

- **File Hash Verification**: Ensures download integrity
- **Rollback Information**: Includes current file hashes for reverting
- **Dependency Checking**: Warns about potential conflicts
- **Version Pinning**: Prevents updates for specific mods
- **Exclusion Lists**: Skip problematic or unnecessary mods

## Error Handling

The script includes robust error handling for:
- Network timeouts and API failures
- Missing or discontinued mods
- API rate limit exceeded scenarios
- Malformed configuration files
- Invalid XML structures

## Performance Considerations

- **Concurrent Requests**: Uses ThreadPoolExecutor for parallel API calls
- **Rate Limiting**: Respects API limits to prevent blocking
- **Progress Reporting**: Shows real-time progress for long operations
- **Efficient Parsing**: Optimized XML parsing for large modpacks

## Troubleshooting

### Common Issues

1. **No CurseForge updates found**: Ensure you have a valid API key
2. **Rate limit exceeded**: Reduce `rate_limit_per_minute` in config
3. **Network timeouts**: Increase `request_timeout` in config
4. **XML parsing errors**: Check for malformed XML files

### Debug Mode

Run with `--verbose` flag for detailed debugging information:
```bash
python mod_update_automation.py . --verbose
```

## Contributing

This script is part of the Gears & Frontiers modpack project. For issues or improvements, please refer to the main repository.

## License

MIT License - see the main repository for details.
