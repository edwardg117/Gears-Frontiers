#!/usr/bin/env python3
"""
Comprehensive Mod Update Automation Script for Minecraft Modpacks
Analyzes MCUpdater XML configurations and checks for mod updates across multiple platforms.

Author: The Augster
Version: 1.0.0
License: MIT
"""

import argparse
import configparser
import hashlib
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
from packaging import version
from tqdm import tqdm

# Configuration constants
DEFAULT_CONFIG_FILE = "mod_update_config.ini"
MODRINTH_API_BASE = "https://api.modrinth.com/v2"
CURSEFORGE_API_BASE = "https://api.curseforge.com/v1"
MINECRAFT_GAME_ID = 432  # CurseForge game ID for Minecraft
DEFAULT_RATE_LIMIT = 60  # Requests per minute
DEFAULT_TIMEOUT = 30  # Request timeout in seconds
MAX_WORKERS = 5  # Maximum concurrent API requests

class ModUpdateConfig:
    """Configuration management for the mod update automation script."""
    
    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """Load configuration from file or create default configuration."""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """Create default configuration file."""
        self.config['API'] = {
            'modrinth_api_key': '',
            'curseforge_api_key': '',
            'rate_limit_per_minute': str(DEFAULT_RATE_LIMIT),
            'request_timeout': str(DEFAULT_TIMEOUT)
        }
        
        self.config['MODPACK'] = {
            'target_minecraft_version': '1.21.1',
            'target_loader': 'neoforge',
            'excluded_mods': '',
            'pinned_versions': ''
        }
        
        self.config['UPDATE_POLICY'] = {
            'allow_major_updates': 'true',
            'allow_minor_updates': 'true',
            'allow_patch_updates': 'true',
            'check_dependencies': 'true',
            'verify_file_hashes': 'true'
        }
        
        self.config['OUTPUT'] = {
            'output_directory': 'updates',
            'generate_xml': 'true',
            'generate_changelog': 'true',
            'generate_log': 'true',
            'include_rollback_info': 'true'
        }

        self.config['SCANNING'] = {
            'ignored_directories': 'test_output,output,generated,build,dist,temp,tmp'
        }
        
        self.save_config()
    
    def save_config(self):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            self.config.write(f)
    
    def get(self, section: str, key: str, fallback: str = '') -> str:
        """Get configuration value with fallback."""
        return self.config.get(section, key, fallback=fallback)
    
    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        """Get boolean configuration value with fallback."""
        return self.config.getboolean(section, key, fallback=fallback)
    
    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        """Get integer configuration value with fallback."""
        return self.config.getint(section, key, fallback=fallback)

class ModInfo:
    """Data class for mod information."""
    
    def __init__(self, name: str, mod_id: str, url: str, source_file: str):
        self.name = name
        self.mod_id = mod_id
        self.url = url
        self.source_file = source_file
        self.current_version = None
        self.current_hash = None
        self.current_size = None
        self.dependencies = []
        self.side = None
        self.required = True
        self.mod_type = "Regular"
        
        # Platform-specific identifiers
        self.platform = self._detect_platform()
        self.project_id = None
        self.version_id = None
        self.file_path = None
        
        self._extract_platform_ids()
    
    def _detect_platform(self) -> str:
        """Detect the mod hosting platform from URL."""
        if 'cdn.modrinth.com' in self.url:
            return 'modrinth'
        elif 'edge.forgecdn.net' in self.url:
            return 'curseforge'
        else:
            return 'unknown'
    
    def _extract_platform_ids(self):
        """Extract platform-specific identifiers from URL."""
        if self.platform == 'modrinth':
            match = re.search(r'cdn\.modrinth\.com/data/([^/]+)/versions/([^/]+)/', self.url)
            if match:
                self.project_id, self.version_id = match.groups()
        elif self.platform == 'curseforge':
            match = re.search(r'edge\.forgecdn\.net/files/(\d+)/(\d+)/', self.url)
            if match:
                self.file_path = f"{match.group(1)}/{match.group(2)}"

