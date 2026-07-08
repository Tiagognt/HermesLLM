#!/usr/bin/env python3
"""
Shared cleaning function for the RoboMix DAPT pipeline.
Spec (confirmed): fully flatten every document to a single line.
- No markdown/rst heading markup (#, ==, ~~, .. directive lines, :field: lines)
- No raw newlines survive in the output string -- all whitespace runs
  (spaces, tabs, newlines) collapse to a single space
- Applies uniformly to prose AND code, per explicit instruction -- code
  loses indentation/executability as a result; that's the accepted tradeoff.
"""
import re

_HEADER_SYMBOL_LINE = re.compile(r'^[=\-~^"\'`#*+.]{3,}\s*$', re.M)
_MD_ATX_HEADER = re.compile(r'^#{1,6}\s*', re.M)
_RST_DIRECTIVE = re.compile(r'^\.\. [a-zA-Z_\-]+::.*$', re.M)
_RST_TARGET = re.compile(r'^\.\. _[^:]+:\s*$', re.M)          # .. _label: hyperlink targets
_RST_FIELD = re.compile(r'^\s*:[a-zA-Z_\-]+:.*$', re.M)
_RST_ROLE = re.compile(r':[a-zA-Z_\-]+:`([^`]*)`')            # :doc:`text <link>` -> text
_RST_ROLE_LINK = re.compile(r'([^<`]*)<[^>]*>')                # strip trailing <url> inside role text
_BACKTICKS = re.compile(r'`{1,2}([^`]*)`{1,2}')                # `code` / ``code`` -> code
_ANGLE_URL = re.compile(r'\s*<[^>]*>')                          # drop embedded <url> targets
_REF_SUFFIX = re.compile(r'(?<=\w)__?(?=\s|$)')                 # trailing _ / __ rst reference markers
_WHITESPACE_RUN = re.compile(r'\s+')

def clean_text(raw: str) -> str:
    text = raw
    text = _RST_DIRECTIVE.sub('', text)
    text = _RST_TARGET.sub('', text)
    text = _RST_FIELD.sub('', text)
    text = _RST_ROLE.sub(lambda m: _RST_ROLE_LINK.sub(r'\1', m.group(1)).strip(), text)
    text = _BACKTICKS.sub(r'\1', text)
    text = _ANGLE_URL.sub('', text)
    text = _REF_SUFFIX.sub('', text)
    text = _HEADER_SYMBOL_LINE.sub('', text)
    text = _MD_ATX_HEADER.sub('', text)
    text = _WHITESPACE_RUN.sub(' ', text)  # this is what collapses newlines -> single space
    return text.strip()

if __name__ == "__main__":
    sample = """# Installation
Options for installing ROS 2 Humble:

.. toctree::
   :hidden:

   Installation/Ubuntu-Install-Debs

Some real content here
spanning multiple lines.
"""
    print(repr(clean_text(sample)))
