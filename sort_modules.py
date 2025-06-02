#!/usr/bin/env python3
"""
Script to sort <Module> elements in XML files alphabetically by their name attribute.
Particularly useful for Minecraft modpack XML files like those used by MCUpdater.
"""

import argparse
import os
import re

def sort_modules(input_file, output_file=None, backup=True):
    """
    Sort <Module> elements in an XML file alphabetically by their name attribute.
    
    Args:
        input_file (str): Path to the input XML file
        output_file (str, optional): Path to the output XML file. If None, overwrites the input file.
        backup (bool): Whether to create a backup of the input file before overwriting
    """
    # Read the original file content
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Create backup if requested and we're overwriting the input file
    if backup and (output_file is None or output_file == input_file):
        backup_file = f"{input_file}.bak"
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Backup created at {backup_file}")
    
    # Extract XML declaration
    xml_decl = ""
    xml_decl_match = re.match(r'(<\?xml[^>]+\?>)', content)
    if xml_decl_match:
        xml_decl = xml_decl_match.group(1) + "\n"
        content = content[len(xml_decl_match.group(1)):].lstrip()
    
    # Find the content between ServerPack opening and closing tags
    serverpack_match = re.search(r'(<ServerPack[^>]*>)(.*?)(</ServerPack>)', content, re.DOTALL)
    if not serverpack_match:
        raise ValueError("No <ServerPack> tag found in the XML file")
    
    serverpack_start = serverpack_match.group(1)
    serverpack_content = serverpack_match.group(2)
    serverpack_end = serverpack_match.group(3)
    
    # Find the Server tag
    server_match = re.search(r'(<Server[^>]*>)(.*?)(</Server>)', serverpack_content, re.DOTALL)
    if not server_match:
        raise ValueError("No <Server> tag found in the XML file")
    
    server_start = server_match.group(1)
    server_content = server_match.group(2)
    server_end = server_match.group(3)
    
    # Extract all Module blocks
    module_pattern = r'(\s*<Module[^>]*name="([^"]*)".*?</Module>\s*)'
    modules = re.findall(module_pattern, server_content, re.DOTALL)
    
    if not modules:
        print("No <Module> elements found in the XML file")
        return
    
    # Sort modules by name attribute (case-insensitive)
    sorted_modules = sorted(modules, key=lambda m: m[1].lower())
    
    # Replace the server content with sorted modules
    sorted_server_content = ''.join(module[0] for module in sorted_modules)
    
    # Reconstruct the Server tag
    sorted_server = server_start + sorted_server_content + server_end
    
    # Replace the Server tag in the ServerPack content
    sorted_serverpack_content = serverpack_content.replace(server_match.group(0), sorted_server)
    
    # Reconstruct the XML
    sorted_content = serverpack_start + sorted_serverpack_content + serverpack_end
    
    # Write the sorted XML to the output file
    output = output_file if output_file else input_file
    with open(output, 'w', encoding='utf-8') as f:
        f.write(xml_decl + sorted_content)
    
    print(f"Modules sorted alphabetically in {output}")

def main():
    parser = argparse.ArgumentParser(description='Sort <Module> elements in XML files alphabetically by name.')
    parser.add_argument('input_file', help='Path to the input XML file')
    parser.add_argument('-o', '--output', help='Path to the output XML file (default: overwrite input)')
    parser.add_argument('--no-backup', action='store_true', help='Do not create a backup of the input file')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' does not exist.")
        return 1
    
    try:
        sort_modules(args.input_file, args.output, not args.no_backup)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())