class ModuleAttributeMapper:
    """Manages mapping of module attributes (side, required) from existing XML files."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.attributes = {}  # mod_id -> {side, required, source_file, priority}
        self.file_priorities = {}  # file_path -> priority_score

    def _calculate_file_priority(self, file_path: str) -> int:
        """Calculate priority score for a file. Higher score = higher priority."""
        file_name = os.path.basename(file_path).lower()

        # Base file has highest priority
        if file_name == 'base.xml':
            return 1000

        # Recent update files have high priority (based on date in filename)
        if file_name.startswith('updates-') or file_name.startswith('2025-'):
            # Extract date and use as priority
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', file_name)
            if date_match:
                year, month, day = map(int, date_match.groups())
                return year * 10000 + month * 100 + day

        # Other files have lower priority
        return 100

    def add_module(self, mod_id: str, side: str, required: bool, source_file: str, mod_type: str = "Regular"):
        """Add or update module attributes with priority-based conflict resolution."""
        if not mod_id or mod_id == 'Unknown':
            return

        # Calculate file priority
        if source_file not in self.file_priorities:
            self.file_priorities[source_file] = self._calculate_file_priority(source_file)

        file_priority = self.file_priorities[source_file]

        # Check if we should update this module's attributes
        should_update = True
        if mod_id in self.attributes:
            existing_priority = self.attributes[mod_id]['priority']
            if file_priority < existing_priority:
                should_update = False
                self.logger.debug(f"Skipping {mod_id} from {source_file} (lower priority than {self.attributes[mod_id]['source_file']})")
            elif file_priority == existing_priority:
                # Same priority - log conflict but keep existing
                self.logger.debug(f"Attribute conflict for {mod_id}: {source_file} vs {self.attributes[mod_id]['source_file']} (keeping existing)")
                should_update = False

        if should_update:
            self.attributes[mod_id] = {
                'side': side,
                'required': required,
                'mod_type': mod_type,
                'source_file': source_file,
                'priority': file_priority
            }
            self.logger.debug(f"Added/updated {mod_id}: side={side}, required={required}, mod_type={mod_type} from {source_file}")

            # Special logging for removal status
            if mod_type == 'Removal':
                self.logger.info(f"Mod {mod_id} marked for REMOVAL from {source_file}")

    def get_attributes(self, mod_id: str) -> Dict[str, Union[str, bool]]:
        """Get attributes for a module, with fallback defaults."""
        if mod_id in self.attributes:
            attrs = self.attributes[mod_id]
            self.logger.debug(f"Retrieved preserved attributes for {mod_id}: side={attrs['side']}, required={attrs['required']}, mod_type={attrs['mod_type']}")
            return {
                'side': attrs['side'],
                'required': attrs['required'],
                'mod_type': attrs['mod_type'],
                'source': 'preserved'
            }
        else:
            # Fallback defaults
            self.logger.info(f"No preserved attributes for {mod_id}, using fallback defaults: side=BOTH, required=True, mod_type=Regular")
            return {
                'side': 'BOTH',
                'required': True,
                'mod_type': 'Regular',
                'source': 'default'
            }

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the attribute mapping."""
        stats = {
            'total_modules': len(self.attributes),
            'files_processed': len(self.file_priorities)
        }

        # Count by side, required, and mod_type
        side_counts = {}
        required_counts = {'true': 0, 'false': 0}
        mod_type_counts = {}

        for attrs in self.attributes.values():
            side = attrs['side']
            side_counts[side] = side_counts.get(side, 0) + 1

            required_key = 'true' if attrs['required'] else 'false'
            required_counts[required_key] += 1

            mod_type = attrs.get('mod_type', 'Regular')
            mod_type_counts[mod_type] = mod_type_counts.get(mod_type, 0) + 1

        stats.update(side_counts)
        stats.update(required_counts)
        stats.update({f'mod_type_{k}': v for k, v in mod_type_counts.items()})

        return stats

