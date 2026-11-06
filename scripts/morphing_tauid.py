#!/usr/bin/env python3
"""Command line interface for CombineHarvester.TauIDSFSimple.produce_datacards.

Options and defaults are taken from the function signature, so they always
match it (and the C++ MorphingTauID2017 option names), e.g.

    morphing_tauid.py --era=2018 --categories=DM0 --base_path=/my/shapes --output_folder=test

Booleans accept true/false or 1/0, as in the C++ program.
"""

import argparse
import inspect

from CombineHarvester.TauIDSFSimple import produce_datacards


def to_bool(value):
    if value.lower() in ("1", "true", "yes"):
        return True
    if value.lower() in ("0", "false", "no"):
        return False
    raise argparse.ArgumentTypeError("expected a boolean, got '{}'".format(value))


parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
for name, param in inspect.signature(produce_datacards).parameters.items():
    flags = ["--" + name] + (["--categories"] if name == "category" else [])  # C++ option name
    kind = to_bool if isinstance(param.default, bool) else type(param.default)
    parser.add_argument(*flags, dest=name, type=kind, default=param.default,
                        help="default: %(default)s")

produce_datacards(**vars(parser.parse_args()))
