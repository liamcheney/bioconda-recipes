#!/usr/bin/env python
import os
import re
from textwrap import dedent
import tarfile
from conda.fetch import download

# e.g., "========   addCols   ===================================="
re_header = re.compile(r'^=+\s+(?P<program>\w+)\s+=+$')

# e.g.,# "addCols - Sum columns in a text file."
re_summary = re.compile(r'^(?P<program>\w.*?) - (?P<description>.*)$')


def parse_footer(fn):
    """
    Parse the downloaded FOOTER file, which contains a header for each program
    and (usually) a description line.

    Yields either a nested 2-tuple of (header-program-name,
    (description-program-name, description-text)) if a description can be
    found, or a 1-tuple of (header-program-name,) if no description found.
    """
    block = []
    f = open(fn)
    while True:
        line = f.readline()
        if not line:
            break
        m1 = re_header.match(line)
        if m1:
            if block:
                yield block
                block = []
            name = m1.groups()[0]
            block.append(name)
            continue
        m = re_summary.match(line)
        if m:
            if not block:
                continue
            block.append(m.groups())
            yield block
            block = []
    if block:
        yield block


# This is the version of the last available tarball visible on
# http://hgdownload.cse.ucsc.edu/admin/exe/
VERSION = "324"

# Download tarball if it doesn't exist. Always download FOOTER.
tarball = (
    'http://hgdownload.cse.ucsc.edu/admin/exe/userApps.v{0}.src.tgz'
    .format(VERSION))
if not os.path.exists(os.path.basename(tarball)):
    download(tarball, os.path.basename(tarball))
download(
    'http://hgdownload.cse.ucsc.edu/admin/exe/linux.x86_64/FOOTER',
    'FOOTER')

# Different programs are built under different subdirectories in the source. So
# get a directory listing of the tarball
t = tarfile.open(os.path.basename(tarball))
names = [i for i in t.getnames()
         if i.startswith('./userApps/kent/src')]


def program_subdir(program, names):
    """
    Identify the source directory for a program.
    """
    hits = [i for i in names if program in i and t.getmember(i).isdir()]
    if len(hits) == 0:
        return
    top = sorted(hits)[0]

    return top.replace('./userApps/', '')


meta_template = open('template-meta.yaml').read()
build_template = open('template-build.sh').read()
test_template = open('template-run_test.sh').read()

# relative to where this file lives
recipes_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'recipes')

# Mismatches between what is parsed from FOOTER and where a program lives in
# the source
problematic = {
    'LiftSpec': 'liftSpec',
}

# Mismatches between the header and the summary; keys are the program name in
# the header and values are the dir in the source code.
resolve_header_and_summary_conflicts = {
    'rmFaDups': 'rmFaDups',
}

# Programs whose descriptions do not meet the regex and therefore must be
# manually assigned.
manual_descriptions = {

    'estOrient': dedent(
        """
        Read ESTs from a database and determine orientation based on
        estOrientInfo table or direction in gbCdnaInfo table.  Update
        PSLs so that the strand reflects the direction of transcription.
        By default, PSLs where the direction can't be determined are dropped.
        """),

    'fetchChromSizes': dedent(
        """
        used to fetch chrom.sizes information from UCSC for the given <db>
        """),

    'overlapSelect': dedent(
        """
        Select records based on overlapping chromosome ranges.  The ranges are
        specified in the selectFile, with each block specifying a range.
        Records are copied from the inFile to outFile based on the selection
        criteria.  Selection is based on blocks or exons rather than entire
        range.
        """),

    'pslCDnaFilter': dedent(
        """
        Filter cDNA alignments in psl format.  Filtering criteria are
        comparative, selecting near best in genome alignments for each given
        cDNA and non-comparative, based only on the quality of an individual
        alignment.
        """),

    'pslHisto': dedent(
        """
        Collect counts on PSL alignments for making histograms. These then be
        analyzed with R, textHistogram, etc.
        """),

    'pslSwap': dedent(
        """
        Swap target and query in psls
        """),

    'pslToBed': dedent(
        """
        transform a psl format file to a bed format file.
        """),  # note for those keeping track, s/tranform/transform
}

SKIP = [
    'sizeof',
]

custom_build_scripts = {
    'fetchChromSizes': 'template-build-fetchChromSizes.sh',
}

for block in parse_footer('FOOTER'):
    if len(block) == 2:
        program, summary = block
        program = problematic.get(program, program)
        summary_program, description = summary

        # some programs -- like bedGraphToBigWig -- have summary lines that
        # look like this:
        #
        #   bedGraphToBigWig v 4 - Convert a bedGraph file to bigWig format
        #
        # So just get the first word as the program name.
        summary_program = summary_program.split()[0]
        if program != summary_program:
            try:
                program = resolve_header_and_summary_conflicts[program]
            except KeyError:
                raise ValueError(
                    "mismatch in header and summary. header: "
                    "'{0}'; summary: '{1}'"
                    .format(program, summary_program))
        if program in SKIP:
            continue

    else:
        assert len(block) == 1
        program = block[0]
        if program in SKIP:
            continue
        description = manual_descriptions[program]

    # conda package names must be lowercase
    package = 'ucsc-' + program.lower()
    recipe_dir = os.path.join(recipes_dir, package)

    subdir = program_subdir(program, names)
    if subdir is None and program not in custom_build_scripts:
        print("Skipping {0}".format(program))
        continue

    if not os.path.exists(recipe_dir):
        os.makedirs(recipe_dir)

    # Fill in templates and write them to recipe dir
    with open(os.path.join(recipe_dir, 'meta.yaml'), 'w') as fout:
        fout.write(
            meta_template.format(
                program=program,
                package=package,
                summary=description,
                version=VERSION,
            )
        )

    with open(os.path.join(recipe_dir, 'build.sh'), 'w') as fout:
        _template = open(
            custom_build_scripts.get(program, 'template-build.sh')
        ).read()

        fout.write(
            _template.format(
                program=program,
                program_source_dir=program_subdir(program, names),
            )
        )

    with open(os.path.join(recipe_dir, 'run_test.sh'), 'w') as fout:
        fout.write(
            test_template.format(
                program=program
            )
        )

    with open(os.path.join(recipe_dir, 'include.patch'), 'w') as fout:
        fout.write(open('include.patch').read())