class XMLParser:
    """Parser for MCUpdater XML configuration files."""

    def __init__(self, logger: logging.Logger, config: ModUpdateConfig = None, mapper: ModuleAttributeMapper = None):
        self.logger = logger
        self.config = config
        self.mods = {}
        self.mapper = mapper
    
    def parse_xml_file(self, file_path: str) -> Dict[str, ModInfo]:
        """Parse a single XML file and extract mod information."""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Handle namespace - register it for XPath queries
            namespace = {'mcupdater': 'http://www.mcupdater.com'}

            # Find modules with namespace awareness
            modules = root.findall('.//mcupdater:Module', namespace)
            if not modules:
                # Fallback: try without namespace (for files without namespace)
                modules = root.findall('.//Module')

            file_mods = {}

            for module in modules:
                mod_info = self._parse_module(module, file_path)
                if mod_info:
                    file_mods[mod_info.mod_id] = mod_info

            self.logger.info(f"Parsed {len(file_mods)} mods from {file_path}")
            return file_mods

        except ET.ParseError as e:
            self.logger.error(f"Failed to parse XML file {file_path}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error parsing {file_path}: {e}")
            return {}
    
    def _parse_module(self, module: ET.Element, source_file: str) -> Optional[ModInfo]:
        """Parse a single Module element."""
        try:
            name = module.get('name', 'Unknown')
            mod_id = module.get('id', 'Unknown')
            depends = module.get('depends', '')
            side = module.get('side', 'BOTH')

            # Handle namespace for child elements
            namespace = {'mcupdater': 'http://www.mcupdater.com'}

            # Try with namespace first, then without
            url_elem = module.find('mcupdater:URL', namespace)
            if url_elem is None:
                url_elem = module.find('URL')

            if url_elem is None:
                self.logger.debug(f"No URL element found for mod {name} ({mod_id})")
                return None

            if not url_elem.text or not url_elem.text.strip():
                self.logger.debug(f"Empty URL found for mod {name} ({mod_id})")
                return None

            mod_info = ModInfo(name, mod_id, url_elem.text.strip(), source_file)
            mod_info.side = side
            mod_info.dependencies = [dep.strip() for dep in depends.split() if dep.strip()]

            # Extract additional information (try with namespace first)
            size_elem = module.find('mcupdater:Size', namespace)
            if size_elem is None:
                size_elem = module.find('Size')
            if size_elem is not None and size_elem.text:
                mod_info.current_size = int(size_elem.text)

            md5_elem = module.find('mcupdater:MD5', namespace)
            if md5_elem is None:
                md5_elem = module.find('MD5')
            if md5_elem is not None and md5_elem.text:
                mod_info.current_hash = md5_elem.text.strip()

            required_elem = module.find('mcupdater:Required', namespace)
            if required_elem is None:
                required_elem = module.find('Required')
            if required_elem is not None and required_elem.text:
                mod_info.required = required_elem.text.strip().lower() == 'true'

            mod_type_elem = module.find('mcupdater:ModType', namespace)
            if mod_type_elem is None:
                mod_type_elem = module.find('ModType')
            if mod_type_elem is not None and mod_type_elem.text:
                mod_info.mod_type = mod_type_elem.text.strip()

            # Extract version from Meta if available
            meta_elem = module.find('mcupdater:Meta', namespace)
            if meta_elem is None:
                meta_elem = module.find('Meta')
            if meta_elem is not None:
                version_elem = meta_elem.find('mcupdater:version', namespace)
                if version_elem is None:
                    version_elem = meta_elem.find('version')
                if version_elem is not None and version_elem.text:
                    mod_info.current_version = version_elem.text.strip()

            # Add module attributes to mapper if available
            if self.mapper:
                self.mapper.add_module(mod_id, side, mod_info.required, source_file, mod_info.mod_type)

                # Use preserved attributes from mapper (including mod_type)
                preserved_attrs = self.mapper.get_attributes(mod_id)
                mod_info.mod_type = preserved_attrs['mod_type']
                mod_info.side = preserved_attrs['side']
                mod_info.required = preserved_attrs['required']

                # Log when using preserved removal status
                if preserved_attrs['mod_type'] == 'Removal' and preserved_attrs['source'] == 'preserved':
                    self.logger.info(f"Using preserved REMOVAL status for {mod_id} from higher-priority file")

            return mod_info

        except Exception as e:
            self.logger.error(f"Error parsing module {name}: {e}")
            return None
    
    def parse_directory(self, directory: str) -> Dict[str, ModInfo]:
        """Parse all XML files in a directory and merge mod information."""
        all_mods = {}

        # Get ignored directories from config
        ignored_dirs = {'.git', '.svn', '__pycache__'}  # Always ignore these
        if self.config:
            config_ignored = self.config.get('SCANNING', 'ignored_directories', '')
            if config_ignored:
                ignored_dirs.update(dir.strip() for dir in config_ignored.split(',') if dir.strip())
        else:
            # Default ignored directories if no config
            ignored_dirs.update(['test_output', 'output', 'generated', 'build', 'dist', 'temp', 'tmp'])

        for root, dirs, files in os.walk(directory):
            # Remove ignored directories from the search
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith('.')]

            for file in files:
                if file.endswith('.xml'):
                    file_path = os.path.join(root, file)
                    file_mods = self.parse_xml_file(file_path)

                    # Later files override earlier ones (import order)
                    all_mods.update(file_mods)

        self.mods = all_mods
        self.logger.info(f"Total unique mods found: {len(all_mods)}")
        return all_mods

