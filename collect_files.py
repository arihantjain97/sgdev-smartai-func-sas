#!/usr/bin/env python3
"""
Script to recursively collect all files from a directory and output them
in a structured text format with tree hierarchy and file contents.
Respects .gitignore patterns.
"""

import os
import argparse
import fnmatch
from pathlib import Path

# Try to import pathspec for better gitignore support, fallback to fnmatch if not available
try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False


def load_gitignore_patterns(root_dir):
    """Load and parse .gitignore patterns from root directory."""
    gitignore_path = Path(root_dir) / ".gitignore"
    patterns = []
    
    if gitignore_path.exists():
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                patterns.append(line)
    
    if not patterns:
        return None
    
    if HAS_PATHSPEC:
        # Use pathspec for proper gitignore pattern matching
        spec = pathspec.PathSpec.from_lines('gitwildmatch', patterns)
        def check_path(rel_path_str):
            # pathspec expects forward slashes
            normalized = rel_path_str.replace('\\', '/')
            return spec.match_file(normalized)
        return check_path
    else:
        # Fallback to fnmatch-based matching
        def should_ignore(rel_path_str):
            # Normalize path separators
            rel_path = rel_path_str.replace('\\', '/')
            # Check each pattern
            for pattern in patterns:
                # Handle directory patterns (ending with /)
                if pattern.endswith('/'):
                    pattern = pattern[:-1]
                    if fnmatch.fnmatch(rel_path, pattern) or rel_path.startswith(pattern + '/'):
                        return True
                # Handle patterns starting with / (root-relative)
                elif pattern.startswith('/'):
                    pattern = pattern[1:]
                    if fnmatch.fnmatch(rel_path, pattern) or rel_path.startswith(pattern + '/'):
                        return True
                # Regular pattern matching - check if pattern matches any part of the path
                else:
                    # Check if pattern matches the path or any parent directory
                    parts = rel_path.split('/')
                    for i in range(len(parts)):
                        subpath = '/'.join(parts[i:])
                        if fnmatch.fnmatch(subpath, pattern) or subpath.startswith(pattern + '/'):
                            return True
            return False
        return should_ignore


def generate_tree(directory, gitignore_check=None):
    """Generate a tree-like structure of the directory, respecting gitignore."""
    tree_lines = []
    root_dir = Path(directory).resolve()
    
    def build_tree(path, prefix="", is_last=True):
        path = Path(path)
        rel_path = path.relative_to(root_dir)
        
        # Check if path should be ignored
        if gitignore_check and gitignore_check(str(rel_path)):
            return
        
        if path.is_file():
            tree_lines.append(f"{prefix}{'└── ' if is_last else '├── '}{path.name}")
        elif path.is_dir():
            tree_lines.append(f"{prefix}{'└── ' if is_last else '├── '}{path.name}/")
            
            try:
                children = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
                # Always exclude .git directories
                children = [c for c in children if c.name != '.git']
                # Filter out ignored children
                if gitignore_check:
                    children = [c for c in children if not gitignore_check(str(c.relative_to(root_dir)))]
                
                for i, child in enumerate(children):
                    is_last_child = i == len(children) - 1
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    build_tree(child, child_prefix, is_last_child)
            except PermissionError:
                tree_lines.append(f"{prefix}    [Permission Denied]")
    
    build_tree(root_dir)
    return tree_lines


def collect_files(directory, output_file):
    """
    Recursively collect all files from directory and write to output file.
    Respects .gitignore patterns.
    
    Args:
        directory (str): Source directory to collect files from
        output_file (str): Output file path
    """
    source_dir = Path(directory).resolve()
    output_path = Path(output_file).resolve()
    
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory '{directory}' does not exist")
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load gitignore patterns
    gitignore_check = load_gitignore_patterns(source_dir)
    if gitignore_check:
        print("Loaded .gitignore patterns")
    else:
        print("No .gitignore found or no patterns loaded")
    
    # Get all files recursively, filtering by gitignore
    all_files = []
    for root, dirs, files in os.walk(source_dir):
        # Always exclude .git directories (not useful source code, can be very large)
        dirs[:] = [d for d in dirs if d != '.git']
        
        # Filter out ignored directories before descending
        if gitignore_check:
            dirs[:] = [d for d in dirs if not gitignore_check(str(Path(root).relative_to(source_dir) / d))]
        
        for file in files:
            file_path = Path(root) / file
            rel_path = file_path.relative_to(source_dir)
            
            # Skip if file matches gitignore pattern
            if gitignore_check and gitignore_check(str(rel_path)):
                continue
            
            all_files.append(file_path)
    
    # Sort files for consistent ordering
    all_files.sort(key=lambda x: str(x).lower())
    
    print(f"Found {len(all_files)} files in '{source_dir}' (after gitignore filtering)")
    print(f"Writing to '{output_path}'")
    
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # Write tree hierarchy
        outfile.write("Directory Structure:\n")
        outfile.write("=" * 50 + "\n")
        tree_lines = generate_tree(source_dir, gitignore_check)
        for line in tree_lines:
            outfile.write(line + "\n")
        outfile.write("\n")
        
        # Write file contents
        for file_path in all_files:
            try:
                # Calculate relative path from source directory
                rel_path = file_path.relative_to(source_dir)
                
                # Write file header
                outfile.write(f"File: {rel_path}\n")
                outfile.write(f"[{file_path.name}: start]\n")
                
                # Read and write file content
                try:
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(content)
                        
                        # Ensure content ends with newline if it doesn't already
                        if content and not content.endswith('\n'):
                            outfile.write('\n')
                            
                except UnicodeDecodeError:
                    # Handle binary files
                    outfile.write(f"[Binary file - {file_path.stat().st_size} bytes]\n")
                except Exception as e:
                    outfile.write(f"[Error reading file: {str(e)}]\n")
                
                # Write file footer
                outfile.write(f"[{file_path.name}: end]\n")
                outfile.write("\n")
                
            except Exception as e:
                outfile.write(f"Error processing {file_path}: {str(e)}\n")
                outfile.write(f"[{file_path.name}: end]\n")
                outfile.write("\n")
    
    print(f"Successfully wrote {len(all_files)} files to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(
        description="Recursively collect all files from a directory and output them in a structured format"
    )
    parser.add_argument(
        "source_dir", 
        help="Source directory to collect files from (directory A)"
    )
    parser.add_argument(
        "output_file", 
        help="Output file path"
    )
    
    args = parser.parse_args()
    
    try:
        collect_files(args.source_dir, args.output_file)
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
