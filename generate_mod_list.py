#!/usr/bin/env python3
"""
Script to generate a mod list in markdown format from Minecraft modpack XML files.
"""

import argparse
import os
import re
import html

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
            'source_file': file_path
        }
        
        # Try to extract description and authors from Meta if available
        desc_match = re.search(r'<Meta>.*?<description>([^<]*)</description>.*?</Meta>', 
                              content[content.find(f'id="{mod_id}"'):content.find(f'</Module>', content.find(f'id="{mod_id}"'))], 
                              re.DOTALL)
        if desc_match:
            result[mod_id]['description'] = desc_match.group(1)
        
        authors_match = re.search(r'<Meta>.*?<authors>([^<]*)</authors>.*?</Meta>', 
                                 content[content.find(f'id="{mod_id}"'):content.find(f'</Module>', content.find(f'id="{mod_id}"'))], 
                                 re.DOTALL)
        if authors_match:
            result[mod_id]['authors'] = authors_match.group(1)
    
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

def generate_markdown(modules, output_file):
    """Generate a markdown file with the mod list."""
    # Sort modules by name (case-insensitive)
    sorted_modules = sorted(modules.values(), key=lambda m: m['name'].lower())
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Minecraft Modpack - Mod List\n\n")
        
        for module in sorted_modules:
            mod_name = module['name']
            
            f.write(f'## {mod_name}\n\n')
            
            if 'authors' in module:
                f.write(f'**Authors:** {module["authors"]}\n\n')
            
            if 'description' in module:
                f.write(f'{module["description"]}\n\n')
            
            f.write('---\n\n')
    
    print(f"Markdown mod list generated at: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Generate a mod list in markdown format from Minecraft modpack XML files.')
    parser.add_argument('directory', help='Directory containing XML files')
    parser.add_argument('-o', '--output', default='mod_list.md', help='Output markdown file (default: mod_list.md)')
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"Error: {args.directory} is not a valid directory")
        return
    
    print(f"Scanning XML files in {args.directory}...")
    modules = get_all_modules(args.directory)
    print(f"Found {len(modules)} unique modules")
    
    generate_markdown(modules, args.output)

if __name__ == "__main__":
    main()