class RateLimiter:
    """Simple rate limiter for API requests."""
    
    def __init__(self, requests_per_minute: int = DEFAULT_RATE_LIMIT):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.last_request_time = 0
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()

class ModrinthAPIClient:
    """Client for interacting with the Modrinth API v2."""

    def __init__(self, config: ModUpdateConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.base_url = MODRINTH_API_BASE
        self.rate_limiter = RateLimiter(config.getint('API', 'rate_limit_per_minute', DEFAULT_RATE_LIMIT))
        self.timeout = config.getint('API', 'request_timeout', DEFAULT_TIMEOUT)
        self.session = requests.Session()

        # Set user agent
        self.session.headers.update({
            'User-Agent': 'Gears-Frontiers-ModUpdater/1.0.0 (github.com/edwardg117/Gears-Frontiers)'
        })

        # Add API key if provided
        api_key = config.get('API', 'modrinth_api_key')
        if api_key:
            self.session.headers.update({'Authorization': api_key})

    def get_project_versions(self, project_id: str, minecraft_version: str = None, loader: str = None) -> List[Dict]:
        """Get all versions for a project."""
        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}/project/{project_id}/version"
        params = {}

        if minecraft_version:
            params['game_versions'] = f'["{minecraft_version}"]'
        if loader:
            params['loaders'] = f'["{loader}"]'

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to get versions for project {project_id}: {e}")
            return []

    def get_latest_version(self, project_id: str, minecraft_version: str = None, loader: str = None) -> Optional[Dict]:
        """Get the latest compatible version for a project."""
        versions = self.get_project_versions(project_id, minecraft_version, loader)
        return versions[0] if versions else None

    def get_project_info(self, project_id: str) -> Optional[Dict]:
        """Get project information."""
        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}/project/{project_id}"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to get project info for {project_id}: {e}")
            return None

class CurseForgeAPIClient:
    """Client for interacting with the CurseForge Core API."""

    def __init__(self, config: ModUpdateConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.base_url = CURSEFORGE_API_BASE
        self.rate_limiter = RateLimiter(config.getint('API', 'rate_limit_per_minute', DEFAULT_RATE_LIMIT))
        self.timeout = config.getint('API', 'request_timeout', DEFAULT_TIMEOUT)
        self.session = requests.Session()

        # API key is required for CurseForge
        api_key = config.get('API', 'curseforge_api_key')
        if not api_key:
            self.logger.warning("No CurseForge API key provided - CurseForge mods will be skipped")
            self.enabled = False
        else:
            self.session.headers.update({'x-api-key': api_key})
            self.enabled = True

    def get_mod_files(self, mod_id: int, minecraft_version: str = None, mod_loader: str = None) -> List[Dict]:
        """Get all files for a mod."""
        if not self.enabled:
            return []

        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}/mods/{mod_id}/files"
        params = {'gameId': MINECRAFT_GAME_ID}

        if minecraft_version:
            params['gameVersion'] = minecraft_version
        if mod_loader:
            params['modLoaderType'] = self._get_loader_id(mod_loader)

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except requests.RequestException as e:
            self.logger.error(f"Failed to get files for mod {mod_id}: {e}")
            return []

    def get_mod_info(self, mod_id: int) -> Optional[Dict]:
        """Get mod information."""
        if not self.enabled:
            return None

        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}/mods/{mod_id}"

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get('data')
        except requests.RequestException as e:
            self.logger.error(f"Failed to get mod info for {mod_id}: {e}")
            return None

    def _get_loader_id(self, loader: str) -> int:
        """Convert loader name to CurseForge loader ID."""
        loader_map = {
            'forge': 1,
            'fabric': 4,
            'quilt': 5,
            'neoforge': 6
        }
        return loader_map.get(loader.lower(), 0)

