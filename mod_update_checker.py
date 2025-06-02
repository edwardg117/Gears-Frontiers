#!/usr/bin/env python3
"""
Script to check for updates to mods in a Minecraft modpack.
Scans XML files used by MCUpdater and checks if newer versions are available on Modrinth.
"""

import argparse
import os
import re
import requests
import json
from packaging import version
from urllib.parse import urlparse, parse_qs

def extract_modules_from_xml(file_path):
    """Extract module information from an XML file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Find all Module elements
    module_pattern = r'<Module\s+name="([^"]*)"\s+id="([^"]*)".*?<URL[^>]*>([^<]*)</URL>.*?</Module>'
    modules = re.findall(module_pattern, content, re.DOTALL)
    
    result = {}
    for name, mod_id, url in modules:
        result[mod_id] = {
            'name': name,
            'id': mod_id,
            'url': url,
            'source_file': file_path
        }
        
        # Try to extract version from Meta if available
        version_match = re.search(r'<Meta>.*?<version>([^<]*)</version>.*?</Meta>', 
                                 content[content.find(f'id="{mod_id}"'):content.find(f'</Module>', content.find(f'id="{mod_id}"'))], 
                                 re.DOTALL)
        if version_match:
            result[mod_id]['version'] = version_match.group(1)
        
        # Extract Modrinth project ID and version ID from URL if possible
        if 'modrinth.com/data/' in url:
            parts = url.split('/')
            if len(parts) >= 6:
                result[mod_id]['modrinth_id'] = parts[-3]
                result[mod_id]['modrinth_version_id'] = parts[-2]
    
    return result

def get_all_modules(directory):
    """Get all modules from XML files in the directory, with later occurrences overriding earlier ones."""
    all_modules = {}
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.xml'):
                file_path = os.path.join(root, file)
                modules = extract_modules_from_xml(file_path)
                all_modules.update(modules)  # Later modules override earlier ones
    
    return all_modules

def check_for_updates(modules):
    """Check for updates for each module."""
    updates_available = []
    
    for mod_id, module in modules.items():
        if 'modrinth_id' in module:
            try:
                # Get latest version for the same game version
                response = requests.get(f"https://api.modrinth.com/v2/project/{module['modrinth_id']}/version")
                if response.status_code == 200:
                    versions = response.json()
                    
                    # Extract game version from current URL if possible
                    current_game_version = None
                    if 'mc1.21' in module['url']:
                        current_game_version = '1.21'
                    elif 'mc1.20' in module['url']:
                        current_game_version = '1.20'
                    
                    # Filter versions for the same game version
                    compatible_versions = []
                    for ver in versions:
                        if current_game_version and any(gv.startswith(current_game_version) for gv in ver.get('game_versions', [])):
                            compatible_versions.append(ver)
                    
                    if compatible_versions:
                        latest_version = compatible_versions[0]  # Modrinth returns versions in descending order
                        
                        # Compare with current version
                        if 'version' in module and module.get('modrinth_version_id') != latest_version.get('id'):
                            try:
                                current_ver = version.parse(module['version'])
                                latest_ver = version.parse(latest_version['version_number'])
                                
                                if latest_ver > current_ver:
                                    updates_available.append({
                                        'name': module['name'],
                                        'id': mod_id,
                                        'current_version': module.get('version', 'Unknown'),
                                        'latest_version': latest_version['version_number'],
                                        'download_url': latest_version['files'][0]['url'],
                                        'source_file': module['source_file']
                                    })
                            except:
                                # If version parsing fails, compare by version ID
                                if module.get('modrinth_version_id') != latest_version.get('id'):
                                    updates_available.append({
                                        'name': module['name'],
                                        'id': mod_id,
                                        'current_version': module.get('version', 'Unknown'),
                                        'latest_version': latest_version['version_number'],
                                        'download_url': latest_version['files'][0]['url'],
                                        'source_file': module['source_file']
                                    })
            except Exception as e:
                print(f"Error checking updates for {module['name']}: {str(e)}")
    
    return updates_available

def main():
    parser = argparse.ArgumentParser(description='Check for mod updates in a Minecraft modpack.')
    parser.add_argument('directory', help='Directory containing XML files')
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory")
        return
    
    print(f"Scanning XML files in {args.directory}...")
    modules = get_all_modules(args.directory)
    print(f"Found {len(modules)} unique modules")
    
    print("Checking for updates...")
    updates = check_for_updates(modules)
    
    if updates:
        print(f"\nFound {len(updates)} modules with updates available:")
        for update in updates:
            print(f"\n{update['name']} ({update['id']})")
            print(f"  Current version: {update['current_version']}")
            print(f"  Latest version: {update['latest_version']}")
            print(f"  Download URL: {update['download_url']}")
            print(f"  Source file: {update['source_file']}")
    else:
        print("\nAll modules are up to date!")

if __name__ == "__main__":
    main()