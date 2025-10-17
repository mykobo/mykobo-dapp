#!/usr/bin/env python3
"""
Merge generated CSS from wallet-connect build into main.css

This script:
1. Parses the minified generated CSS file
2. Extracts CSS rules (selectors and their properties)
3. Merges with existing main.css:
   - Replaces rules with matching selectors
   - Appends new rules that don't exist in main.css
4. Maintains the expanded (non-minified) format of main.css
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def parse_minified_css(css_content: str) -> Dict[str, str]:
    """
    Parse minified CSS and extract rules.

    Returns a dictionary mapping selectors to their full rule bodies.
    """
    rules = {}

    # Match CSS rules: selector { properties }
    # This regex handles multiple selectors separated by commas
    pattern = r'([^{}]+)\{([^{}]+)\}'

    for match in re.finditer(pattern, css_content):
        selector = match.group(1).strip()
        properties = match.group(2).strip()

        # Split multiple selectors (e.g., ".class1, .class2")
        selectors = [s.strip() for s in selector.split(',')]

        for sel in selectors:
            rules[sel] = properties

    return rules


def parse_expanded_css(css_content: str) -> List[Tuple[str, str, str]]:
    """
    Parse expanded CSS and extract rules with their original formatting.

    Returns a list of tuples: (selector, properties_block, full_rule)
    """
    rules = []

    # Match CSS rules with their full formatting
    pattern = r'([^{}]+)\{([^{}]+)\}'

    for match in re.finditer(pattern, css_content, re.DOTALL):
        selector = match.group(1).strip()
        properties_block = match.group(2)
        full_rule = match.group(0)

        # Handle multiple selectors
        selectors = [s.strip() for s in selector.split(',')]

        for sel in selectors:
            rules.append((sel, properties_block, full_rule))

    return rules


def format_css_rule(selector: str, properties: str) -> str:
    """
    Format a CSS rule from minified properties to expanded format.
    """
    # Split properties by semicolon
    props = [p.strip() for p in properties.split(';') if p.strip()]

    # Format with indentation
    formatted_props = '\n'.join(f'    {prop};' for prop in props)

    return f'{selector} {{\n{formatted_props}\n}}'


def merge_css(main_css_path: Path, generated_css_path: Path) -> str:
    """
    Merge generated CSS into main.css.

    - Replaces matching selectors
    - Appends new selectors
    - Preserves main.css formatting
    """
    # Read files
    main_css = main_css_path.read_text()
    generated_css = generated_css_path.read_text()

    # Parse CSS files
    generated_rules = parse_minified_css(generated_css)
    main_rules = parse_expanded_css(main_css)

    # Track which selectors we've seen in main.css
    main_selectors = set()
    updated_selectors = set()
    result_parts = []

    # Process main.css rules
    for selector, properties_block, full_rule in main_rules:
        main_selectors.add(selector)

        if selector in generated_rules:
            # Replace with generated version
            new_rule = format_css_rule(selector, generated_rules[selector])
            result_parts.append(new_rule)
            updated_selectors.add(selector)
        else:
            # Keep original
            result_parts.append(full_rule)

    # Append new rules from generated CSS that don't exist in main.css
    new_rules = []
    for selector, properties in generated_rules.items():
        if selector not in main_selectors:
            new_rule = format_css_rule(selector, properties)
            new_rules.append(new_rule)

    # Combine results
    result = '\n\n'.join(result_parts)

    if new_rules:
        result += '\n\n/* New rules from generated CSS */\n\n'
        result += '\n\n'.join(new_rules)

    return result


def main():
    if len(sys.argv) < 3:
        print("Usage: python merge-css.py <generated-css-file> <main-css-file>")
        print("Example: python merge-css.py app/static/css/index-B-_mI3yP.css app/static/css/main.css")
        sys.exit(1)

    generated_css_path = Path(sys.argv[1])
    main_css_path = Path(sys.argv[2])

    if not generated_css_path.exists():
        print(f"Error: Generated CSS file not found: {generated_css_path}")
        sys.exit(1)

    if not main_css_path.exists():
        print(f"Error: Main CSS file not found: {main_css_path}")
        sys.exit(1)

    # Backup main.css
    backup_path = main_css_path.with_suffix('.css.backup')
    backup_path.write_text(main_css_path.read_text())
    print(f"Created backup: {backup_path}")

    # Merge CSS
    merged_css = merge_css(main_css_path, generated_css_path)

    # Write result
    main_css_path.write_text(merged_css)
    print(f"Successfully merged CSS into {main_css_path}")
    print(f"Updated {len(merged_css.splitlines())} lines")


if __name__ == '__main__':
    main()
