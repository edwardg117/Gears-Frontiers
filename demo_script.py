#!/usr/bin/env python3
"""
Demonstration script for the Mod Update Automation tool
Shows various usage examples and features
"""

import os
import subprocess
import sys
from datetime import datetime

def run_command(cmd, description):
    """Run a command and display the results."""
    print(f"\n{'='*60}")
    print(f"DEMO: {description}")
    print(f"Command: {cmd}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        print(f"Return code: {result.returncode}")
    except subprocess.TimeoutExpired:
        print("Command timed out after 120 seconds")
    except Exception as e:
        print(f"Error running command: {e}")

def main():
    """Run demonstration of mod update automation features."""
    print("Mod Update Automation Tool - Feature Demonstration")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if script exists
    if not os.path.exists("mod_update_automation.py"):
        print("ERROR: mod_update_automation.py not found!")
        sys.exit(1)
    
    # Demo 1: Show help
    run_command(
        "python mod_update_automation.py --help",
        "Display help and available options"
    )
    
    # Demo 2: Dry run with verbose output (limited)
    run_command(
        "python mod_update_automation.py . --dry-run --verbose | head -30",
        "Dry run with verbose output (first 30 lines)"
    )
    
    # Demo 3: Show configuration file
    if os.path.exists("mod_update_config.ini"):
        print(f"\n{'='*60}")
        print("DEMO: Current configuration file")
        print(f"{'='*60}")
        with open("mod_update_config.ini", "r") as f:
            print(f.read())
    
    # Demo 4: Generate actual output files
    output_dir = f"demo_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_command(
        f"python mod_update_automation.py . --output {output_dir}",
        f"Generate output files in {output_dir}"
    )
    
    # Demo 5: Show generated files
    if os.path.exists(output_dir):
        print(f"\n{'='*60}")
        print(f"DEMO: Generated files in {output_dir}")
        print(f"{'='*60}")
        
        for file in os.listdir(output_dir):
            file_path = os.path.join(output_dir, file)
            file_size = os.path.getsize(file_path)
            print(f"- {file} ({file_size:,} bytes)")
        
        # Show sample of changelog
        changelog_files = [f for f in os.listdir(output_dir) if f.startswith("CHANGELOG")]
        if changelog_files:
            changelog_path = os.path.join(output_dir, changelog_files[0])
            print(f"\nSample from {changelog_files[0]} (first 20 lines):")
            print("-" * 40)
            with open(changelog_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    print(line.rstrip())
    
    print(f"\n{'='*60}")
    print("DEMONSTRATION COMPLETED")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