class UpdateChecker:
    """Main class for checking mod updates across platforms."""

    def __init__(self, config: ModUpdateConfig, logger: logging.Logger,
                 modrinth_client: ModrinthAPIClient, curseforge_client: CurseForgeAPIClient):
        self.config = config
        self.logger = logger
        self.modrinth_client = modrinth_client
        self.curseforge_client = curseforge_client
        self.minecraft_version = config.get('MODPACK', 'target_minecraft_version', '1.21.1')
        self.target_loader = config.get('MODPACK', 'target_loader', 'neoforge')

        # Parse excluded mods and pinned versions
        self.excluded_mods = set(
            mod.strip() for mod in config.get('MODPACK', 'excluded_mods', '').split(',') if mod.strip()
        )
        self.pinned_versions = {}
        pinned_str = config.get('MODPACK', 'pinned_versions', '')
        for pin in pinned_str.split(','):
            if ':' in pin:
                mod_id, version = pin.split(':', 1)
                self.pinned_versions[mod_id.strip()] = version.strip()

    def check_for_updates(self, mods: Dict[str, ModInfo]) -> List[Dict]:
        """Check for updates for all mods."""
        updates = []

        # Filter mods to check
        mods_to_check = {
            mod_id: mod for mod_id, mod in mods.items()
            if mod_id not in self.excluded_mods and mod.mod_type != 'Removal'
        }

        self.logger.info(f"Checking {len(mods_to_check)} mods for updates")

        # Use ThreadPoolExecutor for concurrent API requests
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all update check tasks
            future_to_mod = {
                executor.submit(self._check_mod_update, mod): mod
                for mod in mods_to_check.values()
            }

            # Process results with progress bar
            with tqdm(total=len(future_to_mod), desc="Checking for updates") as pbar:
                for future in as_completed(future_to_mod):
                    mod = future_to_mod[future]
                    try:
                        update_info = future.result()
                        if update_info:
                            updates.append(update_info)
                    except Exception as e:
                        self.logger.error(f"Error checking updates for {mod.name}: {e}")
                    finally:
                        pbar.update(1)

        # Sort updates by severity (major, minor, patch)
        updates.sort(key=lambda x: (x.get('severity_order', 999), x['name']))

        return updates

    def _check_mod_update(self, mod: ModInfo) -> Optional[Dict]:
        """Check for updates for a single mod."""
        try:
            # Skip if version is pinned
            if mod.mod_id in self.pinned_versions:
                self.logger.debug(f"Skipping {mod.name} - version pinned to {self.pinned_versions[mod.mod_id]}")
                return None

            if mod.platform == 'modrinth':
                return self._check_modrinth_update(mod)
            elif mod.platform == 'curseforge':
                return self._check_curseforge_update(mod)
            else:
                self.logger.warning(f"Unknown platform for mod {mod.name}: {mod.platform}")
                return None

        except Exception as e:
            self.logger.error(f"Error checking update for {mod.name}: {e}")
            return None

    def _check_modrinth_update(self, mod: ModInfo) -> Optional[Dict]:
        """Check for Modrinth mod updates."""
        if not mod.project_id:
            self.logger.warning(f"No project ID found for Modrinth mod {mod.name}")
            return None

        latest_version = self.modrinth_client.get_latest_version(
            mod.project_id, self.minecraft_version, self.target_loader
        )

        if not latest_version:
            self.logger.warning(f"No compatible version found for {mod.name}")
            return None

        # Compare versions
        current_version = mod.current_version or "unknown"
        latest_version_number = latest_version.get('version_number', 'unknown')

        if self._is_newer_version(current_version, latest_version_number, mod.version_id, latest_version.get('id')):
            return self._create_update_info(mod, latest_version, 'modrinth')

        return None

    def _check_curseforge_update(self, mod: ModInfo) -> Optional[Dict]:
        """Check for CurseForge mod updates."""
        # For CurseForge, we need to extract mod ID from file path or use search
        # This is more complex and would require additional API calls
        self.logger.debug(f"CurseForge update checking not fully implemented for {mod.name}")
        return None

    def _is_newer_version(self, current: str, latest: str, current_id: str = None, latest_id: str = None) -> bool:
        """Compare versions to determine if an update is available."""
        # First check by version ID if available
        if current_id and latest_id and current_id != latest_id:
            return True

        # Try semantic version comparison
        try:
            current_ver = version.parse(current)
            latest_ver = version.parse(latest)
            return latest_ver > current_ver
        except version.InvalidVersion:
            # Fall back to string comparison if version parsing fails
            return current != latest

    def _create_update_info(self, mod: ModInfo, latest_version: Dict, platform: str) -> Dict:
        """Create update information dictionary."""
        current_version = mod.current_version or "unknown"
        latest_version_number = latest_version.get('version_number', 'unknown')

        # Determine update severity
        severity = self._determine_update_severity(current_version, latest_version_number)

        # Get download information
        files = latest_version.get('files', [])
        primary_file = files[0] if files else {}

        update_info = {
            'name': mod.name,
            'mod_id': mod.mod_id,
            'platform': platform,
            'current_version': current_version,
            'latest_version': latest_version_number,
            'severity': severity,
            'severity_order': {'major': 1, 'minor': 2, 'patch': 3}.get(severity, 4),
            'download_url': primary_file.get('url', ''),
            'file_size': primary_file.get('size', 0),
            'file_hash': self._extract_hash(primary_file.get('hashes', {})),
            'release_date': latest_version.get('date_published', ''),
            'changelog': latest_version.get('changelog', ''),
            'dependencies': latest_version.get('dependencies', []),
            'source_file': mod.source_file,
            'minecraft_versions': latest_version.get('game_versions', []),
            'loaders': latest_version.get('loaders', [])
        }

        return update_info

    def _determine_update_severity(self, current: str, latest: str) -> str:
        """Determine the severity of an update (major, minor, patch)."""
        try:
            current_ver = version.parse(current)
            latest_ver = version.parse(latest)

            if latest_ver.major > current_ver.major:
                return 'major'
            elif latest_ver.minor > current_ver.minor:
                return 'minor'
            else:
                return 'patch'
        except version.InvalidVersion:
            return 'unknown'

    def _extract_hash(self, hashes: Dict) -> str:
        """Extract the best available hash from hash dictionary."""
        # Prefer SHA256, then SHA1, then MD5
        for hash_type in ['sha256', 'sha1', 'md5']:
            if hash_type in hashes:
                return hashes[hash_type]
        return ''

