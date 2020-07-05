#!/usr/bin/env python3

"""
Generate src/bin/termptydbl.{c,h} from unicode files
used with ucd.all.flat.xml from
https://www.unicode.org/Public/UCD/latest/ucdxml/ucd.all.flat.zip
"""

import argparse
from collections import namedtuple
import xml.etree.ElementTree as ET

Range = namedtuple('range', ['width', 'start', 'end'])

def get_ranges(xmlfile, emoji_as_wide):
    tree = ET.parse(xmlfile)
    root = tree.getroot()
    repertoire = root.find("{http://www.unicode.org/ns/2003/ucd/1.0}repertoire")
    chars = repertoire.findall("{http://www.unicode.org/ns/2003/ucd/1.0}char")

    ranges = []
    range = Range('N', 0, 0)
    for c in chars:
        ea = c.get('ea')
        if ea in ('Na', 'H'):
            ea = 'N'
        if ea in ('F'):
            ea = 'W'
        assert ea in ('N', 'A', 'W')
        cp = c.get('cp')
        if not cp:
            continue
        if emoji_as_wide:
            emoji = c.get('ExtPict')
            if emoji == 'Y':
                ea = 'W'

        cp = int(cp, 16)
        if ea != range[0]:
            ranges.append(range)
            range = Range(ea, cp, cp)
        else:
            range = range._replace(end=cp)

    ranges.append(range)

    return ranges

def merge_ranges(ranges, is_same_width):
    res = []
    range = ranges[0]
    for r in ranges:
        if is_same_width(r, range):
            range = range._replace(end=r.end)
        else:
            res.append(range)
            range = r
    res.append(range)
    return res

def skip_ranges(ranges, width_skipped):
    res = []
    for r in ranges:
        if r.width not in width_skipped:
            res.append(r)
    return res

def gen_header(range, file_header):
    file_header.write(
"""/* XXX: Code generated by tool unicode_dbl_width.py */
#ifndef _TERMPTY_DBL_H__
#define _TERMPTY_DBL_H__ 1

Eina_Bool _termpty_is_wide(const Eina_Unicode g);
Eina_Bool _termpty_is_ambigous_wide(const Eina_Unicode g);

static inline Eina_Bool
_termpty_is_dblwidth_get(const Termpty *ty, const Eina_Unicode g)
{
   /* optimize for latin1 non-ambiguous */
""")
    file_header.write(f"   if (g <= 0x{range.end:X})")
    file_header.write(
"""
     return EINA_FALSE;
   if (!ty->termstate.cjk_ambiguous_wide)
     return _termpty_is_wide(g);
   else
     return _termpty_is_ambigous_wide(g);
}

#endif
""")

def gen_ambigous(ranges, file_source):
    file_source.write(
"""
__attribute__((const))
Eina_Bool
_termpty_is_ambigous_wide(Eina_Unicode g)
{
    switch (g)
      {
""")
    def is_same_width(r1, r2):
        if r1.width == 'N':
            return r2.width == 'N'
        else:
            return r2.width in ('A', 'W')
    ranges = merge_ranges(ranges[1:], is_same_width)
    ranges = skip_ranges(ranges, ('N',))

    fallthrough = " EINA_FALLTHROUGH;"
    for idx, r in enumerate(ranges):
        if r.width == 'N':
            continue;
        if idx == len(ranges) -1:
            fallthrough = ""
        if r.start == r.end:
            file_source.write(f"       case 0x{r.start:X}:{fallthrough}\n")
        else:
            file_source.write(f"       case 0x{r.start:X} ... 0x{r.end:X}:{fallthrough}\n")

    file_source.write(
"""
        return EINA_TRUE;
    }
   return EINA_FALSE;
}
""")

def gen_wide(ranges, file_source):
    file_source.write(
"""
__attribute__((const))
Eina_Bool
_termpty_is_wide(Eina_Unicode g)
{
    switch (g)
      {
""")
    def is_same_width(r1, r2):
        if r1.width in ('N', 'A'):
            return r2.width in ('N', 'A')
        else:
            return r2.width == 'W'
    ranges = merge_ranges(ranges[1:], is_same_width)
    ranges = skip_ranges(ranges, ('N', 'A'))
    fallthrough = " EINA_FALLTHROUGH;"
    for idx, r in enumerate(ranges):
        if r.width in ('N', 'A'):
            continue;
        if idx == len(ranges) -1:
            fallthrough = ""
        if r.start == r.end:
            file_source.write(f"       case 0x{r.start:X}:{fallthrough}\n")
        else:
            file_source.write(f"       case 0x{r.start:X} ... 0x{r.end:X}:{fallthrough}\n")

    file_source.write(
"""
        return EINA_TRUE;
    }
   return EINA_FALSE;
}
""")


def gen_c(ranges, file_header, file_source):
    gen_header(ranges[0], file_header)
    file_source.write(
"""/* XXX: Code generated by tool unicode_dbl_width.py */
#include "private.h"

#include <Elementary.h>
#include "termpty.h"
#include "termptydbl.h"
""")
    gen_ambigous(ranges, file_source)
    gen_wide(ranges, file_source)

parser = argparse.ArgumentParser(description='Generate code handling different widths of unicode codepoints.')
parser.add_argument('xml', type=argparse.FileType('r'))
parser.add_argument('header', type=argparse.FileType('w'))
parser.add_argument('source', type=argparse.FileType('w'))

args = parser.parse_args()

ranges = get_ranges(args.xml, True)
gen_c(ranges, args.header, args.source)