class OutputGenerator:
    """Generator for various output formats (XML, Markdown, logs)."""

    def __init__(self, config: ModUpdateConfig, logger: logging.Logger, mapper: ModuleAttributeMapper = None):
        self.config = config
        self.logger = logger
        self.mapper = mapper

    def generate_all_outputs(self, updates: List[Dict], all_mods: Dict[str, ModInfo],
                           output_dir: str, timestamp: str):
        """Generate all configured output files."""
        os.makedirs(output_dir, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")

        if self.config.getboolean('OUTPUT', 'generate_xml', True):
            xml_file = os.path.join(output_dir, f"updates-{date_str}.xml")
            self.generate_xml_update(updates, xml_file)

        if self.config.getboolean('OUTPUT', 'generate_changelog', True):
            changelog_file = os.path.join(output_dir, f"CHANGELOG-{date_str}.md")
            self.generate_changelog(updates, changelog_file)

        if self.config.getboolean('OUTPUT', 'generate_log', True):
            log_file = os.path.join(output_dir, f"update-log-{date_str}.txt")
            self.generate_execution_log(updates, all_mods, log_file, timestamp)

    def generate_xml_update(self, updates: List[Dict], output_file: str):
        """Generate XML update file compatible with MCUpdater schema."""
        try:
            # Create root element
            root = ET.Element('ServerPack')
            root.set('version', '4.1')
            root.set('xmlns', 'http://www.mcupdater.com')
            root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            root.set('xsi:schemaLocation', 'http://www.mcupdater.com http://files.mcupdater.com/ServerPackv2.xsd')

            # Create server element
            server = ET.SubElement(root, 'Server')
            server.set('id', f"update-{datetime.now().strftime('%Y%m%d')}")
            server.set('abstract', 'false')
            server.set('name', f"Update {datetime.now().strftime('%Y-%m-%d')}")
            server.set('newsUrl', 'about:blank')
            server.set('version', self.config.get('MODPACK', 'target_minecraft_version', '1.21.1'))
            server.set('generateList', 'true')
            server.set('autoConnect', 'false')
            server.set('revision', '')
            server.set('mainClass', 'cpw.mods.bootstraplauncher.BootstrapLauncher')
            server.set('launcherType', 'Vanilla')

            # Add modules for each update
            for update in updates:
                module = ET.SubElement(server, 'Module')
                module.set('name', update['name'])
                module.set('id', update['mod_id'])
                module.set('depends', '')  # TODO: Extract dependencies

                # Get preserved attributes or use defaults
                if self.mapper:
                    attrs = self.mapper.get_attributes(update['mod_id'])
                    module.set('side', attrs['side'])
                    if attrs['source'] == 'preserved':
                        self.logger.debug(f"Using preserved attributes for {update['mod_id']}: side={attrs['side']}, required={attrs['required']}")
                    else:
                        self.logger.debug(f"Using default attributes for {update['mod_id']}: side={attrs['side']}, required={attrs['required']}")
                else:
                    attrs = {'side': 'BOTH', 'required': True}
                    module.set('side', attrs['side'])
                    self.logger.debug(f"No mapper available, using hardcoded defaults for {update['mod_id']}")

                # URL
                url_elem = ET.SubElement(module, 'URL')
                url_elem.set('priority', '1')
                url_elem.text = update['download_url']

                # Size
                size_elem = ET.SubElement(module, 'Size')
                size_elem.text = str(update['file_size'])

                # Required
                required_elem = ET.SubElement(module, 'Required')
                required_elem.text = 'true' if attrs['required'] else 'false'

                # ModType
                mod_type_elem = ET.SubElement(module, 'ModType')
                mod_type_elem.text = 'Regular'

                # Hash
                if update['file_hash']:
                    hash_elem = ET.SubElement(module, 'MD5')
                    hash_elem.text = update['file_hash']

                # Meta information
                meta_elem = ET.SubElement(module, 'Meta')

                version_elem = ET.SubElement(meta_elem, 'version')
                version_elem.text = update['latest_version']

                if update['changelog']:
                    changelog_elem = ET.SubElement(meta_elem, 'changelog')
                    changelog_elem.text = update['changelog'][:500]  # Truncate if too long

            # Write XML file
            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ", level=0)
            tree.write(output_file, encoding='utf-8', xml_declaration=True)

            self.logger.info(f"Generated XML update file: {output_file}")

        except Exception as e:
            self.logger.error(f"Failed to generate XML update file: {e}")

    def generate_changelog(self, updates: List[Dict], output_file: str):
        """Generate markdown changelog documentation."""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# Modpack Update Changelog - {datetime.now().strftime('%Y-%m-%d')}\n\n")

                # Executive summary
                f.write("## Executive Summary\n\n")
                f.write(f"- **Total Updates**: {len(updates)}\n")

                # Count by severity
                severity_counts = {}
                for update in updates:
                    severity = update.get('severity', 'unknown')
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1

                for severity, count in severity_counts.items():
                    f.write(f"- **{severity.title()} Updates**: {count}\n")

                f.write(f"- **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                # Updates by severity
                for severity in ['major', 'minor', 'patch', 'unknown']:
                    severity_updates = [u for u in updates if u.get('severity') == severity]
                    if not severity_updates:
                        continue

                    f.write(f"## {severity.title()} Updates ({len(severity_updates)})\n\n")

                    for update in severity_updates:
                        f.write(f"### {update['name']}\n\n")
                        f.write(f"- **Current Version**: {update['current_version']}\n")
                        f.write(f"- **New Version**: {update['latest_version']}\n")
                        f.write(f"- **Platform**: {update['platform'].title()}\n")

                        if update['release_date']:
                            f.write(f"- **Release Date**: {update['release_date']}\n")

                        if update['changelog']:
                            f.write(f"- **Changelog**: {update['changelog'][:200]}...\n")

                        f.write("\n---\n\n")

                # Warnings and notes
                f.write("## Important Notes\n\n")
                f.write("- Always backup your world before applying updates\n")
                f.write("- Test updates in a separate instance first\n")
                f.write("- Check for mod compatibility issues\n")
                f.write("- Review dependency changes carefully\n\n")

            self.logger.info(f"Generated changelog: {output_file}")

        except Exception as e:
            self.logger.error(f"Failed to generate changelog: {e}")

    def generate_execution_log(self, updates: List[Dict], all_mods: Dict[str, ModInfo],
                             output_file: str, timestamp: str):
        """Generate detailed execution log."""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"Mod Update Automation Execution Log\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Session ID: {timestamp}\n")
                f.write("=" * 50 + "\n\n")

                # Summary statistics
                f.write("SUMMARY STATISTICS\n")
                f.write("-" * 20 + "\n")
                f.write(f"Total mods scanned: {len(all_mods)}\n")
                f.write(f"Updates found: {len(updates)}\n")
                f.write(f"Update rate: {len(updates)/len(all_mods)*100:.1f}%\n\n")

                # Platform breakdown
                platform_stats = {}
                for mod in all_mods.values():
                    platform_stats[mod.platform] = platform_stats.get(mod.platform, 0) + 1

                f.write("PLATFORM BREAKDOWN\n")
                f.write("-" * 20 + "\n")
                for platform, count in platform_stats.items():
                    f.write(f"{platform.title()}: {count} mods\n")
                f.write("\n")

                # Update details
                f.write("UPDATE DETAILS\n")
                f.write("-" * 20 + "\n")
                for update in updates:
                    f.write(f"Mod: {update['name']} ({update['mod_id']})\n")
                    f.write(f"  Platform: {update['platform']}\n")
                    f.write(f"  Version: {update['current_version']} -> {update['latest_version']}\n")
                    f.write(f"  Severity: {update['severity']}\n")
                    f.write(f"  File Size: {update['file_size']} bytes\n")
                    f.write(f"  Download URL: {update['download_url']}\n")
                    if update['file_hash']:
                        f.write(f"  File Hash: {update['file_hash']}\n")
                    f.write("\n")

            self.logger.info(f"Generated execution log: {output_file}")

        except Exception as e:
            self.logger.error(f"Failed to generate execution log: {e}")

def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> logging.Logger:
    """Set up logging configuration."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logger
    logger = logging.getLogger('mod_update_automation')
    logger.setLevel(log_level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def main():
    """Main entry point for the mod update automation script."""
    parser = argparse.ArgumentParser(
        description='Comprehensive mod update automation for Minecraft modpacks'
    )
    parser.add_argument(
        'directory',
        help='Directory containing MCUpdater XML files'
    )
    parser.add_argument(
        '--config', '-c',
        default=DEFAULT_CONFIG_FILE,
        help=f'Configuration file path (default: {DEFAULT_CONFIG_FILE})'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Preview updates without generating files'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output directory for generated files'
    )
    
    args = parser.parse_args()
    
    # Validate directory
    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory")
        sys.exit(1)
    
    # Load configuration
    config = ModUpdateConfig(args.config)
    
    # Set up logging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"mod_update_log_{timestamp}.txt" if not args.dry_run else None
    logger = setup_logging(args.verbose, log_file)
    
    logger.info("Starting mod update automation script")
    logger.info(f"Scanning directory: {args.directory}")
    logger.info(f"Configuration file: {args.config}")
    logger.info(f"Dry run mode: {args.dry_run}")

    # Initialize module attribute mapper
    mapper = ModuleAttributeMapper(logger)

    # Parse XML files with attribute mapping
    parser = XMLParser(logger, config, mapper)
    mods = parser.parse_directory(args.directory)

    # Log attribute mapping statistics
    stats = mapper.get_stats()
    logger.info(f"Attribute mapping completed: {stats['total_modules']} modules from {stats['files_processed']} files")
    if args.verbose:
        logger.info(f"Side distribution - CLIENT: {stats.get('CLIENT', 0)}, SERVER: {stats.get('SERVER', 0)}, BOTH: {stats.get('BOTH', 0)}")
        logger.info(f"Required distribution - true: {stats.get('true', 0)}, false: {stats.get('false', 0)}")
    
    if not mods:
        logger.error("No mods found in XML files")
        sys.exit(1)
    
    logger.info(f"Found {len(mods)} mods to check for updates")
    
    try:
        # Initialize API clients
        modrinth_client = ModrinthAPIClient(config, logger)
        curseforge_client = CurseForgeAPIClient(config, logger)

        # Check for updates
        update_checker = UpdateChecker(config, logger, modrinth_client, curseforge_client)
        updates = update_checker.check_for_updates(mods)

        if not updates:
            logger.info("No updates found")
            if args.dry_run:
                logger.info("Dry run completed - no updates available")
            return

        logger.info(f"Found {len(updates)} mods with available updates")

        if args.dry_run:
            # Display preview of updates
            logger.info("=== DRY RUN - PREVIEW OF AVAILABLE UPDATES ===")
            for update in updates:
                logger.info(f"UPDATE: {update['name']} ({update['current_version']} -> {update['latest_version']}) [{update['severity']}]")
            logger.info("=== END DRY RUN PREVIEW ===")
        else:
            # Generate output files
            output_dir = args.output or config.get('OUTPUT', 'output_directory', 'updates')
            generator = OutputGenerator(config, logger, mapper)
            generator.generate_all_outputs(updates, mods, output_dir, timestamp)
            logger.info(f"Output files generated in: {output_dir}")

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

    logger.info("Mod update automation completed")

if __name__ == "__main__":
    main()
